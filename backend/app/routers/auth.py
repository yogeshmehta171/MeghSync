from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth.deps import Official, require_official
from ..auth.security import DUMMY_HASH, create_token, verify_password
from ..ratelimit import RateLimiter
from ..schemas import LoginRequest

router = APIRouter(prefix="/api/auth")
_login_limit = RateLimiter(10, 60, "login")


@router.post("/login")
async def login(request: Request, body: LoginRequest):
    _login_limit.check(request)
    st = request.app.state
    async with st.pool.acquire() as conn:
        u = await conn.fetchrow("SELECT * FROM users WHERE username = $1", body.municipality_id.strip())
        ok = verify_password(body.password, u["password_hash"] if u else DUMMY_HASH)
        if not (u and ok and u["active"]):
            raise HTTPException(401, "Invalid ID or password")
        await conn.execute("UPDATE users SET last_login_at = now() WHERE id = $1", u["id"])
    ttl = st.settings.jwt_ttl_minutes
    token = create_token(st.settings.jwt_secret, ttl, u["id"], u["username"], u["role"])
    return {"token": token, "tokenType": "bearer", "expiresInSeconds": ttl * 60,
            "user": {"id": u["id"], "username": u["username"], "displayName": u["display_name"], "role": u["role"]}}


@router.get("/me")
async def me(official: Official = Depends(require_official)):
    return {"id": official.id, "username": official.username, "role": official.role}
