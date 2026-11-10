from contextlib import asynccontextmanager

import pytest
from app.api import (
    BindOAuthPayload,
    user_bind_oauth,
    user_list_identities,
    user_unlink_identity,
)
from app.models import Base, OAuthIdentity, User
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@asynccontextmanager
async def create_test_env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            # 用户 1: admin (已设置密码)
            admin = User(
                id=1,
                username="admin",
                role="admin",
                sub_hash_token="admin-token",
                password_hash="pbkdf2:sha256:200000$fakepasswordhash",
                is_active=True,
            )
            # 用户 2: pkman (普通用户，有密码，无 Authentik 账号)
            pkman = User(
                id=2,
                username="pkman",
                role="user",
                sub_hash_token="pkman-token",
                password_hash="pbkdf2:sha256:200000$fakepasswordhash",
                is_active=True,
            )
            # 用户 3: bob (已绑定 authentik 账号 uid: "authentik-uid-bob")
            bob = User(
                id=3,
                username="bob",
                role="user",
                sub_hash_token="bob-token",
                password_hash="pbkdf2:sha256:200000$fakepasswordhash",
                oauth_provider="authentik",
                oauth_id="bob_sso",
                is_active=True,
            )
            session.add_all([admin, pkman, bob])
            session.add(
                OAuthIdentity(
                    id=1,
                    user_id=3,
                    provider="authentik",
                    issuer="authentik",
                    subject="authentik-uid-bob",
                )
            )
            await session.commit()
        yield session_factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_prevent_fake_authentik_binding_without_headers():
    """验证安全修复：若未携带真实的 Authentik 网关认证头，严禁将本地用户名默认绑定为 Authentik 账号！"""
    async with create_test_env() as session_factory:
        async with session_factory() as session:
            pkman = await session.get(User, 2)
            payload = BindOAuthPayload(provider="authentik")

            # 模拟在普通网络环境下（无 Authentik 请求头）发起的绑定请求
            with pytest.raises(HTTPException) as exc_info:
                await user_bind_oauth(
                    payload=payload,
                    user=pkman,
                    db=session,
                    x_authentik_username=None,
                    x_authentik_uid=None,
                    x_forwarded_user=None,
                )

            assert exc_info.value.status_code == 400
            assert "未检测到有效的 Authentik 网关认证凭证" in exc_info.value.detail

            # 确保数据库没有被伪造篡改
            assert pkman.oauth_provider is None
            assert pkman.oauth_id is None


@pytest.mark.asyncio
async def test_valid_authentik_binding_with_gateway_headers():
    """验证携带真实 Authentik 网关认证头时，能够正常绑定，并同步更新 User 与 OAuthIdentity 表"""
    async with create_test_env() as session_factory:
        async with session_factory() as session:
            pkman = await session.get(User, 2)
            payload = BindOAuthPayload(provider="authentik")

            result = await user_bind_oauth(
                payload=payload,
                user=pkman,
                db=session,
                x_authentik_username="pkman_real_sso",
                x_authentik_uid="authentik-uid-pkman-999",
                x_forwarded_user="pkman_real_sso",
            )

            assert result["status"] == "ok"
            assert pkman.oauth_provider == "authentik"
            assert pkman.oauth_id == "pkman_real_sso"

            # 验证 OAuthIdentity 存在
            identities = await user_list_identities(user=pkman, db=session)
            assert len(identities) == 1
            assert identities[0]["provider"] == "authentik"
            assert identities[0]["subject"] == "authentik-uid-pkman-999"


@pytest.mark.asyncio
async def test_reject_binding_when_authentik_subject_already_taken():
    """验证安全约束：当 Authentik 账号已被其他用户绑定时，返回 409 拒绝绑定冲突"""
    async with create_test_env() as session_factory:
        async with session_factory() as session:
            pkman = await session.get(User, 2)
            payload = BindOAuthPayload(provider="authentik")

            # 试图绑定已经被 bob 绑定的 UID: "authentik-uid-bob"
            with pytest.raises(HTTPException) as exc_info:
                await user_bind_oauth(
                    payload=payload,
                    user=pkman,
                    db=session,
                    x_authentik_username="bob_sso",
                    x_authentik_uid="authentik-uid-bob",
                    x_forwarded_user="bob_sso",
                )

            assert exc_info.value.status_code == 409
            assert "已绑定至其他系统用户" in exc_info.value.detail


@pytest.mark.asyncio
async def test_user_list_identities_returns_subject_and_migrates_legacy():
    """验证列表接口返回中包含 subject 字段（修复前端渲染为空的问题），并兼容补齐 legacy 数据"""
    async with create_test_env() as session_factory:
        async with session_factory() as session:
            # 创建一个只有 legacy oauth 字段但无 OAuthIdentity 的用户
            legacy_user = User(
                id=4,
                username="legacyuser",
                role="user",
                sub_hash_token="legacy-token",
                password_hash="pbkdf2:sha256:200000$fakepasswordhash",
                oauth_provider="authentik",
                oauth_id="legacy_sso_id",
                is_active=True,
            )
            session.add(legacy_user)
            await session.commit()

            identities = await user_list_identities(user=legacy_user, db=session)
            assert len(identities) == 1
            assert identities[0]["provider"] == "authentik"
            # 关键：检查 subject 字段存在且非空
            assert identities[0]["subject"] == "legacy_sso_id"
            assert identities[0]["id"] is not None


@pytest.mark.asyncio
async def test_user_unlink_identity_cleans_both_tables():
    """验证解绑身份时，同步清理 OAuthIdentity 与 User.oauth_provider 字段"""
    async with create_test_env() as session_factory:
        async with session_factory() as session:
            bob = await session.get(User, 3)
            identities = await user_list_identities(user=bob, db=session)
            identity_id = identities[0]["id"]

            res = await user_unlink_identity(identity_id=identity_id, user=bob, db=session)
            assert res["status"] == "ok"

            # 验证两表均已清理
            assert bob.oauth_provider is None
            assert bob.oauth_id is None
            identities_after = await user_list_identities(user=bob, db=session)
            assert len(identities_after) == 0


@pytest.mark.asyncio
async def test_prevent_unlinking_last_login_method_when_no_password():
    """验证安全防自锁：若用户没有本地密码且没有通行密钥，禁止解绑唯一的外部身份"""
    async with create_test_env() as session_factory:
        async with session_factory() as session:
            oauth_only_user = User(
                id=5,
                username="nopassuser",
                role="user",
                sub_hash_token="nopass-token",
                password_hash=None,  # 无密码
                oauth_provider="authentik",
                oauth_id="nopass_sso",
                is_active=True,
            )
            session.add(oauth_only_user)
            id_entry = OAuthIdentity(
                id=50,
                user_id=5,
                provider="authentik",
                issuer="authentik",
                subject="nopass_sso_sub",
            )
            session.add(id_entry)
            await session.commit()

            with pytest.raises(HTTPException) as exc_info:
                await user_unlink_identity(identity_id=50, user=oauth_only_user, db=session)

            assert exc_info.value.status_code == 400
            assert "请先设置密码或绑定其他通行密钥" in exc_info.value.detail
