import hashlib
import json

import cbor2
import httpx
import pytest
from app.auth_webauthn import (
    encode_b64url,
    parse_and_verify_registration,
    verify_authentication_assertion,
)
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI

RP_ID = "example.test"
ORIGIN = "https://example.test"
CHALLENGE = "challenge"


def client_data(kind, origin=ORIGIN):
    return json.dumps({"type": kind, "challenge": CHALLENGE, "origin": origin}).encode()


def registration_data(rp_id=RP_ID, flags=0x41):
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_numbers()
    cose = {1: 2, 3: -7, -1: 1, -2: public.x.to_bytes(32, "big"), -3: public.y.to_bytes(32, "big")}
    credential_id = b"credential"
    auth_data = (hashlib.sha256(rp_id.encode()).digest() + bytes([flags]) + b"\0" * 4
                 + b"\0" * 16 + len(credential_id).to_bytes(2, "big") + credential_id + cbor2.dumps(cose))
    return encode_b64url(cbor2.dumps({"fmt": "none", "authData": auth_data, "attStmt": {}}))


def test_registration_validates_origin_rp_id_and_presence():
    def verify(origin=ORIGIN, rp_id=RP_ID, flags=0x41):
        return parse_and_verify_registration(
            encode_b64url(client_data("webauthn.create", origin)), registration_data(rp_id, flags),
            CHALLENGE, RP_ID, ORIGIN,
        )
    assert verify()["credential_id"] == encode_b64url(b"credential")
    with pytest.raises(ValueError, match="origin"):
        verify(origin="https://other.test")
    with pytest.raises(ValueError, match="RP ID"):
        verify(rp_id="other.test")
    with pytest.raises(ValueError, match="presence"):
        verify(flags=0x40)


def test_authentication_validates_signed_data_and_counter():
    key = ec.generate_private_key(ec.SECP256R1())
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    def verify(origin=ORIGIN, rp_id=RP_ID, counter=1, stored=0):
        client = client_data("webauthn.get", origin)
        auth = hashlib.sha256(rp_id.encode()).digest() + b"\x01" + counter.to_bytes(4, "big")
        signature = key.sign(auth + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        return verify_authentication_assertion(
            encode_b64url(client), encode_b64url(auth), encode_b64url(signature),
            CHALLENGE, public_pem, RP_ID, ORIGIN, stored,
        )

    assert verify() == 1
    assert verify(counter=0) == 0
    assert verify(counter=0, stored=1) == 1
    with pytest.raises(ValueError, match="origin"):
        verify(origin="https://other.test")
    with pytest.raises(ValueError, match="RP ID"):
        verify(rp_id="other.test")
    with pytest.raises(ValueError, match="counter"):
        verify(counter=1, stored=1)


@pytest.mark.asyncio
async def test_login_challenges_are_isolated_by_browser(monkeypatch, tmp_path):
    monkeypatch.setenv("WEBAUTHN_ORIGIN", ORIGIN)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.api import router
    from app.auth_webauthn import _CHALLENGES

    app = FastAPI()
    app.include_router(router)
    assert "/api/auth/passkey/login/start" in app.openapi()["paths"]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=ORIGIN) as first, httpx.AsyncClient(
        transport=transport, base_url=ORIGIN,
    ) as second:
        first_response = await first.post("/api/auth/passkey/login/start")
        second_response = await second.post("/api/auth/passkey/login/start")
        assert first_response.status_code == second_response.status_code == 200
        first_id = first.cookies.get("webauthn_login")
        second_id = second.cookies.get("webauthn_login")
        assert first_id and second_id and first_id != second_id
        assert _CHALLENGES[f"login:{first_id}"][0] == first_response.json()["challenge"]
        assert _CHALLENGES[f"login:{second_id}"][0] == second_response.json()["challenge"]


@pytest.mark.asyncio
async def test_passkey_endpoints_require_configured_origin(monkeypatch, tmp_path):
    monkeypatch.delenv("WEBAUTHN_ORIGIN", raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.api import router

    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        assert (await client.post("/api/auth/passkey/login/start")).status_code == 503
        monkeypatch.setenv("WEBAUTHN_ORIGIN", "https://different.test")
        assert (await client.post("/api/auth/passkey/login/start")).status_code == 400
