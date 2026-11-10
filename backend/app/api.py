import asyncio
import base64
from datetime import datetime
import os
from pathlib import Path
import secrets
import time
from typing import Any, Dict, List, Optional
import urllib.parse
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .auth_webauthn import (
    decode_b64url,
    encode_b64url,
    generate_challenge,
    parse_and_verify_registration,
    verify_and_consume_challenge,
    verify_authentication_assertion,
)
from .builder import build_base64_config, build_clash_config, build_singbox_config, extract_dynamic_groups
from .db import get_db
from .models import Node, PasskeyCredential, Setting, Source, User
from .parsers.clash import extract_subscription_extra_info
from .security import (
    create_session_token,
    generate_secure_password,
    hash_password,
    validate_password,
    validate_username,
    verify_password,
    verify_session_token,
)
from .syncer import ping_single_node, sync_single_source
from .version import VERSION

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY", "sub-egress-secure-signing-salt-key-v3")

DEFAULT_SETTINGS = {
    "sub_hash_token": "e699ffd91845385075b27d813b8590df40375c6af2c4eb77",
    "require_token": "false",
    "default_target": "clash",
    "update_interval": "12",
    "write_api_token": "sec_7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d",
    "subscription_title": "sub-egress",
    "clash_mixed_port": "7897",
    "clash_terminal_port": "7898",
    "custom_direct_domains": "ying-qing.cn",
    "custom_nameserver_policy": '{"geosite:cn": ["223.5.5.5", "119.29.29.29"], "+.hosecloud.com": ["223.5.5.5", "119.29.29.29"], "+.ekuaibao.com": ["223.5.5.5", "119.29.29.29"]}',
    "profile_web_url": ""
}

async def get_system_settings(db: AsyncSession) -> Dict[str, str]:
    stmt = select(Setting)
    res = await db.execute(stmt)
    db_settings = {s.key: s.value for s in res.scalars().all()}
    
    # 补齐默认设置
    merged = dict(DEFAULT_SETTINGS)
    missing = []
    for k, v in DEFAULT_SETTINGS.items():
        if k in db_settings:
            merged[k] = db_settings[k]
        else:
            missing.append(Setting(key=k, value=v))
    
    if missing:
        for s in missing:
            db.add(s)
        await db.commit()
    return merged


# ==================== 用户认证与会话管理依赖 ====================

def set_auth_cookie(response: Response, user: User) -> str:
    token = create_session_token(
        {"sub": user.id, "username": user.username, "role": user.role},
        SECRET_KEY,
        expires_in_seconds=86400 * 30
    )
    response.set_cookie(
        key="sub_egress_session",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=86400 * 30,
        path="/"
    )
    return token


async def get_current_user_optional(
    request: Request,
    sub_egress_session: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
    x_authentik_username: Optional[str] = Header(None),
    x_forwarded_user: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """优先从 Cookie 读取 Session，其次从 Bearer 头部，再次从 Authentik 代理头读取"""
    token = sub_egress_session
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()

    if token:
        payload = verify_session_token(token, SECRET_KEY)
        if payload and "sub" in payload:
            user_id = payload["sub"]
            stmt = select(User).where(User.id == user_id)
            res = await db.execute(stmt)
            user = res.scalar_one_or_none()
            if user and user.is_active:
                return user

    # 兼容 Authentik 反向代理显性头
    sso_username = (x_authentik_username or x_forwarded_user or "").strip().lower()
    if sso_username:
        stmt = select(User).where(User.username == sso_username)
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()
        if user and user.is_active:
            return user

    return None


async def get_current_user(
    user: Optional[User] = Depends(get_current_user_optional)
) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="请先登录后再进行操作")
    return user


async def get_current_admin(
    user: User = Depends(get_current_user)
) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="权限不足：需要管理员身份")
    return user


# ==================== 身份认证 API ====================

class LoginPayload(BaseModel):
    username: str
    password: str

class RegisterPayload(BaseModel):
    username: str
    password: str

class ChangePasswordPayload(BaseModel):
    old_password: Optional[str] = None
    new_password: str

@router.post("/api/auth/login", summary="用户账号密码登录")
async def auth_login(payload: LoginPayload, response: Response, db: AsyncSession = Depends(get_db)):
    u_str = payload.username.strip()
    p_str = payload.password.strip()

    # 规范拦截校验：严禁大写字母
    if any(c.isupper() for c in u_str):
        raise HTTPException(status_code=400, detail="用户名严禁包含大写字母，请检查输入")
    if any(c.isupper() for c in p_str):
        raise HTTPException(status_code=400, detail="密码严禁包含大写字母，请使用小写字母、数字和符号")

    stmt = select(User).where(User.username == u_str.lower())
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=400, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="该账户已被管理员禁用，请联系管理员")

    if not user.password_hash or not verify_password(p_str, user.password_hash):
        raise HTTPException(status_code=400, detail="用户名或密码错误")

    user.last_login_at = datetime.utcnow()
    await db.commit()

    token = set_auth_cookie(response, user)
    return {
        "status": "ok",
        "token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "sub_hash_token": user.sub_hash_token,
            "subscription_title": user.subscription_title,
            "clash_mixed_port": user.clash_mixed_port,
            "clash_terminal_port": user.clash_terminal_port,
            "custom_direct_domains": user.custom_direct_domains or "ying-qing.cn",
            "custom_proxy_domains": user.custom_proxy_domains or "",
            "custom_rules": user.custom_rules or ""
        }
    }


