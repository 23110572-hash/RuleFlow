"""Authentication primitives — password hashing + signed session tokens.

Stdlib only (pbkdf2 + hmac) so there is no extra dependency to install. Tokens
are compact JWT-style: base64url(header).base64url(payload).base64url(sig),
signed with HMAC-SHA256 over the app secret.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from app.config import settings

_PBKDF2_ROUNDS = 200_000


# ---- password hashing ----

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


# ---- tokens ----

def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_token(subject: str, extra: dict | None = None) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {"sub": subject, "iat": now, "exp": now + settings.token_expiry_minutes * 60}
    if extra:
        payload.update(extra)
    h = _b64u(json.dumps(header, separators=(",", ":")).encode())
    p = _b64u(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(settings.secret_key.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
    return f"{h}.{p}.{_b64u(sig)}"


def decode_token(token: str) -> dict | None:
    try:
        h, p, s = token.split(".")
        expected = hmac.new(settings.secret_key.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64u(expected), s):
            return None
        payload = json.loads(_b64u_decode(p))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None
