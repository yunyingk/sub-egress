"""
sub-egress Passkey / WebAuthn Core
Supports WebAuthn Level 2 / Level 3 registration and authentication using cryptography and cbor2.
"""
import base64
import hashlib
import json
import secrets
import time
from typing import Any

import cbor2
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

# Challenge 内存缓存 (TTL 5分钟)
_CHALLENGES: dict[str, tuple[str, float]] = {}


def _clean_expired_challenges():
    now = time.time()
    expired = [k for k, (_, exp) in _CHALLENGES.items() if exp < now]
    for k in expired:
        _CHALLENGES.pop(k, None)


def generate_challenge(key: str, ttl_seconds: int = 300) -> str:
    """生成 32 字节随机 base64url 编码的 Challenge 并缓存"""
    _clean_expired_challenges()
    challenge_bytes = secrets.token_bytes(32)
    challenge_str = base64.urlsafe_b64encode(challenge_bytes).decode("utf-8").rstrip("=")
    _CHALLENGES[key] = (challenge_str, time.time() + ttl_seconds)
    return challenge_str


def verify_and_consume_challenge(key: str, challenge: str) -> bool:
    """验证并消费 Challenge"""
    _clean_expired_challenges()
    stored = _CHALLENGES.pop(key, None)
    if not stored:
        return False
    stored_challenge, exp = stored
    if time.time() > exp:
        return False
    # 安全比对
    return secrets.compare_digest(stored_challenge, challenge)


def decode_b64url(s: str) -> bytes:
    """解码 base64url 字符串并自动补齐等号"""
    s = s.strip()
    padding_needed = (4 - len(s) % 4) % 4
    return base64.urlsafe_b64decode(s + ("=" * padding_needed))


def encode_b64url(data: bytes) -> str:
    """编码为无等号 base64url 字符串"""
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def cose_key_to_pem(cose_key: dict[int, Any]) -> str:
    """将 COSE Key 转换为 PEM 格式存储"""
    key_type = cose_key.get(1)
    alg = cose_key.get(3)

    if key_type == 2 and alg == -7 and cose_key.get(-1) == 1:  # EC2 (Elliptic Curve)
        # alg -7 是 ES256 (P-256)
        x = cose_key.get(-2)
        y = cose_key.get(-3)
        if not isinstance(x, bytes) or not isinstance(y, bytes):
            raise ValueError("Invalid EC2 key coordinates")
        x_int = int.from_bytes(x, "big")
        y_int = int.from_bytes(y, "big")
        public_numbers = ec.EllipticCurvePublicNumbers(x_int, y_int, ec.SECP256R1())
        pubkey = public_numbers.public_key()
        return pubkey.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

    elif key_type == 3 and alg == -257:  # RSA
        # alg -257 是 RS256
        n = cose_key.get(-1)
        e = cose_key.get(-2)
        if not isinstance(n, bytes) or not isinstance(e, bytes):
            raise ValueError("Invalid RSA key modulus/exponent")
        n_int = int.from_bytes(n, "big")
        e_int = int.from_bytes(e, "big")
        public_numbers = rsa.RSAPublicNumbers(e_int, n_int)
        pubkey = public_numbers.public_key()
        return pubkey.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

    raise ValueError(f"Unsupported COSE Key type {key_type} / alg {alg}")