@router.post("/api/auth/register", summary="新用户自主注册")
async def auth_register(payload: RegisterPayload, response: Response, db: AsyncSession = Depends(get_db)):
    # 彻底关闭新用户自主注册功能
    raise HTTPException(
        status_code=403,
        detail="系统已关闭新用户自主注册功能，如需使用请联系系统管理员分配账号"
    )


@router.get("/api/auth/me", summary="获取当前登录用户信息")
async def auth_me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # 统计用户通行密钥数量
    pk_stmt = select(PasskeyCredential).where(PasskeyCredential.user_id == user.id)
    pk_res = await db.execute(pk_stmt)
    passkeys = pk_res.scalars().all()

    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_active": user.is_active,
        "has_password": bool(user.password_hash),
        "sub_hash_token": user.sub_hash_token,
        "subscription_title": user.subscription_title,
        "clash_mixed_port": user.clash_mixed_port,
        "clash_terminal_port": user.clash_terminal_port,
        "custom_direct_domains": user.custom_direct_domains or "ying-qing.cn",
        "custom_proxy_domains": user.custom_proxy_domains or "",
        "custom_rules": user.custom_rules or "",
        "passkeys_count": len(passkeys),
        "oauth_provider": user.oauth_provider,
        "oauth_id": user.oauth_id,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None
    }


@router.post("/api/auth/logout", summary="退出登录并注销会话")
async def auth_logout(response: Response):
    response.delete_cookie(key="sub_egress_session", path="/")
    return {"status": "ok", "message": "已成功退出登录"}


