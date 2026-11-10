import asyncio
import base64
import logging
import os
import re
import secrets
import time
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from .auth_webauthn import (
    encode_b64url,
    generate_challenge,
    parse_and_verify_registration,
    verify_and_consume_challenge,
    verify_authentication_assertion,
)
from .builder import (
    build_base64_config,
    build_clash_config,
    build_singbox_config,
    extract_dynamic_groups,
)
from .db import get_db
from .models import Node, OAuthIdentity, PasskeyCredential, Setting, Source, User
from .parsers.clash import extract_subscription_extra_info, parse_clash_yaml
from .parsers.singbox import parse_singbox_json
from .parsers.uri import parse_subscription_text
from .security import (
    create_session_token,
    generate_secure_password,
    hash_password,
    validate_password,
    validate_username,
    verify_password,
    verify_session_token,
)
from .syncer import (
    DEFAULT_UA,
    parse_userinfo_header,
    ping_single_node,
    sync_single_source,
)
from .version import VERSION

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY must be configured with a private random value")

router = APIRouter()
GITHUB_OAUTH_ISSUER = "https://github.com"

@router.get("/api/auth/github/start", include_in_schema=False)
async def github_oauth_start(request: Request, db: Annotated[AsyncSession, Depends(get_db)], mode: str = "login"):
    client_id = os.getenv("GITHUB_CLIENT_ID")
    if not client_id or not os.getenv("GITHUB_CLIENT_SECRET") or not os.getenv("GITHUB_REDIRECT_URI"):
        raise HTTPException(status_code=503, detail="GitHub OAuth 尚未配置")
    if mode not in {"login", "link"}:
        raise HTTPException(status_code=400, detail="OAuth mode 无效")
    state = secrets.token_urlsafe(32)
    local_user_id = None
    if mode == "link":
        local_user = await get_current_user_optional(request, db, request.cookies.get("sub_egress_session"))
        if not local_user:
            raise HTTPException(status_code=401, detail="绑定 GitHub 前请先登录")
        local_user_id = local_user.id
    signed_state = create_session_token({"oauth_state": state, "mode": mode, "user_id": local_user_id}, SECRET_KEY, 600)
    response = RedirectResponse("https://github.com/login/oauth/authorize?" + urllib.parse.urlencode({"client_id": client_id, "redirect_uri": os.environ["GITHUB_REDIRECT_URI"], "scope": "read:user", "state": state}), status_code=302)
    response.set_cookie("github_oauth_state", signed_state, httponly=True, secure=True, samesite="lax", max_age=600, path="/")
    return response

@router.get("/api/auth/github/callback", include_in_schema=False)
async def github_oauth_callback(request: Request, db: Annotated[AsyncSession, Depends(get_db)], code: str, state: str, github_oauth_state: Annotated[str | None, Cookie()] = None):
    state_data = verify_session_token(github_oauth_state or "", SECRET_KEY)
    if not state_data or not secrets.compare_digest(state_data.get("oauth_state", ""), state):
        raise HTTPException(status_code=400, detail="GitHub OAuth state 无效或已过期")

    github_proxy = os.getenv("GITHUB_PROXY") or os.getenv("OUTBOUND_PROXY")
    if not github_proxy and (os.path.exists("/frontend") or os.getenv("DATA_DIR") == "/data"):
        github_proxy = "http://10.42.1.1:7897"

    try:
        async with httpx.AsyncClient(proxy=github_proxy, timeout=15.0, headers={"Accept": "application/json", "User-Agent": "sub-egress"}) as client:
            token_response = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": os.environ["GITHUB_CLIENT_ID"],
                    "client_secret": os.environ["GITHUB_CLIENT_SECRET"],
                    "code": code,
                    "redirect_uri": os.environ["GITHUB_REDIRECT_URI"],
                    "state": state
                }
            )
            token_response.raise_for_status()
            access_token = token_response.json().get("access_token")
            if not access_token:
                response = RedirectResponse("/login?error=github_token_rejected", status_code=302)
                response.delete_cookie("github_oauth_state", path="/")
                return response
            profile_response = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            profile_response.raise_for_status()
            profile = profile_response.json()
    except Exception:
        response = RedirectResponse("/login?error=github_network_error", status_code=302)
        response.delete_cookie("github_oauth_state", path="/")
        return response

    subject = str(profile["id"])
    identity_result = await db.execute(select(OAuthIdentity).where(OAuthIdentity.issuer == GITHUB_OAUTH_ISSUER, OAuthIdentity.subject == subject))
    identity = identity_result.scalar_one_or_none()
    if state_data.get("mode") == "link":
        user = await db.get(User, state_data.get("user_id"))
        if not user or not user.is_active:
            response = RedirectResponse("/login?error=session_expired", status_code=302)
            response.delete_cookie("github_oauth_state", path="/")
            return response
        if identity and identity.user_id != user.id:
            response = RedirectResponse("/?error=github_already_linked", status_code=302)
            response.delete_cookie("github_oauth_state", path="/")
            return response
        if not identity:
            identity = OAuthIdentity(user_id=user.id, provider="github", issuer=GITHUB_OAUTH_ISSUER, subject=subject)
            db.add(identity)
        if not user.oauth_provider:
            user.oauth_provider = "github"
            user.oauth_id = subject
        user.last_login_at = datetime.now(UTC)
        await db.commit()
        response = RedirectResponse("/?msg=github_linked", status_code=302)
        response.delete_cookie("github_oauth_state", path="/")
        return response
    else:
        user = await db.get(User, identity.user_id) if identity else None
        if not user:
            # 严格禁止自动创建账号！签发临时 pending token 进入二级绑定核验页
            pending_token = create_session_token(
                {"action": "github_bind", "gh_id": subject, "gh_login": profile.get("login") or subject},
                SECRET_KEY,
                600
            )
            gh_login_param = urllib.parse.quote(profile.get("login") or subject)
            response = RedirectResponse(
                f"/login?step=github_bind&token={pending_token}&gh_user={gh_login_param}",
                status_code=302
            )
            response.delete_cookie("github_oauth_state", path="/")
            return response

        if not user.is_active:
            return RedirectResponse("/login?error=account_disabled", status_code=302)

        user.last_login_at = datetime.now(UTC)
        await db.commit()
        response = RedirectResponse("/", status_code=302)
        response.delete_cookie("github_oauth_state", path="/")
        set_auth_cookie(response, user)
        return response


class GitHubBindLoginPayload(BaseModel):
    pending_token: str
    username: str
    password: str


