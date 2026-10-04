from __future__ import annotations


async def log_action(conn, official: str, ref: str, action: str, description: str, status: str | None = None) -> None:
    """Append to the official action log. `conn` may be a pool or a connection (use a connection inside a transaction)."""
    await conn.execute(
        "INSERT INTO actions(official_id, ref_id, action, description, status) VALUES ($1, $2, $3, $4, $5)",
        official, ref or "-", action, description, status)