@router.post("/api/auth/change-password", summary="当前用户修改密码")
async def auth_change_password(
    payload: ChangePasswordPayload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if user.password_hash:
        if not payload.old_password or not verify_password(payload.old_password, user.password_hash):
            raise HTTPException(status_code=400, detail="原密码错误")

    valid, msg = validate_password(payload.new_password)
    if not valid:
        raise HTTPException(status_code=400, detail=msg)

    user.password_hash = hash_password(payload.new_password)
    await db.commit()
    return {"status": "ok", "message": "密码修改成功"}


# ==================== 通行密钥 (Passkey / WebAuthn) API ====================

class PasskeyRegisterFinishPayload(BaseModel):
    id: str
    rawId: str
    type: str
    name: Optional[str] = "我的通行密钥"
    response: Dict[str, Any]

class PasskeyLoginFinishPayload(BaseModel):
    id: str
    rawId: str
    type: str
    response: Dict[str, Any]

@router.post("/api/auth/passkey/register/start", summary="发起通行密钥注册挑战")
async def passkey_register_start(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # 硬限制：每个账号最多只允许绑定 5 个通行密钥
    count_stmt = select(func.count(PasskeyCredential.id)).where(PasskeyCredential.user_id == user.id)
    pk_count = (await db.execute(count_stmt)).scalar() or 0
    if pk_count >= 5:
        raise HTTPException(
            status_code=400,
            detail="每个账号最多只允许绑定 5 个通行密钥。请在安全中心解绑多余设备后再添加新密钥。"
        )

    host = request.headers.get("host", "sub.ying-qing.cn").split(":")[0]
    challenge = generate_challenge(f"reg:{user.id}", ttl_seconds=300)

    return {
        "challenge": challenge,
        "rp": {
            "name": "sub-egress",
            "id": host
        },
        "user": {
            "id": encode_b64url(str(user.id).encode("utf-8")),
            "name": user.username,
            "displayName": user.username
        },
        "pubKeyCredParams": [
            {"type": "public-key", "alg": -7},    # ES256 (P-256)
            {"type": "public-key", "alg": -257}   # RS256
        ],
        "authenticatorSelection": {
            "residentKey": "preferred",
            "userVerification": "preferred"
        },
        "timeout": 60000,
        "attestation": "none"
    }


@router.post("/api/auth/passkey/register/finish", summary="完成通行密钥注册并存储公钥")
async def passkey_register_finish(
    request: Request,
    payload: PasskeyRegisterFinishPayload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    host = request.headers.get("host", "sub.ying-qing.cn").split(":")[0]
    reg_key = f"reg:{user.id}"
    
    # 获取之前缓存的 challenge
    stored = _get_stored_challenge(reg_key)
    if not stored:
        raise HTTPException(status_code=400, detail="通行密钥注册挑战已过期，请重试")

    client_data_b64 = payload.response.get("clientDataJSON")
    attestation_b64 = payload.response.get("attestationObject")
    if not client_data_b64 or not attestation_b64:
        raise HTTPException(status_code=400, detail="缺少 WebAuthn 注册凭证数据")

    try:
        cred_info = parse_and_verify_registration(
            client_data_json_b64=client_data_b64,
            attestation_obj_b64=attestation_b64,
            expected_challenge=stored,
            rp_id=host
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"通行密钥注册校验失败: {e}")

    # 消费 Challenge
    verify_and_consume_challenge(reg_key, stored)

    # 硬限制：每个账号最多只允许绑定 5 个通行密钥
    count_stmt = select(func.count(PasskeyCredential.id)).where(PasskeyCredential.user_id == user.id)
    pk_count = (await db.execute(count_stmt)).scalar() or 0
    if pk_count >= 5:
        raise HTTPException(status_code=400, detail="每个账号最多只允许绑定 5 个通行密钥，已达到上限")

    # 检查是否重复注册
    stmt = select(PasskeyCredential).where(PasskeyCredential.credential_id == cred_info["credential_id"])
    res = await db.execute(stmt)
    if res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该通行密钥凭证已绑定过，请勿重复注册")

    passkey = PasskeyCredential(
        user_id=user.id,
        credential_id=cred_info["credential_id"],
        public_key=cred_info["public_key_pem"],
        sign_count=cred_info["sign_count"],
        name=payload.name or "我的通行密钥",
        aaguid=cred_info.get("aaguid")
    )
    db.add(passkey)
    await db.commit()

    return {"status": "ok", "message": "通行密钥绑定成功！"}


@router.post("/api/auth/passkey/login/start", summary="发起通行密钥免密登录挑战")
async def passkey_login_start(
    request: Request,
    username: Optional[str] = Query(None)
):
    host = request.headers.get("host", "sub.ying-qing.cn").split(":")[0]
    challenge = generate_challenge("login_assertion", ttl_seconds=300)

    return {
        "challenge": challenge,
        "rpId": host,
        "timeout": 60000,
        "userVerification": "preferred"
    }


@router.post("/api/auth/passkey/login/finish", summary="校验通行密钥并完成登录")
async def passkey_login_finish(
    request: Request,
    payload: PasskeyLoginFinishPayload,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    host = request.headers.get("host", "sub.ying-qing.cn").split(":")[0]
    stored = _get_stored_challenge("login_assertion")
    if not stored:
        raise HTTPException(status_code=400, detail="登录挑战已失效或过期，请重新点击登录")

    client_data_b64 = payload.response.get("clientDataJSON")
    auth_data_b64 = payload.response.get("authenticatorData")
    sig_b64 = payload.response.get("signature")

    if not client_data_b64 or not auth_data_b64 or not sig_b64:
        raise HTTPException(status_code=400, detail="缺少通行密钥认证数据")

    # 根据 credential_id 查找绑定记录
    cred_id = payload.id
    stmt = (
        select(PasskeyCredential)
        .options(selectinload(PasskeyCredential.user))
        .where(PasskeyCredential.credential_id == cred_id)
    )
    res = await db.execute(stmt)
    passkey = res.scalar_one_or_none()
    if not passkey:
        raise HTTPException(status_code=400, detail="未找到与该设备匹配的通行密钥，请先使用密码登录后在个人安全中心绑定")

    user = passkey.user
    if not user or not user.is_active:
        raise HTTPException(status_code=403, detail="该账户已被管理员禁用，请联系管理员")

    try:
        new_sign_count = verify_authentication_assertion(
            client_data_json_b64=client_data_b64,
            authenticator_data_b64=auth_data_b64,
            signature_b64=sig_b64,
            expected_challenge=stored,
            public_key_pem=passkey.public_key,
            expected_rp_id=host,
            stored_sign_count=passkey.sign_count
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"通行密钥验签失败: {e}")

    # 消费 challenge
    verify_and_consume_challenge("login_assertion", stored)

    passkey.sign_count = new_sign_count
    passkey.last_used_at = datetime.utcnow()
    user.last_login_at = datetime.utcnow()
    await db.commit()

    token = set_auth_cookie(response, user)
    return {
        "status": "ok",
        "token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "sub_hash_token": user.sub_hash_token,
            "subscription_title": user.subscription_title
        }
    }


def _get_stored_challenge(key: str) -> Optional[str]:
    from .auth_webauthn import _CHALLENGES
    item = _CHALLENGES.get(key)
    if item and item[1] > time.time():
        return item[0]
    return None


# ==================== 用户个人设置 API ====================

class UserSettingsPayload(BaseModel):
    subscription_title: Optional[str] = None
    clash_mixed_port: Optional[str] = None
    clash_terminal_port: Optional[str] = None
    custom_direct_domains: Optional[str] = None
    custom_proxy_domains: Optional[str] = None
    custom_rules: Optional[str] = None

@router.post("/api/user/settings", summary="保存当前用户专属订阅偏好")
async def update_user_settings(
    payload: UserSettingsPayload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if payload.subscription_title is not None:
        user.subscription_title = payload.subscription_title.strip()
    if payload.clash_mixed_port is not None:
        user.clash_mixed_port = str(payload.clash_mixed_port).strip()
    if payload.clash_terminal_port is not None:
        user.clash_terminal_port = str(payload.clash_terminal_port).strip()
    if payload.custom_direct_domains is not None:
        user.custom_direct_domains = payload.custom_direct_domains.strip()
    if payload.custom_proxy_domains is not None:
        user.custom_proxy_domains = payload.custom_proxy_domains.strip()
    if payload.custom_rules is not None:
        user.custom_rules = payload.custom_rules.strip()
    await db.commit()
    return {"status": "ok", "message": "个人订阅配置与分流规则已更新"}


@router.post("/api/user/regenerate-token", summary="用户重置自身专属订阅令牌")
async def user_regenerate_token(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    new_token = secrets.token_hex(24)
    user.sub_hash_token = new_token
    await db.commit()
    return {"status": "ok", "new_token": new_token}


@router.get("/api/user/passkeys", summary="获取当前用户绑定的所有通行密钥")
async def list_user_passkeys(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(PasskeyCredential).where(PasskeyCredential.user_id == user.id).order_by(PasskeyCredential.id)
    res = await db.execute(stmt)
    keys = res.scalars().all()
    return [
        {
            "id": k.id,
            "name": k.name,
            "credential_id": k.credential_id[:16] + "...",
            "created_at": k.created_at.isoformat() if k.created_at else None,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "sign_count": k.sign_count
        }
        for k in keys
    ]


@router.delete("/api/user/passkeys/{key_id}", summary="当前用户删除自身指定通行密钥")
async def delete_user_passkey(
    key_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(PasskeyCredential).where(PasskeyCredential.id == key_id, PasskeyCredential.user_id == user.id)
    res = await db.execute(stmt)
    k = res.scalar_one_or_none()
    if not k:
        raise HTTPException(status_code=404, detail="未找到该通行密钥凭证")
    await db.delete(k)
    await db.commit()
    return {"status": "ok", "message": "通行密钥已解除绑定"}


class BindOAuthPayload(BaseModel):
    provider: Optional[str] = "authentik"
    oauth_id: Optional[str] = None

@router.post("/api/user/unbind-oauth", summary="当前用户解绑第三方身份源")
async def user_unbind_oauth(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # 安全防自锁检查：若用户未设置本地密码且没有任何通行密钥，禁止解绑以防账号无法登录！
    if not user.password_hash:
        count_stmt = select(func.count(PasskeyCredential.id)).where(PasskeyCredential.user_id == user.id)
        pk_count = (await db.execute(count_stmt)).scalar() or 0
        if pk_count == 0:
            raise HTTPException(
                status_code=400,
                detail="为了您的账户安全，解绑第三方登录前请先设置登录密码或至少绑定一个通行密钥，以防账号无法登录。"
            )

    user.oauth_provider = None
    user.oauth_id = None
    await db.commit()
    return {"status": "ok", "message": "已成功解除第三方登录绑定"}


@router.post("/api/user/bind-oauth", summary="当前用户绑定第三方身份源")
async def user_bind_oauth(
    payload: BindOAuthPayload,
    user: User = Depends(get_current_user),
    x_authentik_username: Optional[str] = Header(None),
    x_forwarded_user: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
):
    sso_user = (payload.oauth_id or x_authentik_username or x_forwarded_user or user.username).strip()
    user.oauth_provider = payload.provider or "authentik"
    user.oauth_id = sso_user
    await db.commit()
    return {"status": "ok", "message": f"已成功绑定第三方登录 ({user.oauth_provider}: {user.oauth_id})"}


# ==================== 管理员管理面板 API (独立页签与专属权限) ====================

class AdminResetPasswordPayload(BaseModel):
    new_password: Optional[str] = None

@router.get("/api/admin/users", summary="管理员查看全量用户列表")
async def admin_list_users(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(User).options(selectinload(User.passkeys)).order_by(User.id)
    res = await db.execute(stmt)
    users = res.scalars().all()

    results = []
    for u in users:
        results.append({
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "is_active": u.is_active,
            "sub_hash_token": u.sub_hash_token,
            "subscription_title": u.subscription_title,
            "clash_mixed_port": u.clash_mixed_port,
            "clash_terminal_port": u.clash_terminal_port,
            "oauth_provider": u.oauth_provider,
            "passkeys_count": len(u.passkeys),
            "passkeys": [
                {
                    "id": p.id,
                    "name": p.name,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "last_used_at": p.last_used_at.isoformat() if p.last_used_at else None,
                    "sign_count": p.sign_count
                }
                for p in u.passkeys
            ],
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None
        })
    return results


@router.post("/api/admin/users/{user_id}/activate", summary="管理员激活指定用户")
async def admin_activate_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(User).where(User.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.is_active = True
    await db.commit()
    return {"status": "ok", "message": f"用户 {user.username} 已激活"}


@router.post("/api/admin/users/{user_id}/deactivate", summary="管理员禁用指定用户")
async def admin_deactivate_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="管理员不能禁用自身账号")
    stmt = select(User).where(User.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.is_active = False
    await db.commit()
    return {"status": "ok", "message": f"用户 {user.username} 已禁用"}


@router.post("/api/admin/users/{user_id}/reset-password", summary="管理员重置用户级别密码")
async def admin_reset_user_password(
    user_id: int,
    payload: AdminResetPasswordPayload,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    # 严格硬拦截：管理员严禁在管理面板重设自身密码！
    if user_id == admin.id:
        raise HTTPException(
            status_code=400,
            detail="管理员严禁在管理页面重设自身密码！若需修改自身密码请使用个人修改密码功能，若遗忘密码请通过服务器重启环境变量 RESET_ADMIN_PASSWORD 重设。"
        )

    stmt = select(User).where(User.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="目标用户不存在")

    if payload.new_password:
        p_valid, p_msg = validate_password(payload.new_password)
        if not p_valid:
            raise HTTPException(status_code=400, detail=p_msg)
        new_pwd = payload.new_password
    else:
        new_pwd = generate_secure_password(32)

    user.password_hash = hash_password(new_pwd)
    await db.commit()

    return {
        "status": "ok",
        "username": user.username,
        "new_password": new_pwd,
        "message": f"已成功重置用户 {user.username} 的密码！"
    }


@router.delete("/api/admin/users/{user_id}/passkeys/{key_id}", summary="管理员解绑用户的通行密钥")
async def admin_unbind_user_passkey(
    user_id: int,
    key_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(PasskeyCredential).where(PasskeyCredential.id == key_id, PasskeyCredential.user_id == user_id)
    res = await db.execute(stmt)
    k = res.scalar_one_or_none()
    if not k:
        raise HTTPException(status_code=404, detail="未找到该通行密钥")
    await db.delete(k)
    await db.commit()
    return {"status": "ok", "message": "已成功解绑该通行密钥"}


@router.post("/api/admin/users/{user_id}/unbind-oauth", summary="管理员解绑用户的第三方授权")
async def admin_unbind_user_oauth(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(User).where(User.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.oauth_provider = None
    user.oauth_id = None
    await db.commit()
    return {"status": "ok", "message": f"用户 {user.username} 的第三方授权已解除"}


# ==================== 下游订阅分发端点 (多用户订阅隔离与客户端直连) ====================

@router.api_route("/c/{token}", methods=["GET", "HEAD"], summary="基于专属安全令牌的统一订阅调度端点")
@router.api_route("/feed", methods=["GET", "HEAD"], summary="标准统一订阅调度端点")
async def export_subscription(
    request: Request,
    token: Optional[str] = None,
    target: Optional[str] = Query(None, description="目标客户端内核: clash, sing-box, base64"),
    type: Optional[str] = Query(None, description="别名目标内核: clash, sing-box, base64"),
    name: Optional[str] = Query(None, description="自定义订阅卡片名称 (显示在客户端)"),
    title: Optional[str] = Query(None, description="自定义订阅卡片名称 (别名)"),
    t: Optional[str] = Query(None, description="Query 传递的安全令牌 (用于 /feed)"),
    db: AsyncSession = Depends(get_db)
):
    settings = await get_system_settings(db)
    req_token = token or t

    # 1. 根据专属 Token 查找对应用户 (实现多用户资源隔离)
    matched_user: Optional[User] = None
    if req_token:
        u_stmt = select(User).where(User.sub_hash_token == req_token)
        u_res = await db.execute(u_stmt)
        matched_user = u_res.scalar_one_or_none()

    # 读权限安全检查
    if settings.get("require_token", "false").lower() == "true":
        expected_token = settings.get("sub_hash_token", "")
        if not matched_user and req_token != expected_token:
            raise HTTPException(
                status_code=403,
                detail="403 Forbidden: Invalid or missing subscription security hash token"
            )

    if matched_user and not matched_user.is_active:
        raise HTTPException(status_code=403, detail="403 Forbidden: Account is deactivated")

    # 确定目标导出内核
    raw_target = (target or type or settings.get("default_target", "clash")).lower()
    if raw_target in ("sing-box", "singbox", "sb"):
        final_target = "sing-box"
    elif raw_target in ("base64", "uri", "txt"):
        final_target = "base64"
    else:
        final_target = "clash"

    # 多租户节点源过滤：提取公共共享源 + 用户私有源
    stmt = (
        select(Node, Source.name.label("source_name"))
        .join(Source, Node.source_id == Source.id)
        .where(Source.enabled == True)
    )
    if matched_user:
        stmt = stmt.where((Source.is_shared == True) | (Source.user_id == matched_user.id))
    else:
        stmt = stmt.where(Source.is_shared == True)

    stmt = stmt.order_by(Node.country_code, Node.id)
    result = await db.execute(stmt)
    rows = result.all()

    nodes_list = []
    source_traffic_info = {}
    for node, source_name in rows:
        cfg = dict(node.config_json)
        cfg["source_name"] = source_name
        cfg["display_name"] = node.display_name
        cfg["country_code"] = node.country_code
        cfg["is_residential"] = node.is_residential
        nodes_list.append(cfg)

    # 计算总流量与到期时间
    src_stmt = select(Source).where(Source.enabled == True)
    if matched_user:
        src_stmt = src_stmt.where((Source.is_shared == True) | (Source.user_id == matched_user.id))
    else:
        src_stmt = src_stmt.where(Source.is_shared == True)

    src_res = await db.execute(src_stmt)
    sources = src_res.scalars().all()
    
    total_used = sum(s.traffic_used for s in sources if s.traffic_used)
    total_max = sum(s.traffic_total for s in sources if s.traffic_total)
    valid_expires = [int(s.expire_at.timestamp()) for s in sources if s.expire_at]
    earliest_expire = min(valid_expires) if valid_expires else int(time.time()) + 86400 * 365

    # 用户个性化卡片标题与端口
    display_profile_title = name or title or (matched_user.subscription_title if matched_user else settings.get("subscription_title", "sub-egress"))
    mixed_port = matched_user.clash_mixed_port if matched_user else settings.get("clash_mixed_port", "7897")
    terminal_port = matched_user.clash_terminal_port if matched_user else settings.get("clash_terminal_port", "7898")

    # 用户级 / 全局分流规则与直连域名 (最高优先级)
    user_direct_raw = (
        matched_user.custom_direct_domains
        if (matched_user and matched_user.custom_direct_domains is not None)
        else settings.get("custom_direct_domains", "ying-qing.cn")
    )
    direct_domains = [d.strip() for d in (user_direct_raw or "").replace("\n", ",").replace(";", ",").split(",") if d.strip()]

    user_proxy_raw = (
        matched_user.custom_proxy_domains
        if (matched_user and matched_user.custom_proxy_domains is not None)
        else settings.get("custom_proxy_domains", "")
    )
    proxy_domains = [d.strip() for d in (user_proxy_raw or "").replace("\n", ",").replace(";", ",").split(",") if d.strip()]

    user_rules_raw = (
        matched_user.custom_rules
        if (matched_user and matched_user.custom_rules is not None)
        else settings.get("custom_rules", "")
    )
    custom_rules_list = [r.strip() for r in (user_rules_raw or "").splitlines() if r.strip() and not r.strip().startswith("#")]

    # 构建对应内核配置
    if final_target == "clash":
        try:
            m_port = int(mixed_port)
        except (ValueError, TypeError):
            m_port = 7897
        try:
            t_port = int(terminal_port)
        except (ValueError, TypeError):
            t_port = 7898

        content = build_clash_config(
            nodes_list,
            mixed_port=m_port,
            terminal_port=t_port,
            custom_direct_domains=direct_domains,
            custom_proxy_domains=proxy_domains,
            custom_rules=custom_rules_list
        )
        media_type = "text/yaml; charset=utf-8"
    elif final_target == "sing-box":
        content = build_singbox_config(nodes_list, custom_direct_domains=direct_domains)
        media_type = "application/json; charset=utf-8"
    else:
        content = build_base64_config(nodes_list)
        media_type = "text/plain; charset=utf-8"

    interval_sec = int(settings.get("update_interval", "12")) * 3600
    safe_profile_title = urllib.parse.quote(display_profile_title)
    
    headers = {
        "content-disposition": f'inline; filename="{safe_profile_title}.yaml"',
        "profile-update-interval": str(interval_sec),
        "profile-title": f"base64:{base64.b64encode(display_profile_title.encode('utf-8')).decode('utf-8')}",
        "profile-web-page-url": str(request.base_url)
    }
    if total_max > 0:
        headers["subscription-userinfo"] = f"upload=0; download={total_used}; total={total_max}; expire={earliest_expire}"

    return Response(content=content, media_type=media_type, headers=headers)


# ==================== 读写设置 API ====================

class SettingsPayload(BaseModel):
    sub_hash_token: Optional[str] = None
    require_token: Optional[bool] = None
    default_target: Optional[str] = None
    update_interval: Optional[str] = None
    write_api_token: Optional[str] = None
    subscription_title: Optional[str] = None
    clash_mixed_port: Optional[str] = None
    clash_terminal_port: Optional[str] = None
    custom_direct_domains: Optional[str] = None
    custom_proxy_domains: Optional[str] = None
    custom_rules: Optional[str] = None

@router.get("/api/settings", summary="获取全局读写与安全设置")
async def get_settings(user: Optional[User] = Depends(get_current_user_optional), db: AsyncSession = Depends(get_db)):
    settings = await get_system_settings(db)
    # 若有当前用户，返回该用户专有端口、标题与分流规则
    sub_title = user.subscription_title if user else settings.get("subscription_title", "sub-egress")
    m_port = user.clash_mixed_port if user else settings.get("clash_mixed_port", "7897")
    t_port = user.clash_terminal_port if user else settings.get("clash_terminal_port", "7898")
    u_token = user.sub_hash_token if user else settings.get("sub_hash_token", "")
    direct_domains = (
        user.custom_direct_domains
        if (user and user.custom_direct_domains is not None)
        else settings.get("custom_direct_domains", "ying-qing.cn")
    )
    proxy_domains = (
        user.custom_proxy_domains
        if (user and user.custom_proxy_domains is not None)
        else settings.get("custom_proxy_domains", "")
    )
    custom_rules = (
        user.custom_rules
        if (user and user.custom_rules is not None)
        else settings.get("custom_rules", "")
    )

    return {
        "version": VERSION,
        "sub_hash_token": u_token,
        "require_token": settings.get("require_token", "false").lower() == "true",
        "default_target": settings.get("default_target", "clash"),
        "update_interval": settings.get("update_interval", "12"),
        "write_api_token": settings.get("write_api_token", ""),
        "subscription_title": sub_title,
        "clash_mixed_port": m_port,
        "clash_terminal_port": t_port,
        "custom_direct_domains": direct_domains,
        "custom_proxy_domains": proxy_domains,
        "custom_rules": custom_rules
    }


@router.post("/api/settings", summary="保存全局读写设置")
async def update_settings(
    payload: SettingsPayload,
    user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    updates = {}
    if payload.sub_hash_token is not None:
        updates["sub_hash_token"] = payload.sub_hash_token.strip()
        if user:
            user.sub_hash_token = payload.sub_hash_token.strip()
    if payload.require_token is not None:
        updates["require_token"] = "true" if payload.require_token else "false"
    if payload.default_target is not None:
        updates["default_target"] = payload.default_target.strip().lower()
    if payload.update_interval is not None:
        updates["update_interval"] = payload.update_interval.strip()
    if payload.write_api_token is not None:
        updates["write_api_token"] = payload.write_api_token.strip()
    if payload.subscription_title is not None:
        updates["subscription_title"] = payload.subscription_title.strip()
        if user:
            user.subscription_title = payload.subscription_title.strip()
    if payload.clash_mixed_port is not None:
        updates["clash_mixed_port"] = str(payload.clash_mixed_port).strip()
        if user:
            user.clash_mixed_port = str(payload.clash_mixed_port).strip()
    if payload.clash_terminal_port is not None:
        updates["clash_terminal_port"] = str(payload.clash_terminal_port).strip()
        if user:
            user.clash_terminal_port = str(payload.clash_terminal_port).strip()
    if payload.custom_direct_domains is not None:
        updates["custom_direct_domains"] = payload.custom_direct_domains.strip()
        if user:
            user.custom_direct_domains = payload.custom_direct_domains.strip()
    if payload.custom_proxy_domains is not None:
        updates["custom_proxy_domains"] = payload.custom_proxy_domains.strip()
        if user:
            user.custom_proxy_domains = payload.custom_proxy_domains.strip()
    if payload.custom_rules is not None:
        updates["custom_rules"] = payload.custom_rules.strip()
        if user:
            user.custom_rules = payload.custom_rules.strip()

    for k, v in updates.items():
        stmt = select(Setting).where(Setting.key == k)
        res = await db.execute(stmt)
        setting = res.scalar_one_or_none()
        if setting:
            setting.value = v
        else:
            db.add(Setting(key=k, value=v))
    await db.commit()
    return {"status": "success", "message": "Settings updated"}


@router.post("/api/settings/regenerate-token", summary="重新生成安全哈希令牌")
async def regenerate_token(
    user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    new_token = secrets.token_hex(24)
    if user:
        user.sub_hash_token = new_token

    stmt = select(Setting).where(Setting.key == "sub_hash_token")
    res = await db.execute(stmt)
    setting = res.scalar_one_or_none()
    if setting:
        setting.value = new_token
    else:
        db.add(Setting(key="sub_hash_token", value=new_token))
    await db.commit()
    return {"status": "success", "new_token": new_token}


# ==================== 上游源管理 API (供 Web 控制台) ====================

class SourceCreate(BaseModel):
    name: str
    url: str
    source_type: Optional[str] = "auto"
    raw_content: Optional[str] = None
    is_shared: Optional[bool] = True

class SourceUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    enabled: Optional[bool] = None
    raw_content: Optional[str] = None
    is_shared: Optional[bool] = None

@router.get("/api/sources", summary="获取上游源列表")
async def list_sources(
    user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Source).order_by(Source.id)
    if user and user.role != "admin":
        stmt = stmt.where((Source.is_shared == True) | (Source.user_id == user.id))

    res = await db.execute(stmt)
    sources = res.scalars().all()
    results = []
    for s in sources:
        extra = extract_subscription_extra_info(s.raw_content or "")
        results.append({
            "id": s.id,
            "name": s.name,
            "url": s.url,
            "source_type": s.source_type,
            "enabled": s.enabled,
            "status": s.status,
            "error_message": s.error_message,
            "node_count": s.node_count,
            "traffic_used": s.traffic_used,
            "traffic_total": s.traffic_total,
            "is_shared": s.is_shared,
            "user_id": s.user_id,
            "expire_at": s.expire_at.isoformat() if s.expire_at else None,
            "last_sync_at": s.last_sync_at.isoformat() if s.last_sync_at else None,
            "reset_info": extra.get("reset_info"),
            "remaining_text": extra.get("remaining_text")
        })
    return results

@router.post("/api/sources", summary="新增上游源")
async def create_source(
    payload: SourceCreate,
    user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    is_shared = payload.is_shared if (user and user.role == "admin") else (user is None)
    src = Source(
        user_id=user.id if user else None,
        is_shared=is_shared,
        name=payload.name.strip(),
        url=payload.url.strip(),
        source_type=payload.source_type or "auto",
        raw_content=payload.raw_content
    )
    db.add(src)
    await db.commit()
    await db.refresh(src)

    # 异步触发首次同步
    await sync_single_source(src.id, db)
    return {"status": "success", "id": src.id}

@router.put("/api/sources/{source_id}", summary="编辑上游源")
async def update_source(
    source_id: int,
    payload: SourceUpdate,
    user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Source).where(Source.id == source_id)
    res = await db.execute(stmt)
    src = res.scalar_one_or_none()
    if not src:
        raise HTTPException(status_code=404, detail="Source not found")

    if user and user.role != "admin" and src.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权修改他人所属的节点源")

    if payload.name is not None:
        src.name = payload.name.strip()
    if payload.url is not None:
        src.url = payload.url.strip()
    if payload.enabled is not None:
        src.enabled = payload.enabled
    if payload.raw_content is not None:
        src.raw_content = payload.raw_content
    if payload.is_shared is not None and user and user.role == "admin":
        src.is_shared = payload.is_shared

    await db.commit()
    await sync_single_source(src.id, db)
    return {"status": "success"}

@router.delete("/api/sources/{source_id}", summary="删除上游源")
async def delete_source(
    source_id: int,
    user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Source).where(Source.id == source_id)
    res = await db.execute(stmt)
    src = res.scalar_one_or_none()
    if not src:
        raise HTTPException(status_code=404, detail="Source not found")

    if user and user.role != "admin" and src.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权删除他人所属的节点源")

    await db.execute(delete(Source).where(Source.id == source_id))
    await db.commit()
    return {"status": "success"}

@router.post("/api/sources/{source_id}/refresh", summary="手动刷新指定上游源")
async def refresh_source(
    source_id: int,
    user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    success = await sync_single_source(source_id, db)
    if not success:
        stmt = select(Source).where(Source.id == source_id)
        res = await db.execute(stmt)
        src = res.scalar_one_or_none()
        err = src.error_message if src else "Unknown error"
        raise HTTPException(status_code=500, detail=f"Refresh failed: {err}")
    return {"status": "success"}


# ==================== 节点与动态策略组大盘 API ====================

@router.get("/api/nodes", summary="获取平铺节点池与动态策略组")
async def list_nodes(
    user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Node, Source.name.label("source_name"))
        .join(Source, Node.source_id == Source.id)
        .where(Source.enabled == True)
    )
    if user and user.role != "admin":
        stmt = stmt.where((Source.is_shared == True) | (Source.user_id == user.id))

    stmt = stmt.order_by(Node.country_code, Node.id)
    res = await db.execute(stmt)
    rows = res.all()

    nodes = []
    raw_nodes_for_groups = []
    for node, source_name in rows:
        node_dict = {
            "id": node.id,
            "source_id": node.source_id,
            "source_name": source_name,
            "original_name": node.original_name,
            "display_name": node.display_name,
            "node_type": node.node_type,
            "server": node.server,
            "port": node.port,
            "country_code": node.country_code,
            "country_flag": node.country_flag,
            "is_residential": node.is_residential,
            "latency": node.latency,
            "latency_status": node.latency_status,
            "latency_updated_at": node.latency_updated_at.isoformat() if node.latency_updated_at else None,
            "config_json": node.config_json
        }
        nodes.append(node_dict)
        raw_nodes_for_groups.append({
            **node.config_json,
            "display_name": node.display_name,
            "country_code": node.country_code,
            "is_residential": node.is_residential
        })

    dynamic_groups = extract_dynamic_groups(raw_nodes_for_groups)
    return {
        "total": len(nodes),
        "dynamic_groups": dynamic_groups,
        "nodes": nodes
    }


# ==================== 节点延迟测速 API ====================

class BatchPingPayload(BaseModel):
    node_ids: Optional[List[int]] = None

@router.post("/api/nodes/{node_id}/ping", summary="测试单个节点网络握手延迟")
async def ping_node_endpoint(node_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Node).where(Node.id == node_id)
    res = await db.execute(stmt)
    node = res.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    result = await ping_single_node(node.server, node.port, node.node_type)
    node.latency = result["latency"]
    node.latency_status = result["status"]
    node.latency_updated_at = datetime.utcnow()
    await db.commit()

    return {
        "node_id": node.id,
        "display_name": node.display_name,
        "server": node.server,
        "port": node.port,
        **result
    }

@router.post("/api/nodes/ping", summary="批量并发测试节点延迟")
async def batch_ping_nodes(payload: Optional[BatchPingPayload] = None, db: AsyncSession = Depends(get_db)):
    stmt = select(Node)
    if payload and payload.node_ids:
        stmt = stmt.where(Node.id.in_(payload.node_ids))
    res = await db.execute(stmt)
    nodes = res.scalars().all()

    sem = asyncio.Semaphore(20)

    async def worker(node: Node):
        async with sem:
            res = await ping_single_node(node.server, node.port, node.node_type, timeout=2.5)
            node.latency = res["latency"]
            node.latency_status = res["status"]
            node.latency_updated_at = datetime.utcnow()
            return node.id, res

    tasks = [worker(n) for n in nodes]
    results = await asyncio.gather(*tasks)
    await db.commit()

    return {
        "total": len(results),
        "results": {str(nid): ping_res for nid, ping_res in results}
    }

@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "sub-egress", "version": VERSION, "timestamp": datetime.utcnow().isoformat()}

@router.get("/api/version", summary="获取服务版本号")
async def get_version():
    return {"version": VERSION}

@router.get("/favicon.ico", include_in_schema=False)
async def favicon_ico():
    fav = Path(os.getenv("FRONTEND_DIR", "/frontend")) / "favicon.ico"
    if not fav.exists():
        fav = Path(__file__).resolve().parent.parent.parent / "frontend" / "favicon.ico"
    if fav.exists():
        return FileResponse(fav, media_type="image/x-icon")
    return Response(status_code=404)
