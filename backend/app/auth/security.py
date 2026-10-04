"""Password hashing (stdlib scrypt, no extra dependency) and JWT tokens (PyJWT)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time

import jwt

_N, _R, _P = 2 ** 14, 8, 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return "scrypt${}${}${}${}${}".format(_N, _R, _P, base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(dk_b64)
        dk = hashlib.scrypt(password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


# Used when the username does not exist, so response time does not reveal which usernames are real.
DUMMY_HASH = hash_password("not-a-real-password")


def create_token(secret: str, ttl_minutes: int, user_id: int, username: str, role: str) -> str:
    now = int(time.time())
    return jwt.encode({"sub": str(user_id), "usr": username, "role": role, "iat": now,
                       "exp": now + ttl_minutes * 60}, secret, algorithm="HS256")


def decode_token(secret: str, token: str) -> dict:
    return jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["exp", "sub"]})
