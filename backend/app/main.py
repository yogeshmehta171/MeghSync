from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth.security import hash_password
from .config import load_settings
from .db import create_pool, run_migrations
from .routers import admin, auth, public
from .services import retention
from .services.engine import Engine
from .services.reports import ReportError

log = logging.getLogger("pravaha")


async def _bootstrap_admin(pool, settings) -> None:
    """Create the first official from env vars if the users table is empty. Never overwrites existing users."""
    if not (settings.bootstrap_user and settings.bootstrap_password):
        return
    if len(settings.bootstrap_password) < 10:
        raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD must be at least 10 characters")
    async with pool.acquire() as conn:
        n = await conn.fetchval("SELECT count(*) FROM users")
        if n == 0:
            await conn.execute("INSERT INTO users(username, password_hash, role, display_name) VALUES ($1,$2,'admin',$1)",
                               settings.bootstrap_user, hash_password(settings.bootstrap_password))
            log.warning("Created first administrator '%s'. Remove BOOTSTRAP_ADMIN_* from the environment now.",
                        settings.bootstrap_user)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    pool = await create_pool(settings.database_url)
    applied = await run_migrations(pool)
    if applied:
        log.info("applied migrations: %s", applied)
    await _bootstrap_admin(pool, settings)
    engine = Engine(settings, pool)
    await engine.start()
    app.state.settings, app.state.pool, app.state.engine = settings, pool, engine
    retention_task = asyncio.create_task(retention.loop(pool, engine.cfg), name="retention")
    log.info("Ready: model=%s nodes=%d", engine.provider.name, len(engine.node_ids))
    yield
    retention_task.cancel()
    await engine.stop()
    await pool.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Pravaha-X T. Nagar Flood API", version="2.0", lifespan=lifespan)
    s = load_settings()                                      # also fails fast here if env is incomplete
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Authorization", "Content-Type"])

    @app.exception_handler(ReportError)
    async def _report_error(_: Request, exc: ReportError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    app.include_router(public.router)
    app.include_router(auth.router)
    app.include_router(admin.router)
    return app


app = create_app()