def parse_and_verify_registration(
    client_data_json_b64: str,
    attestation_obj_b64: str,
    expected_challenge: str,
    rp_id: str,
    expected_origin: str,
) -> dict[str, Any]:
    """
    解析并验证 WebAuthn 注册凭证 (Attestation)
    返回:
    - credential_id: base64url 格式
    - public_key_pem: 对应公钥 PEM 字符串
    - sign_count: 计数器
    - aaguid: 凭证提供者唯一标识 hex
    """
    raw_client_data = decode_b64url(client_data_json_b64)
    client_data = json.loads(raw_client_data.decode("utf-8"))

    if client_data.get("type") != "webauthn.create":
        raise ValueError(f"ClientData type mismatch: {client_data.get('type')}")

    if not secrets.compare_digest(client_data.get("challenge", ""), expected_challenge):
        raise ValueError("WebAuthn challenge mismatch")

    if client_data.get("origin") != expected_origin or client_data.get("crossOrigin", False):
        raise ValueError("WebAuthn origin mismatch")

    raw_attestation = decode_b64url(attestation_obj_b64)
    att_obj = cbor2.loads(raw_attestation)
    auth_data = att_obj.get("authData")
    if not isinstance(auth_data, bytes) or len(auth_data) < 55:
        raise ValueError("Invalid authData in attestationObject")

    # 1. 验证 RP ID Hash
    rp_id_hash = auth_data[0:32]
    expected_rp_hash = hashlib.sha256(rp_id.encode("utf-8")).digest()
    if not secrets.compare_digest(rp_id_hash, expected_rp_hash):
        raise ValueError("WebAuthn RP ID hash mismatch")

    # 2. 检查 Flags: AT (Attested credential data) 必须为 1
    flags = auth_data[32]
    up = bool(flags & 0x01)
    uv = bool(flags & 0x04)
    at = bool(flags & 0x40)
    if not up or not at:
        raise ValueError("User presence or attested credential data flag is not set")

    sign_count = int.from_bytes(auth_data[33:37], "big")

    # 3. 提取 Attested Credential Data
    aaguid = auth_data[37:53]
    cred_id_len = int.from_bytes(auth_data[53:55], "big")
    if not cred_id_len or len(auth_data) <= 55 + cred_id_len:
        raise ValueError("Invalid credential data length")
    cred_id = auth_data[55 : 55 + cred_id_len]
    cose_data = auth_data[55 + cred_id_len :]

    cose_key = cbor2.loads(cose_data)
    pubkey_pem = cose_key_to_pem(cose_key)

    return {
        "credential_id": encode_b64url(cred_id),
        "public_key_pem": pubkey_pem,
        "sign_count": sign_count,
        "aaguid": aaguid.hex(),
        "user_verified": uv,
        "user_present": up,
    }


def verify_authentication_assertion(
    client_data_json_b64: str,
    authenticator_data_b64: str,
    signature_b64: str,
    expected_challenge: str,
    public_key_pem: str,
    expected_rp_id: str,
    expected_origin: str,
    stored_sign_count: int = 0,
) -> int:
    """
    验证通行密钥登录 Assertion 签名
    返回更新后的 sign_count
    """
    raw_client_data = decode_b64url(client_data_json_b64)
    client_data = json.loads(raw_client_data.decode("utf-8"))

    if client_data.get("type") != "webauthn.get":
        raise ValueError(f"ClientData type mismatch: {client_data.get('type')}")

    if not secrets.compare_digest(client_data.get("challenge", ""), expected_challenge):
        raise ValueError("WebAuthn challenge mismatch during authentication")

    if client_data.get("origin") != expected_origin or client_data.get("crossOrigin", False):
        raise ValueError("WebAuthn origin mismatch")

    auth_data = decode_b64url(authenticator_data_b64)
    if len(auth_data) < 37:
        raise ValueError("Invalid authenticatorData")

    if not secrets.compare_digest(auth_data[:32], hashlib.sha256(expected_rp_id.encode("utf-8")).digest()):
        raise ValueError("WebAuthn RP ID hash mismatch")

    flags = auth_data[32]
    up = bool(flags & 0x01)
    if not up:
        raise ValueError("User presence flag (UP) must be true")

    new_sign_count = int.from_bytes(auth_data[33:37], "big")

    # W3C WebAuthn Level 3:
    # 仅当 authenticator 与服务端均维护大于 0 的签名计数器时，才校验计数器单调递增。
    # 现代跨设备同步通行密钥（如 Apple iCloud 钥匙串、Google 密码管理工具）返回的计数器恒为 0，
    # 按照标准应当豁免单调递增校验，避免多端同步或无计数器设备验证失败。
    if new_sign_count > 0 and stored_sign_count > 0 and new_sign_count <= stored_sign_count:
        raise ValueError("WebAuthn signature counter did not increase")

    # 签名数据 = authenticatorData + SHA256(clientDataJSON)
    client_data_hash = hashlib.sha256(raw_client_data).digest()
    signed_bytes = auth_data + client_data_hash

    signature = decode_b64url(signature_b64)
    pubkey = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))

    if isinstance(pubkey, ec.EllipticCurvePublicKey):
        pubkey.verify(signature, signed_bytes, ec.ECDSA(hashes.SHA256()))
    elif isinstance(pubkey, rsa.RSAPublicKey):
        pubkey.verify(signature, signed_bytes, padding.PKCS1v15(), hashes.SHA256())
    else:
        raise ValueError("Unsupported public key type for verification")

    return new_sign_count if new_sign_count > 0 else stored_sign_count