@router.post("/api/auth/github/bind-login", summary="GitHub 未关联用户二级身份校验与账号绑定")
async def github_bind_login(
    payload: GitHubBindLoginPayload,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    token_data = verify_session_token(payload.pending_token, SECRET_KEY)
    if not token_data or token_data.get("action") != "github_bind":
        raise HTTPException(status_code=400, detail="GitHub 授权会话已过期，请重新点击 GitHub 登录")

    gh_id = str(token_data.get("gh_id", "")).strip()
    gh_login = str(token_data.get("gh_login", "")).strip()
    if not gh_id:
        raise HTTPException(status_code=400, detail="无效的 GitHub 授权标识")

    username = payload.username.strip().lower()
    password = payload.password.strip()

    stmt = select(User).where(User.username == username)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user or not user.is_active or not user.password_hash or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=400, detail="系统账号或密码验证失败。若无系统分配账号则无法登录。")

    id_stmt = select(OAuthIdentity).where(OAuthIdentity.issuer == GITHUB_OAUTH_ISSUER, OAuthIdentity.subject == gh_id)
    id_res = await db.execute(id_stmt)
    existing_identity = id_res.scalar_one_or_none()
    if existing_identity and existing_identity.user_id != user.id:
        raise HTTPException(status_code=409, detail="该 GitHub 账号已绑定至其他系统用户")

    if not existing_identity:
        db.add(OAuthIdentity(user_id=user.id, provider="github", issuer=GITHUB_OAUTH_ISSUER, subject=gh_id))

    if not user.oauth_provider:
        user.oauth_provider = "github"
        user.oauth_id = gh_id

    user.last_login_at = datetime.now(UTC)
    await db.commit()

    set_auth_cookie(response, user)
    return {"status": "ok", "message": f"成功将 GitHub (@{gh_login}) 与已有用户 [{user.username}] 关联并登录！"}


