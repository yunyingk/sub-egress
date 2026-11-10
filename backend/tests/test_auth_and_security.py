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
