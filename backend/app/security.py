"""
sub-egress Security and Authentication Core
Provides PBKDF2-SHA256 password hashing, validation, session tokens, and password generation.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import string
import time
from typing import Any, Dict, Optional, Tuple

# ==================== 账号密码格式校验规范 ====================

def validate_username(username: str) -> Tuple[bool, str]:
    """
    用户名规则校验：
    - 长度：5 ~ 20 字符
    - 字符集：仅限小写英文字母 (a-z)、数字 (0-9)、连字符 (-) 或下划线 (_)
    - 严禁包含大写字母
    """
    if not username:
        return False, "用户名不能为空"
    if len(username) < 5 or len(username) > 20:
        return False, "用户名长度必须在 5 到 20 个字符之间"
    if any(c.isupper() for c in username):
        return False, "用户名严禁包含大写字母，仅支持小写字母、数字和连字符"
    if not re.match(r"^[a-z0-9_-]+$", username):
        return False, "用户名仅允许包含小写字母、数字、下划线(_)或连字符(-)"
    return True, ""


def validate_password(password: str) -> Tuple[bool, str]:
    """
    密码规则校验：
    - 长度：20 ~ 260 字符
    - 严禁包含大写字母
    - 必须包含小写字母和数字，可包含键盘符号
    """
    if not password:
        return False, "密码不能为空"
    if len(password) < 20 or len(password) > 260:
        return False, "密码长度必须在 20 到 260 个字符之间"
    if any(c.isupper() for c in password):
        return False, "密码严禁包含大写字母，请使用小写字母、数字和符号"
    if not any(c.islower() for c in password):
        return False, "密码必须至少包含一个小写英文字母"
    if not any(c.isdigit() for c in password):
        return False, "密码必须至少包含一个数字"
    return True, ""


def generate_secure_password(length: int = 32) -> str:
    """
    生成符合规范的超长安全随机密码：
    - 纯小写英文字母 (a-z) + 数字 (0-9) + 安全标点符号 (!@#%&*+-=._)
    - 绝对不包含大写字母
    """
    length = max(20, min(length, 260))
    lowers = string.ascii_lowercase
    digits = string.digits
    safe_symbols = "!@#%&*+-=._"
    all_chars = lowers + digits + safe_symbols

    # 确保至少包含小写、数字和符号
    pwd = [
        secrets.choice(lowers),
        secrets.choice(digits),
        secrets.choice(safe_symbols)
    ]
    pwd += [secrets.choice(all_chars) for _ in range(length - len(pwd))]
    secrets.SystemRandom().shuffle(pwd)
    return "".join(pwd)


# ==================== 密码加盐哈希（PBKDF2-SHA256） ====================

def hash_password(password: str) -> str:
    """
    使用内置标准库 PBKDF2-HMAC-SHA256 进行 200,000 轮加盐哈希存储。
    格式: pbkdf2:sha256:200000$<salt_hex>$<hash_hex>
    """
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200000)
    return f"pbkdf2:sha256:200000${salt.hex()}${key.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """
    验证密码与加盐哈希串是否一致。
    """
    if not hashed or not password:
        return False
    try:
        parts = hashed.split("$")
        if len(parts) != 3 or not parts[0].startswith("pbkdf2:sha256:"):
            return False
        iterations = int(parts[0].split(":")[2])
        salt = bytes.fromhex(parts[1])
        expected_key = parts[2]
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return secrets.compare_digest(key.hex(), expected_key)
    except Exception:
        return False


# ==================== 签名会话令牌 (HMAC-SHA256 Session) ====================

def _b64encode_url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64decode_url(s: str) -> bytes:
    padding = "=" * (4 - (len(s) % 4)) if (len(s) % 4) else ""
    return base64.urlsafe_b64decode(s + padding)


def create_session_token(payload: Dict[str, Any], secret_key: str, expires_in_seconds: int = 86400 * 30) -> str:
    """
    创建带 HMAC-SHA256 签名的无依赖 Session Token。
    格式: <payload_b64>.<signature_b64>
    """
    token_payload = dict(payload)
    token_payload["exp"] = int(time.time()) + expires_in_seconds
    raw_payload = json.dumps(token_payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = _b64encode_url(raw_payload)

    sig = hmac.new(secret_key.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    sig_b64 = _b64encode_url(sig)

    return f"{payload_b64}.{sig_b64}"


def verify_session_token(token: str, secret_key: str) -> Optional[Dict[str, Any]]:
    """
    验证 Session Token 签名并检查过期时间。
    """
    if not token or "." not in token:
        return None
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        expected_sig = hmac.new(secret_key.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).digest()
        actual_sig = _b64decode_url(sig_b64)

        if not secrets.compare_digest(expected_sig, actual_sig):
            return None

        raw_payload = _b64decode_url(payload_b64)
        payload = json.loads(raw_payload.decode("utf-8"))

        if "exp" in payload and time.time() > payload["exp"]:
            return None

        return payload
    except Exception:
        return None