DEFAULT_SETTINGS = {
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

async def get_system_settings(db: AsyncSession) -> dict[str, str]:
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
    db: Annotated[AsyncSession, Depends(get_db)],
    sub_egress_session: Annotated[str | None, Cookie()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> User | None:
    """只接受本应用签发的会话，不信任客户端可伪造的身份头。"""
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

    return None


async def get_current_user(
    user: Annotated[User | None, Depends(get_current_user_optional)]
) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="请先登录后再进行操作")
    return user


async def get_current_admin(
    user: Annotated[User, Depends(get_current_user)]
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
    old_password: str | None = None
    new_password: str

@router.post("/api/auth/login", summary="用户账号密码登录")
async def auth_login(payload: LoginPayload, response: Response, db: Annotated[AsyncSession, Depends(get_db)]):
    u_str = payload.username
    p_str = payload.password

    # 规范拦截校验：严禁大写字母
    from .security import validate_username
    username_valid, username_error = validate_username(u_str)
    if not username_valid:
        raise HTTPException(status_code=400, detail=username_error)
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

    user.last_login_at = datetime.now(UTC)
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
async def auth_register(payload: RegisterPayload, response: Response, db: Annotated[AsyncSession, Depends(get_db)]):
    # 彻底关闭新用户自主注册功能
    raise HTTPException(
        status_code=403,
        detail="系统已关闭新用户自主注册功能，如需使用请联系系统管理员分配账号"
    )


@router.get("/api/auth/me", summary="获取当前登录用户信息")
async def auth_me(user: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
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
        "theme_mode": user.theme_mode,
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


@router.get("/api/auth/sso/start", summary="发起 Authentik SSO 认证或绑定流程")
async def auth_sso_start(request: Request, db: Annotated[AsyncSession, Depends(get_db)], mode: str = "login"):
    if mode not in {"login", "link"}:
        raise HTTPException(status_code=400, detail="SSO mode 无效")

    if mode == "link":
        local_user = await get_current_user_optional(request, db, request.cookies.get("sub_egress_session"))
        if not local_user:
            return RedirectResponse("/login?error=session_expired", status_code=302)
        callback_rd = "/api/auth/sso/callback?mode=link"
    else:
        callback_rd = "/api/auth/sso/callback"

    outpost_url = f"/outpost.goauthentik.io/start?rd={urllib.parse.quote(callback_rd)}"
    return RedirectResponse(outpost_url, status_code=302)


@router.get("/api/auth/sso/callback", summary="Authentik 第三方 SSO 回调处理与会话发放")
async def auth_sso_callback(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    mode: str = "login",
    x_authentik_username: Annotated[str | None, Header()] = None,
    x_authentik_email: Annotated[str | None, Header()] = None,
    x_forwarded_user: Annotated[str | None, Header()] = None,
    x_authentik_uid: Annotated[str | None, Header()] = None,
):
    sso_user = (x_authentik_username or x_forwarded_user or "").strip().lower()
    sso_subject = (x_authentik_uid or x_authentik_username or x_forwarded_user or "").strip()
    if not sso_user or not sso_subject:
        # 若未携带 SSO 鉴权身份头，说明未经反代鉴权或已被拦截
        target_error = "sso_unauthorized"
        if mode == "link":
            return RedirectResponse(url=f"/?error={target_error}", status_code=302)
        return RedirectResponse(url=f"/login?error={target_error}", status_code=302)

    # 绑定模式 (mode == "link")
    if mode == "link":
        current_user = await get_current_user_optional(request, db, request.cookies.get("sub_egress_session"))
        if not current_user or not current_user.is_active:
            return RedirectResponse(url="/login?error=session_expired", status_code=302)

        # 检查该 Authentik UID 是否已被其他系统用户占用
        existing_identity_res = await db.execute(
            select(OAuthIdentity).where(OAuthIdentity.issuer == "authentik", OAuthIdentity.subject == sso_subject)
        )
        existing_identity = existing_identity_res.scalar_one_or_none()
        if existing_identity and existing_identity.user_id != current_user.id:
            return RedirectResponse(url="/?error=authentik_already_linked", status_code=302)

        legacy_res = await db.execute(
            select(User).where(User.oauth_provider == "authentik", User.oauth_id == sso_user)
        )
        legacy_other = legacy_res.scalar_one_or_none()
        if legacy_other and legacy_other.id != current_user.id:
            return RedirectResponse(url="/?error=authentik_already_linked", status_code=302)

        if not existing_identity:
            db.add(OAuthIdentity(user_id=current_user.id, provider="authentik", issuer="authentik", subject=sso_subject))
        current_user.oauth_provider = "authentik"
        current_user.oauth_id = sso_user
        current_user.last_login_at = datetime.now(UTC)
        await db.commit()
        return RedirectResponse(url="/?msg=authentik_linked", status_code=302)

    # 登录模式 (mode == "login")
    identity_result = await db.execute(
        select(OAuthIdentity).where(OAuthIdentity.issuer == "authentik", OAuthIdentity.subject == sso_subject)
    )
    identity = identity_result.scalar_one_or_none()
    user = await db.get(User, identity.user_id) if identity else None
    if not user:
        legacy_result = await db.execute(
            select(User).where(User.oauth_provider == "authentik", User.oauth_id == sso_user)
        )
        user = legacy_result.scalar_one_or_none()

    # Create a separate account for a new provider subject; don't attach by username.
    if not user:
        token = secrets.token_hex(24)
        candidate = sso_user
        valid_username, _ = validate_username(candidate)
        if not valid_username:
            candidate = "user" + "".join(c for c in sso_subject.lower() if c.isalnum())[:15]
        existing_name = await db.execute(select(User.id).where(User.username == candidate))
        if existing_name.scalar_one_or_none():
            candidate = "user" + "".join(c for c in sso_subject.lower() if c.isalnum())[:15]
        user = User(
            username=candidate,
            role="user",
            is_active=True,
            sub_hash_token=token,
            subscription_title="sub-egress",
            oauth_provider="authentik",
            oauth_id=sso_user,
            clash_mixed_port="7897",
            clash_terminal_port="7898"
        )
        db.add(user)
        await db.flush()

    if not identity:
        db.add(OAuthIdentity(user_id=user.id, provider="authentik", issuer="authentik", subject=sso_subject))

    if not user.is_active:
        return RedirectResponse(url="/login?error=account_disabled", status_code=302)

    user.last_login_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(user)

    redirect_resp = RedirectResponse(url="/", status_code=302)
    set_auth_cookie(redirect_resp, user)
    return redirect_resp


@router.post("/api/auth/change-password", summary="当前用户修改密码")
async def auth_change_password(
    payload: ChangePasswordPayload,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
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
    name: str | None = "我的通行密钥"
    response: dict[str, Any]

class PasskeyLoginFinishPayload(BaseModel):
    id: str
    rawId: str
    type: str
    response: dict[str, Any]


def _webauthn_site(request: Request) -> tuple[str, str]:
    origin = os.getenv("WEBAUTHN_ORIGIN", "").strip().rstrip("/")
    parsed = urllib.parse.urlsplit(origin)
    if (not parsed.hostname or parsed.username or parsed.password or parsed.path
            or parsed.query or parsed.fragment
            or (parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname == "localhost"))):
        raise HTTPException(status_code=503, detail="请配置有效的 WEBAUTHN_ORIGIN 后使用通行密钥")
    if request.headers.get("host", "").lower() != parsed.netloc.lower():
        raise HTTPException(status_code=400, detail="请求域名与通行密钥配置不一致")
    return parsed.hostname, origin

@router.post("/api/auth/passkey/register/start", summary="发起通行密钥注册挑战")
async def passkey_register_start(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    # 硬限制：每个账号最多只允许绑定 5 个通行密钥
    count_stmt = select(func.count(PasskeyCredential.id)).where(PasskeyCredential.user_id == user.id)
    pk_count = (await db.execute(count_stmt)).scalar() or 0
    if pk_count >= 5:
        raise HTTPException(
            status_code=400,
            detail="每个账号最多只允许绑定 5 个通行密钥。请在安全中心解绑多余设备后再添加新密钥。"
        )

    host, _ = _webauthn_site(request)
    challenge = generate_challenge(f"reg:{user.id}", ttl_seconds=300)

    return {
        "challenge": challenge,
        "rp": {
            "name": "订阅调度 · sub-egress",
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
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    host, origin = _webauthn_site(request)
    reg_key = f"reg:{user.id}"
    
    # 获取之前缓存的 challenge
    stored = _get_stored_challenge(reg_key)
    if not stored:
        raise HTTPException(status_code=400, detail="通行密钥注册挑战已过期，请重试")

    client_data_b64 = payload.response.get("clientDataJSON")
    attestation_b64 = payload.response.get("attestationObject")
    if not client_data_b64 or not attestation_b64:
        raise HTTPException(status_code=400, detail="缺少 WebAuthn 注册凭证数据")
    if payload.type != "public-key" or payload.id != payload.rawId:
        raise HTTPException(status_code=400, detail="通行密钥凭证标识无效")

    try:
        cred_info = parse_and_verify_registration(
            client_data_json_b64=client_data_b64,
            attestation_obj_b64=attestation_b64,
            expected_challenge=stored,
            rp_id=host,
            expected_origin=origin,
        )
        if payload.id != cred_info["credential_id"]:
            raise ValueError("WebAuthn credential ID mismatch")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"通行密钥注册校验失败: {e}") from e

    # 消费 Challenge
    if not verify_and_consume_challenge(reg_key, stored):
        raise HTTPException(status_code=400, detail="通行密钥注册挑战已失效")

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
    response: Response,
    username: Annotated[str | None, Query()] = None
):
    host, origin = _webauthn_site(request)
    login_id = secrets.token_urlsafe(32)
    challenge = generate_challenge(f"login:{login_id}", ttl_seconds=300)
    response.set_cookie("webauthn_login", login_id, max_age=300, httponly=True,
                        secure=origin.startswith("https://"), samesite="strict",
                        path="/api/auth/passkey/login")

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
    db: Annotated[AsyncSession, Depends(get_db)],
    webauthn_login: Annotated[str | None, Cookie()] = None,
):
    host, origin = _webauthn_site(request)
    login_key = f"login:{webauthn_login}"
    stored = _get_stored_challenge(login_key) if webauthn_login else None
    if not stored:
        raise HTTPException(status_code=400, detail="登录挑战已失效或过期，请重新点击登录")

    client_data_b64 = payload.response.get("clientDataJSON")
    auth_data_b64 = payload.response.get("authenticatorData")
    sig_b64 = payload.response.get("signature")

    if not client_data_b64 or not auth_data_b64 or not sig_b64:
        raise HTTPException(status_code=400, detail="缺少通行密钥认证数据")
    if payload.type != "public-key" or payload.id != payload.rawId:
        raise HTTPException(status_code=400, detail="通行密钥凭证标识无效")

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
            expected_origin=origin,
            stored_sign_count=passkey.sign_count
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"通行密钥验签失败: {e}") from e

    # 消费 challenge
    if not verify_and_consume_challenge(login_key, stored):
        raise HTTPException(status_code=400, detail="登录挑战已失效")
    response.delete_cookie("webauthn_login", path="/api/auth/passkey/login")

    passkey.sign_count = new_sign_count
    passkey.last_used_at = datetime.now(UTC)
    user.last_login_at = datetime.now(UTC)
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


def _get_stored_challenge(key: str) -> str | None:
    from .auth_webauthn import _CHALLENGES
    item = _CHALLENGES.get(key)
    if item and item[1] > time.time():
        return item[0]
    return None


# ==================== 用户个人设置 API ====================

class UserSettingsPayload(BaseModel):
    theme_mode: Literal["system", "light", "dark"] | None = None
    subscription_title: str | None = None
    clash_mixed_port: str | None = None
    clash_terminal_port: str | None = None
    custom_direct_domains: str | None = None
    custom_proxy_domains: str | None = None
    custom_rules: str | None = None

@router.post("/api/user/settings", summary="保存当前用户专属订阅偏好")
async def update_user_settings(
    payload: UserSettingsPayload,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    if payload.theme_mode is not None:
        user.theme_mode = payload.theme_mode
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
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    new_token = secrets.token_hex(24)
    user.sub_hash_token = new_token
    await db.commit()
    return {"status": "ok", "new_token": new_token}


@router.get("/api/user/passkeys", summary="获取当前用户绑定的所有通行密钥")
async def list_user_passkeys(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
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
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
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
    provider: str | None = "authentik"
    oauth_id: str | None = None

class UnbindOAuthPayload(BaseModel):
    provider: str | None = "authentik"

@router.post("/api/user/unbind-oauth", summary="当前用户解绑第三方身份源")
async def user_unbind_oauth(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: UnbindOAuthPayload | None = None
):
    provider = ((payload and payload.provider) or "authentik").strip().lower()

    # 安全防自锁检查：若用户未设置本地密码且没有任何通行密钥，禁止解绑以防账号无法登录！
    if not user.password_hash:
        count_stmt = select(func.count(PasskeyCredential.id)).where(PasskeyCredential.user_id == user.id)
        pk_count = (await db.execute(count_stmt)).scalar() or 0
        if pk_count == 0:
            raise HTTPException(
                status_code=400,
                detail="为了您的账户安全，解绑第三方登录前请先设置登录密码或至少绑定一个通行密钥，以防账号无法登录。"
            )

    if user.oauth_provider == provider:
        user.oauth_provider = None
        user.oauth_id = None

    await db.execute(
        delete(OAuthIdentity).where(OAuthIdentity.user_id == user.id, OAuthIdentity.provider == provider)
    )
    await db.commit()
    return {"status": "ok", "message": "已成功解除第三方登录绑定"}


@router.post("/api/user/bind-oauth", summary="当前用户绑定第三方身份源")
async def user_bind_oauth(
    payload: BindOAuthPayload,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    x_authentik_username: Annotated[str | None, Header()] = None,
    x_authentik_uid: Annotated[str | None, Header()] = None,
    x_forwarded_user: Annotated[str | None, Header()] = None,
):
    provider = (payload.provider or "authentik").strip().lower()
    if provider == "authentik":
        sso_user = (x_authentik_username or x_forwarded_user or "").strip().lower()
        sso_subject = (x_authentik_uid or x_authentik_username or x_forwarded_user or "").strip()
        if not sso_user or not sso_subject:
            raise HTTPException(
                status_code=400,
                detail="未检测到有效的 Authentik 网关认证凭证，请点击【立即绑定】完成 Authentik 身份授权"
            )

        # 检查该 Authentik 账号是否已被其他用户绑定
        existing = await db.execute(
            select(OAuthIdentity).where(OAuthIdentity.issuer == "authentik", OAuthIdentity.subject == sso_subject)
        )
        identity = existing.scalar_one_or_none()
        if identity and identity.user_id != user.id:
            raise HTTPException(status_code=409, detail="该 Authentik 账号已绑定至其他系统用户")

        user.oauth_provider = provider
        user.oauth_id = sso_user
        if not identity:
            db.add(OAuthIdentity(user_id=user.id, provider=provider, issuer=provider, subject=sso_subject))
        await db.commit()
        return {"status": "ok", "message": f"已成功绑定 Authentik 账号 ({user.oauth_id})"}

    raise HTTPException(status_code=400, detail="不支持的第三方身份提供商")


@router.get("/api/user/identities", summary="列出当前账号已绑定身份")
async def user_list_identities(user: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(OAuthIdentity).where(OAuthIdentity.user_id == user.id).order_by(OAuthIdentity.id))
    identities = list(result.scalars().all())

    # 兼容历史数据：若 user.oauth_provider 存在但未在 OAuthIdentity 中建档，自动同步补齐
    if user.oauth_provider and user.oauth_id:
        has_provider = any(i.provider == user.oauth_provider for i in identities)
        if not has_provider:
            new_id = OAuthIdentity(
                user_id=user.id,
                provider=user.oauth_provider,
                issuer=user.oauth_provider,
                subject=user.oauth_id
            )
            db.add(new_id)
            await db.commit()
            await db.refresh(new_id)
            identities.append(new_id)

    return [
        {
            "id": identity.id,
            "provider": identity.provider,
            "issuer": identity.issuer,
            "subject": identity.subject,
            "created_at": identity.created_at.isoformat() if identity.created_at else None
        }
        for identity in identities
    ]


@router.delete("/api/user/identities/{identity_id}", summary="解绑当前账号的指定身份")
async def user_unlink_identity(identity_id: int, user: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(OAuthIdentity).where(OAuthIdentity.id == identity_id, OAuthIdentity.user_id == user.id))
    identity = result.scalar_one_or_none()
    if not identity:
        raise HTTPException(status_code=404, detail="身份绑定不存在")
    count = await db.scalar(select(func.count(OAuthIdentity.id)).where(OAuthIdentity.user_id == user.id))
    if count <= 1 and not user.password_hash:
        passkeys = await db.scalar(select(func.count(PasskeyCredential.id)).where(PasskeyCredential.user_id == user.id))
        if not passkeys:
            raise HTTPException(status_code=400, detail="请先设置密码或绑定其他通行密钥，再解绑最后一个登录身份")

    if user.oauth_provider == identity.provider:
        user.oauth_provider = None
        user.oauth_id = None

    provider_name = identity.provider
    await db.delete(identity)
    await db.commit()
    return {"status": "ok", "message": f"已成功解除 {provider_name} 绑定"}


# ==================== 管理员管理面板 API (独立页签与专属权限) ====================

class AdminResetPasswordPayload(BaseModel):
    new_password: str | None = None

class AdminCreateUserPayload(BaseModel):
    username: str
    password: str | None = None
    role: str = "user"

class AdminGlobalRulesPayload(BaseModel):
    admin_direct_domains: str = ""
    admin_proxy_domains: str = ""
    admin_rules: str = ""

class AdminGlobalSettingsPayload(BaseModel):
    require_token: bool
    default_target: str
    update_interval: int
    write_api_token: str | None = None

@router.get("/api/admin/settings", summary="读取管理员全局设置")
async def admin_get_settings(admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    settings = await get_system_settings(db)
    return {"require_token": settings.get("require_token", "false").lower() == "true", "default_target": settings.get("default_target", "clash"), "update_interval": settings.get("update_interval", "12"), "write_api_token_configured": bool(settings.get("write_api_token"))}

@router.put("/api/admin/settings", summary="更新管理员全局设置")
async def admin_put_settings(payload: AdminGlobalSettingsPayload, admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    if payload.default_target not in {"clash", "sing-box", "base64"} or not 1 <= payload.update_interval <= 72:
        raise HTTPException(status_code=400, detail="默认内核或更新间隔无效")
    values = {"require_token": "true" if payload.require_token else "false", "default_target": payload.default_target, "update_interval": str(payload.update_interval)}
    if payload.write_api_token is not None:
        values["write_api_token"] = payload.write_api_token.strip()
    for key, value in values.items():
        result = await db.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = value
        else:
            db.add(Setting(key=key, value=value))
    await db.commit()
    return {"status": "ok"}

@router.get("/api/admin/rules", summary="读取管理员全局规则")
async def admin_get_rules(admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    settings = await get_system_settings(db)
    return {key: settings.get(key, "") for key in ("admin_direct_domains", "admin_proxy_domains", "admin_rules")}

@router.put("/api/admin/rules", summary="更新管理员全局规则")
async def admin_put_rules(payload: AdminGlobalRulesPayload, admin: Annotated[User, Depends(get_current_admin)], db: Annotated[AsyncSession, Depends(get_db)]):
    for key, value in payload.model_dump().items():
        result = await db.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = value.strip()
        else:
            db.add(Setting(key=key, value=value.strip()))
    await db.commit()
    return {"status": "ok"}

@router.post("/api/admin/users", summary="管理员创建用户")
async def admin_create_user(
    payload: AdminCreateUserPayload,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    valid, message = validate_username(payload.username)
    if not valid:
        raise HTTPException(status_code=400, detail=message)
    if payload.role not in {"user", "admin"}:
        raise HTTPException(status_code=400, detail="角色只能是 user 或 admin")
    password = payload.password or generate_secure_password(32)
    valid, message = validate_password(password)
    if not valid:
        raise HTTPException(status_code=400, detail=message)
    existing = await db.execute(select(User).where(User.username == payload.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="用户名已存在")
    user = User(
        username=payload.username,
        password_hash=hash_password(password),
        role=payload.role,
        is_active=True,
        sub_hash_token=secrets.token_hex(24),
        subscription_title="sub-egress",
        clash_mixed_port="7897",
        clash_terminal_port="7898",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"id": user.id, "username": user.username, "role": user.role, "initial_password": password}

@router.get("/api/admin/users", summary="管理员查看全量用户列表")
async def admin_list_users(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    stmt = select(User).options(selectinload(User.passkeys), selectinload(User.identities)).order_by(User.id)
    res = await db.execute(stmt)
    users = res.scalars().all()

    results = []
    for u in users:
        # 获取所有已绑定的第三方外部身份
        user_identities = [
            {
                "id": i.id,
                "provider": i.provider,
                "subject": i.subject,
                "issuer": i.issuer,
                "created_at": i.created_at.isoformat() if i.created_at else None,
            }
            for i in u.identities
        ]
        # 兼容历史数据：若 u.oauth_provider 存在但未在 identities 中建档，平滑合并展示
        providers_set = {i.provider for i in u.identities}
        if u.oauth_provider and u.oauth_provider not in providers_set:
            providers_set.add(u.oauth_provider)
            user_identities.append({
                "id": 0,
                "provider": u.oauth_provider,
                "subject": u.oauth_id or u.username,
                "issuer": u.oauth_provider,
                "created_at": None,
            })

        effective_provider = ", ".join(sorted(providers_set)) if providers_set else None

        results.append({
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "is_active": u.is_active,
            "sub_hash_token": u.sub_hash_token,
            "subscription_title": u.subscription_title,
            "clash_mixed_port": u.clash_mixed_port,
            "clash_terminal_port": u.clash_terminal_port,
            "oauth_provider": effective_provider,
            "oauth_id": u.oauth_id or (u.identities[0].subject if u.identities else None),
            "identities": user_identities,
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
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
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
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
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
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
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
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
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
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    stmt = select(User).where(User.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.oauth_provider = None
    user.oauth_id = None
    await db.execute(delete(OAuthIdentity).where(OAuthIdentity.user_id == user.id))
    await db.commit()
    return {"status": "ok", "message": f"用户 {user.username} 的第三方授权已解除"}


# ==================== 管理员平台共享源管控 API ====================

class SourceCreate(BaseModel):
    name: str
    url: str
    source_type: str | None = "auto"
    raw_content: str | None = None
    is_shared: bool | None = False

class SourceUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    enabled: bool | None = None
    raw_content: str | None = None
    is_shared: bool | None = None

@router.get("/api/admin/sources", summary="管理员获取平台共享源与全量源列表")
async def admin_list_sources(
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    scope: str = "shared"  # "shared" 或 "all"
):
    creator = aliased(User)
    if scope == "all":
        stmt = (
            select(Source, User.username, creator.username)
            .outerjoin(User, Source.owner_user_id == User.id)
            .outerjoin(creator, Source.created_by_user_id == creator.id)
            .order_by(Source.is_shared.desc(), Source.id)
        )
        res = await db.execute(stmt)
        rows = res.all()
        results = []
        for s, uname, creator_name in rows:
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
                "owner_user_id": s.owner_user_id,
                "created_by_user_id": s.created_by_user_id,
                "creator_username": creator_name,
                "owner_username": uname or ("系统平台共享" if s.is_shared else "未知用户"),
                "can_edit": bool(s.is_shared),
                "can_manage": bool(s.is_shared),
                "expire_at": s.expire_at.isoformat() if s.expire_at else None,
                "last_sync_at": s.last_sync_at.isoformat() if s.last_sync_at else None,
                "reset_info": extra.get("reset_info"),
                "remaining_text": extra.get("remaining_text")
            })
        return results
    else:
        stmt = select(Source, creator.username).outerjoin(creator, Source.created_by_user_id == creator.id).where(Source.is_shared.is_(True)).order_by(Source.id)
        res = await db.execute(stmt)
        results = []
        for s, creator_name in res.all():
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
                "is_shared": True,
                "owner_user_id": s.owner_user_id,
                "created_by_user_id": s.created_by_user_id,
                "creator_username": creator_name,
                "owner_username": "平台共享",
                "can_manage": True,
                "expire_at": s.expire_at.isoformat() if s.expire_at else None,
                "last_sync_at": s.last_sync_at.isoformat() if s.last_sync_at else None,
                "reset_info": extra.get("reset_info"),
                "remaining_text": extra.get("remaining_text")
            })
        return results

@router.post("/api/admin/sources", summary="管理员创建平台共享源")
async def admin_create_source(
    payload: SourceCreate,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    src = Source(
        owner_user_id=None,
        created_by_user_id=admin.id,
        is_shared=True,
        name=payload.name.strip(),
        url=payload.url.strip(),
        source_type=payload.source_type or "auto",
        raw_content=payload.raw_content
    )
    db.add(src)
    await db.commit()
    await db.refresh(src)
    await sync_single_source(src.id, db)
    return {"status": "success", "id": src.id}

@router.put("/api/admin/sources/{source_id}", summary="管理员编辑共享源")
async def admin_update_source(
    source_id: int,
    payload: SourceUpdate,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    stmt = select(Source).where(Source.id == source_id)
    res = await db.execute(stmt)
    src = res.scalar_one_or_none()
    if not src:
        raise HTTPException(status_code=404, detail="Source not found")

    # 隐私保护铁律：管理员无权编辑租户的私有订阅源（涉及租户个人隐私）。私有源绝不可转化为公共源；若违规仅支持删除或刷新。
    if not src.is_shared:
        raise HTTPException(
            status_code=403,
            detail="管理员无权编辑租户私有订阅源（保护租户数据隐私）。私有源绝不可转化为公共源；若违规仅支持删除或刷新。"
        )

    if payload.is_shared is not None and not payload.is_shared:
        raise HTTPException(status_code=400, detail="平台共享源不可擅自变更为私有源")

    if payload.name is not None:
        src.name = payload.name.strip()
    if payload.url is not None:
        src.url = payload.url.strip()
    if payload.enabled is not None:
        src.enabled = payload.enabled
    if payload.raw_content is not None:
        src.raw_content = payload.raw_content

    await db.commit()
    await sync_single_source(src.id, db)
    return {"status": "success"}

@router.delete("/api/admin/sources/{source_id}", summary="管理员删除共享源")
async def admin_delete_source(
    source_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    stmt = select(Source).where(Source.id == source_id)
    res = await db.execute(stmt)
    src = res.scalar_one_or_none()
    if not src:
        raise HTTPException(status_code=404, detail="Source not found")

    await db.execute(delete(Source).where(Source.id == source_id))
    await db.commit()
    return {"status": "success"}

@router.post("/api/admin/sources/{source_id}/refresh", summary="管理员手动刷新共享源")
async def admin_refresh_source(
    source_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    stmt = select(Source).where(Source.id == source_id)
    res = await db.execute(stmt)
    src = res.scalar_one_or_none()
    if not src:
        raise HTTPException(status_code=404, detail="Source not found")

    success = await sync_single_source(source_id, db)
    if not success:
        res = await db.execute(stmt)
        src = res.scalar_one_or_none()
        err = src.error_message if src else "Unknown error"
        raise HTTPException(status_code=500, detail=f"Refresh failed: {err}")
    return {"status": "success"}


# ==================== 下游订阅分发端点 (多用户订阅隔离与客户端直连) ====================

@router.head("/c/{token}", include_in_schema=False)
@router.head("/feed", include_in_schema=False)
@router.get("/c/{token}", summary="基于专属安全令牌的统一订阅调度端点")
@router.get("/feed", summary="标准统一订阅调度端点")
async def export_subscription(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    token: str | None = None,
    target: Annotated[str | None, Query(description="目标客户端内核: clash, sing-box, base64")] = None,
    type: Annotated[str | None, Query(description="别名目标内核: clash, sing-box, base64")] = None,
    name: Annotated[str | None, Query(description="自定义订阅卡片名称 (显示在客户端)")] = None,
    title: Annotated[str | None, Query(description="自定义订阅卡片名称 (别名)")] = None,
    t: Annotated[str | None, Query(description="Query 传递的安全令牌 (用于 /feed)")] = None,
):
    settings = await get_system_settings(db)
    req_token = token or t

    # 1. 根据专属 Token 查找对应用户 (实现多用户资源隔离)
    matched_user: User | None = None
    if req_token:
        u_stmt = select(User).where(User.sub_hash_token == req_token)
        u_res = await db.execute(u_stmt)
        matched_user = u_res.scalar_one_or_none()

    # 读权限安全检查
    if req_token or settings.get("require_token", "false").lower() == "true":
        if not matched_user:
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

    # 多租户节点源过滤：提取公共共享源（排除用户个人禁用的共享源）+ 用户私有源
    stmt = (
        select(Node, Source.name.label("source_name"))
        .join(Source, Node.source_id == Source.id)
        .where(Source.enabled.is_(True))
    )
    if matched_user:
        disabled_shared = matched_user.get_disabled_shared_source_ids()
        if disabled_shared:
            stmt = stmt.where(
                ((Source.is_shared.is_(True)) & (~Source.id.in_(disabled_shared)))
                | ((Source.is_shared.is_(False)) & (Source.owner_user_id == matched_user.id))
            )
        else:
            stmt = stmt.where((Source.is_shared.is_(True)) | ((Source.is_shared.is_(False)) & (Source.owner_user_id == matched_user.id)))
    else:
        stmt = stmt.where(Source.is_shared.is_(True))

    stmt = stmt.order_by(Node.country_code, Node.id)
    result = await db.execute(stmt)
    rows = result.all()

    nodes_list = []
    for node, source_name in rows:
        cfg = dict(node.config_json)
        cfg["source_name"] = source_name
        cfg["display_name"] = node.display_name
        cfg["country_code"] = node.country_code
        cfg["is_residential"] = node.is_residential
        nodes_list.append(cfg)

    # 计算总流量与到期时间
    src_stmt = select(Source).where(Source.enabled.is_(True))
    if matched_user:
        src_stmt = src_stmt.where(
            ((Source.is_shared.is_(True)) & (~Source.id.in_(matched_user.get_disabled_shared_source_ids())))
            | ((Source.is_shared.is_(False)) & (Source.owner_user_id == matched_user.id))
        )
    else:
        src_stmt = src_stmt.where(Source.is_shared.is_(True))

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
    direct_domains = [d.strip() for d in (settings.get("admin_direct_domains", "") + "," + (user_direct_raw or "")).replace("\n", ",").replace(";", ",").split(",") if d.strip()]

    user_proxy_raw = (
        matched_user.custom_proxy_domains
        if (matched_user and matched_user.custom_proxy_domains is not None)
        else settings.get("custom_proxy_domains", "")
    )
    proxy_domains = [d.strip() for d in (settings.get("admin_proxy_domains", "") + "," + (user_proxy_raw or "")).replace("\n", ",").replace(";", ",").split(",") if d.strip()]

    user_rules_raw = (
        matched_user.custom_rules
        if (matched_user and matched_user.custom_rules is not None)
        else settings.get("custom_rules", "")
    )
    custom_rules_list = [r.strip() for r in (settings.get("admin_rules", "") + "\n" + (user_rules_raw or "")).splitlines() if r.strip() and not r.strip().startswith("#")]

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
        content = build_singbox_config(
            nodes_list,
            custom_direct_domains=direct_domains,
            custom_proxy_domains=proxy_domains,
            custom_rules=custom_rules_list,
        )
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
    sub_hash_token: str | None = None
    require_token: bool | None = None
    default_target: str | None = None
    update_interval: str | None = None
    write_api_token: str | None = None
    subscription_title: str | None = None
    clash_mixed_port: str | None = None
    clash_terminal_port: str | None = None
    custom_direct_domains: str | None = None
    custom_proxy_domains: str | None = None
    custom_rules: str | None = None

@router.get("/api/settings", summary="获取当前用户设置")
async def get_settings(user: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]):
    settings = await get_system_settings(db)
    # 若有当前用户，返回该用户专有端口、标题与分流规则
    sub_title = user.subscription_title
    m_port = user.clash_mixed_port
    t_port = user.clash_terminal_port
    u_token = user.sub_hash_token
    direct_domains = (
        user.custom_direct_domains
        if user.custom_direct_domains is not None
        else settings.get("custom_direct_domains", "ying-qing.cn")
    )
    proxy_domains = (
        user.custom_proxy_domains
        if user.custom_proxy_domains is not None
        else settings.get("custom_proxy_domains", "")
    )
    custom_rules = (
        user.custom_rules
        if user.custom_rules is not None
        else settings.get("custom_rules", "")
    )

    return {
        "version": VERSION,
        "sub_hash_token": u_token,
        "require_token": settings.get("require_token", "false").lower() == "true",
        "default_target": settings.get("default_target", "clash"),
        "update_interval": settings.get("update_interval", "12"),
        "write_api_token": "",
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
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    updates = {}
    if any(value is not None for value in (payload.require_token, payload.default_target, payload.update_interval, payload.write_api_token)):
        raise HTTPException(status_code=403, detail="全局安全设置仅管理员可修改")
    if payload.sub_hash_token is not None:
        raise HTTPException(status_code=400, detail="订阅令牌由系统随机生成，请使用重置接口")
    if payload.subscription_title is not None:
        updates["subscription_title"] = payload.subscription_title.strip()
        user.subscription_title = payload.subscription_title.strip()
    if payload.clash_mixed_port is not None:
        updates["clash_mixed_port"] = str(payload.clash_mixed_port).strip()
        user.clash_mixed_port = str(payload.clash_mixed_port).strip()
    if payload.clash_terminal_port is not None:
        updates["clash_terminal_port"] = str(payload.clash_terminal_port).strip()
        user.clash_terminal_port = str(payload.clash_terminal_port).strip()
    if payload.custom_direct_domains is not None:
        updates["custom_direct_domains"] = payload.custom_direct_domains.strip()
        user.custom_direct_domains = payload.custom_direct_domains.strip()
    if payload.custom_proxy_domains is not None:
        updates["custom_proxy_domains"] = payload.custom_proxy_domains.strip()
        user.custom_proxy_domains = payload.custom_proxy_domains.strip()
    if payload.custom_rules is not None:
        updates["custom_rules"] = payload.custom_rules.strip()
        user.custom_rules = payload.custom_rules.strip()

    await db.commit()
    return {"status": "success", "message": "Settings updated"}


@router.post("/api/settings/regenerate-token", summary="重新生成安全哈希令牌")
async def regenerate_token(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    new_token = secrets.token_hex(24)
    user.sub_hash_token = new_token
    await db.commit()
    return {"status": "success", "new_token": new_token}


# ==================== 用户端点：上游节点源管理 API (供首页用户仪表盘) ====================

class ProbeSourcePayload(BaseModel):
    url: str

@router.post("/api/sources/probe", summary="智能探测订阅链接名称与节点信息")
async def probe_subscription_source(
    payload: ProbeSourcePayload,
    user: Annotated[User, Depends(get_current_user)],
):
    url = (payload.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="订阅 URL 不能为空")

    suggested_name = ""
    node_count = 0
    source_type = "auto"
    traffic_used = 0
    traffic_total = 0

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": DEFAULT_UA})
            if resp.status_code == 200:
                # 1. 尝试从 Profile-Title 响应头解析
                pt = resp.headers.get("profile-title") or resp.headers.get("Profile-Title")
                if pt:
                    pt = pt.strip()
                    if pt.startswith("base64:"):
                        try:
                            suggested_name = base64.b64decode(pt[7:]).decode("utf-8", errors="ignore").strip()
                        except Exception as exc:
                            logger.debug("Failed to decode base64 profile-title: %s", exc)
                    else:
                        suggested_name = urllib.parse.unquote(pt).strip()

                # 2. 尝试从 Content-Disposition 响应头解析
                if not suggested_name:
                    cd = resp.headers.get("content-disposition") or resp.headers.get("Content-Disposition")
                    if cd:
                        m_utf8 = re.search(r"filename\*=UTF-8''([^;]+)", cd, re.IGNORECASE)
                        if m_utf8:
                            suggested_name = urllib.parse.unquote(m_utf8.group(1)).strip()
                        else:
                            m_std = re.search(r'filename="?([^";]+)"?', cd)
                            if m_std:
                                suggested_name = urllib.parse.unquote(m_std.group(1)).strip()

                # 3. 提取流量信息
                userinfo_header = resp.headers.get("subscription-userinfo") or resp.headers.get("Subscription-Userinfo")
                if userinfo_header:
                    uinfo = parse_userinfo_header(userinfo_header)
                    traffic_used = (uinfo.get("upload") or 0) + (uinfo.get("download") or 0)
                    traffic_total = uinfo.get("total") or 0

                # 4. 解析节点数量与格式
                content = resp.text
                nodes = parse_clash_yaml(content)
                if nodes:
                    source_type = "clash"
                else:
                    nodes = parse_singbox_json(content)
                    if nodes:
                        source_type = "singbox"
                    else:
                        nodes = parse_subscription_text(content)
                        if nodes:
                            source_type = "uri"
                node_count = len(nodes)

    except Exception as exc:
        logger.debug("Probe subscription failed: %s", exc)

    # 5. 若无响应头名称，从 URL 域名提取友好默认名称
    if not suggested_name:
        parsed_url = urllib.parse.urlparse(url)
        host = parsed_url.hostname or ""
        parts = [p.upper() for p in host.split(".") if p.lower() not in ("com", "net", "org", "cc", "cn", "io", "sub", "api", "www")]
        if parts:
            suggested_name = parts[0]
        else:
            suggested_name = "我的订阅源"

    return {
        "success": True,
        "suggested_name": suggested_name,
        "node_count": node_count,
        "source_type": source_type,
        "traffic_used": traffic_used,
        "traffic_total": traffic_total
    }

@router.get("/api/sources", summary="获取当前用户可用上游源列表")
async def list_sources(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    creator = aliased(User)
    stmt = (
        select(Source, creator.username)
        .outerjoin(creator, Source.created_by_user_id == creator.id)
        .where(
            ((Source.is_shared.is_(True)) & (Source.enabled.is_(True)))
            | ((Source.is_shared.is_(False)) & (Source.owner_user_id == user.id))
        )
        .order_by(Source.id)
    )
    res = await db.execute(stmt)
    disabled_ids = user.get_disabled_shared_source_ids()
    results = []
    for s, creator_name in res.all():
        extra = extract_subscription_extra_info(s.raw_content or "")
        is_shared = bool(s.is_shared)
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
            "is_shared": is_shared,
            "owner_user_id": s.owner_user_id,
            "created_by_user_id": s.created_by_user_id,
            "creator_username": creator_name,
            "owner_username": "平台" if is_shared else user.username,
            # 在用户页面上：平台公共共享源绝对不可删除与编辑！即便当前登录的是管理员也严格作为普通用户对待！
            "can_manage": False if is_shared else (s.owner_user_id == user.id),
            "is_enabled_for_user": (s.id not in disabled_ids) if is_shared else bool(s.enabled),
            "expire_at": s.expire_at.isoformat() if s.expire_at else None,
            "last_sync_at": s.last_sync_at.isoformat() if s.last_sync_at else None,
            "reset_info": extra.get("reset_info"),
            "remaining_text": extra.get("remaining_text")
        })
    return results

@router.post("/api/user/shared-sources/{source_id}/toggle", summary="用户个人级启用或禁用平台共享源")
async def toggle_shared_source_for_user(
    source_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    src = await db.get(Source, source_id)
    if not src or not src.is_shared or not src.enabled:
        raise HTTPException(status_code=404, detail="平台共享源不存在")

    disabled_ids = user.get_disabled_shared_source_ids()
    if source_id in disabled_ids:
        disabled_ids.remove(source_id)
        is_enabled = True
    else:
        disabled_ids.add(source_id)
        is_enabled = False

    user.disabled_shared_sources = ",".join(str(i) for i in sorted(disabled_ids))
    await db.commit()
    return {
        "status": "success",
        "source_id": source_id,
        "is_enabled_for_user": is_enabled,
        "disabled_source_ids": list(disabled_ids)
    }

@router.post("/api/sources", summary="用户新增个人私有节点源")
async def create_source(
    payload: SourceCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    # 用户首页添加的源永远属于该用户专属私有，禁止任何用户在用户页直接添加共享源
    src = Source(
        owner_user_id=user.id,
        created_by_user_id=user.id,
        is_shared=False,
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

@router.put("/api/sources/{source_id}", summary="用户编辑个人私有节点源")
async def update_source(
    source_id: int,
    payload: SourceUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    stmt = select(Source).where(Source.id == source_id)
    res = await db.execute(stmt)
    src = res.scalar_one_or_none()
    if not src:
        raise HTTPException(status_code=404, detail="Source not found")

    if src.is_shared:
        raise HTTPException(status_code=403, detail="平台共享源需在管理员控制台中编辑维护")

    if src.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="无权修改他人所属的私有节点源")

    if payload.name is not None:
        src.name = payload.name.strip()
    if payload.url is not None:
        src.url = payload.url.strip()
    if payload.enabled is not None:
        src.enabled = payload.enabled
    if payload.raw_content is not None:
        src.raw_content = payload.raw_content

    await db.commit()
    await sync_single_source(src.id, db)
    return {"status": "success"}

@router.delete("/api/sources/{source_id}", summary="用户删除个人私有节点源")
async def delete_source(
    source_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    stmt = select(Source).where(Source.id == source_id)
    res = await db.execute(stmt)
    src = res.scalar_one_or_none()
    if not src:
        raise HTTPException(status_code=404, detail="Source not found")

    if src.is_shared:
        raise HTTPException(status_code=403, detail="平台公共共享源不可在个人视图中删除，如需下线请前往管理员控制台")

    if src.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="无权删除他人所属的私有节点源")

    await db.execute(delete(Source).where(Source.id == source_id))
    await db.commit()
    return {"status": "success"}

@router.post("/api/sources/{source_id}/refresh", summary="手动刷新指定个人节点源")
async def refresh_source(
    source_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    stmt = select(Source).where(Source.id == source_id)
    res = await db.execute(stmt)
    src = res.scalar_one_or_none()
    if not src:
        raise HTTPException(status_code=404, detail="Source not found")

    if src.is_shared:
        raise HTTPException(status_code=403, detail="平台共享源由系统自动调度同步，普通用户无法单独刷新全站公共源")

    if src.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="无权刷新他人所属的私有节点源")

    success = await sync_single_source(source_id, db)
    if not success:
        res = await db.execute(stmt)
        src = res.scalar_one_or_none()
        err = src.error_message if src else "Unknown error"
        raise HTTPException(status_code=500, detail=f"Refresh failed: {err}")
    return {"status": "success"}


# ==================== 节点与动态策略组大盘 API ====================

@router.get("/api/nodes", summary="获取平铺节点池与动态策略组")
async def list_nodes(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    disabled_shared = user.get_disabled_shared_source_ids()
    stmt = (
        select(Node, Source.name.label("source_name"))
        .join(Source, Node.source_id == Source.id)
        .where(Source.enabled.is_(True))
    )
    if disabled_shared:
        stmt = stmt.where(
            ((Source.is_shared.is_(True)) & (~Source.id.in_(disabled_shared)))
            | ((Source.is_shared.is_(False)) & (Source.owner_user_id == user.id))
        )
    else:
        stmt = stmt.where((Source.is_shared.is_(True)) | ((Source.is_shared.is_(False)) & (Source.owner_user_id == user.id)))
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
    node_ids: list[int] | None = None

@router.post("/api/nodes/{node_id}/ping", summary="测试单个节点网络握手延迟")
async def ping_node_endpoint(
    node_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    stmt = (
        select(Node)
        .join(Source, Node.source_id == Source.id)
        .where(Node.id == node_id, Source.enabled.is_(True))
        .where(
            ((Source.is_shared.is_(True)) & (~Source.id.in_(user.get_disabled_shared_source_ids())))
            | ((Source.is_shared.is_(False)) & (Source.owner_user_id == user.id))
        )
    )
    res = await db.execute(stmt)
    node = res.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    result = await ping_single_node(node.server, node.port, node.node_type)
    node.latency = result["latency"]
    node.latency_status = result["status"]
    node.latency_updated_at = datetime.now(UTC)
    await db.commit()

    return {
        "node_id": node.id,
        "display_name": node.display_name,
        "server": node.server,
        "port": node.port,
        **result
    }

@router.post("/api/nodes/ping", summary="批量并发测试节点延迟")
async def batch_ping_nodes(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: BatchPingPayload | None = None
):
    disabled_shared = user.get_disabled_shared_source_ids()
    stmt = (
        select(Node)
        .join(Source, Node.source_id == Source.id)
        .where(Source.enabled.is_(True))
    )
    if disabled_shared:
        stmt = stmt.where(
            ((Source.is_shared.is_(True)) & (~Source.id.in_(disabled_shared)))
            | ((Source.is_shared.is_(False)) & (Source.owner_user_id == user.id))
        )
    else:
        stmt = stmt.where((Source.is_shared.is_(True)) | ((Source.is_shared.is_(False)) & (Source.owner_user_id == user.id)))
    if payload and payload.node_ids:
        stmt = stmt.where(Node.id.in_(payload.node_ids))
    res = await db.execute(stmt)
    nodes = res.scalars().all()

    sem = asyncio.Semaphore(20)

    async def worker(node: Node):
        async with sem:
            res = await ping_single_node(node.server, node.port, node.node_type, timeout=2.5)
            return node.id, res

    tasks = [worker(n) for n in nodes]
    results = await asyncio.gather(*tasks)
    now = datetime.now(UTC)
    for nid, ping_res in results:
        await db.execute(
            update(Node)
            .where(Node.id == nid)
            .values(
                latency=ping_res["latency"],
                latency_status=ping_res["status"],
                latency_updated_at=now
            )
        )
    await db.commit()

    return {
        "total": len(results),
        "results": {str(nid): ping_res for nid, ping_res in results}
    }

@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "sub-egress", "version": VERSION, "timestamp": datetime.now(UTC).isoformat()}

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
