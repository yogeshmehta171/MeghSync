from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .security import decode_token

_bearer = HTTPBearer(auto_error=False)


@dataclass
class Official:
    id: int
    username: str
    role: str


async def require_official(request: Request,
                           cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Official:
    """Every municipality-only endpoint depends on this."""
    if cred is None:
        raise HTTPException(401, "Login required", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = decode_token(request.app.state.settings.jwt_secret, cred.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expired, please log in again", headers={"WWW-Authenticate": "Bearer"})
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token", headers={"WWW-Authenticate": "Bearer"})
    if claims.get("role") not in ("municipality", "admin"):
        raise HTTPException(403, "Not allowed")
    return Official(id=int(claims["sub"]), username=claims["usr"], role=claims["role"])


async def require_admin(official: Official = Depends(require_official)) -> Official:
    if official.role != "admin":
        raise HTTPException(403, "Administrator role required")
    return official
