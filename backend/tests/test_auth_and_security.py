try:
    import pytest
except ImportError:
    pytest = None

from app.auth_webauthn import (
    generate_challenge,
    verify_and_consume_challenge,
)
from app.security import (
    create_session_token,
    generate_secure_password,
    hash_password,
    validate_password,
    validate_username,
    verify_password,
    verify_session_token,
)


def test_validate_username():
    # 正常小写字母与数字
    ok, msg = validate_username("admin")
    assert ok, msg
    ok, msg = validate_username("user-01")
    assert ok, msg
    ok, msg = validate_username("test_user_99")
    assert ok, msg

    # 严禁大写字母
    ok, msg = validate_username("Admin")
    assert not ok
    assert "大写字母" in msg

    ok, msg = validate_username("UserABC")
    assert not ok
    assert "大写字母" in msg

    # 长度限制 (5~20)
    ok, msg = validate_username("abc")
    assert not ok
    assert "5 到 20" in msg

    ok, msg = validate_username("a" * 21)
    assert not ok
    assert "5 到 20" in msg


def test_validate_password():
    # 20 位以上且不含大写字母即可；字符类型无需强制组合。
    valid_pwd = "my-super-secret-password-12345"
    ok, msg = validate_password(valid_pwd)
    assert ok, msg
    assert validate_password("!@#$%^&*()_+-=[]{};:,.<>?/")[0]

    # 严禁大写字母
    bad_pwd_upper = "My-super-secret-password-12345"
    ok, msg = validate_password(bad_pwd_upper)
    assert not ok
    assert "大写字母" in msg

    # 长度太短
    bad_short = "short123"
    ok, msg = validate_password(bad_short)
    assert not ok
    assert "20 到 260" in msg

    # 无数字仍然合法，只要符合长度且不含大写字母。
    bad_no_digit = "this-password-has-no-digits-at-all"
    ok, msg = validate_password(bad_no_digit)
    assert ok, msg


def test_generate_secure_password():
    for _ in range(10):
        pwd = generate_secure_password(32)
        assert len(pwd) == 32
        assert not any(c.isupper() for c in pwd)
        ok, msg = validate_password(pwd)
        assert ok, msg


def test_password_hashing():
    pwd = generate_secure_password(32)
    h = hash_password(pwd)
    assert h.startswith("pbkdf2:sha256:200000$")
    assert verify_password(pwd, h)
    assert not verify_password(pwd + "x", h)
    assert not verify_password("wrong-password", h)


def test_session_token():
    secret = "test-secret-signing-key"
    payload = {"sub": 1, "username": "admin", "role": "admin"}
    token = create_session_token(payload, secret, expires_in_seconds=3600)
    verified = verify_session_token(token, secret)
    assert verified is not None
    assert verified["sub"] == 1
    assert verified["username"] == "admin"
    assert verified["role"] == "admin"

    # 篡改 token
    tampered = token[:-4] + "abcd"
    assert verify_session_token(tampered, secret) is None

    # 错误密钥
    assert verify_session_token(token, "wrong-secret") is None


def test_challenge_generation_and_consumption():
    c = generate_challenge("test_key", ttl_seconds=60)
    assert len(c) > 20
    # 第一次比对消费成功
    assert verify_and_consume_challenge("test_key", c)
    # 第二次比对已被消费，应失败
    assert not verify_and_consume_challenge("test_key", c)


@pytest.mark.asyncio
async def test_github_bind_login_flow():
    from app.api import (
        SECRET_KEY,
        GitHubBindLoginPayload,
        github_bind_login,
    )
    from app.models import Base, User
    from fastapi import HTTPException, Response
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as db:
            # 创建初始测试用户
            pwd = "test-strong-password-123456"
            user = User(
                username="testuser",
                password_hash=hash_password(pwd),
                role="user",
                is_active=True,
                sub_hash_token="token123"
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

            # 1. 签名有效的 GitHub 待绑定 token
            pending_token = create_session_token(
                {"action": "github_bind", "gh_id": "99999", "gh_login": "octocat"},
                SECRET_KEY,
                600
            )

            # 2. 错误的密码应该被拒绝
            with pytest.raises(HTTPException) as exc_info:
                await github_bind_login(
                    GitHubBindLoginPayload(pending_token=pending_token, username="testuser", password="wrong-password-here"),
                    Response(),
                    db
                )
            assert exc_info.value.status_code == 400

            # 3. 不存在的用户应该被拒绝（禁止注册）
            with pytest.raises(HTTPException) as exc_info:
                await github_bind_login(
                    GitHubBindLoginPayload(pending_token=pending_token, username="nonexistent", password=pwd),
                    Response(),
                    db
                )
            assert exc_info.value.status_code == 400

            # 4. 正确的账号密码，验证并成功绑定
            res = Response()
            result = await github_bind_login(
                GitHubBindLoginPayload(pending_token=pending_token, username="testuser", password=pwd),
                res,
                db
            )
            assert result["status"] == "ok"
            assert "sub_egress_session" in res.headers.get("set-cookie", "")

            # 5. 再次尝试绑定至其他用户，应报 409
            other_user = User(
                username="otheruser",
                password_hash=hash_password(pwd),
                role="user",
                is_active=True,
                sub_hash_token="token456"
            )
            db.add(other_user)
            await db.commit()

            with pytest.raises(HTTPException) as exc_info:
                await github_bind_login(
                    GitHubBindLoginPayload(pending_token=pending_token, username="otheruser", password=pwd),
                    Response(),
                    db
                )
            assert exc_info.value.status_code == 409
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_global_404_fallback():
    import httpx
    from app.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", follow_redirects=False) as client:
        # 1. 任意未匹配的页面路径（如 /a, /random-page）应 302 重定向到根目录 /
        res = await client.get("/a")
        assert res.status_code == 302
        assert res.headers["location"] == "/"

        res2 = await client.get("/random-unknown-page")
        assert res2.status_code == 302
        assert res2.headers["location"] == "/"

        # 2. 未匹配的 /api/ 接口路径应保留标准的 404 JSON
        api_res = await client.get("/api/nonexistent-endpoint")
        assert api_res.status_code == 404
        assert api_res.headers["content-type"].startswith("application/json")


