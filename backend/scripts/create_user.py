"""
Create or reset a municipality login.

    python scripts/create_user.py MUNI_01 --role admin
    python scripts/create_user.py MUNI_02 --reset          (asks for a new password)

Reads DATABASE_URL from the environment (same as the server). The password is typed at a hidden prompt,
never passed on the command line, so it does not end up in shell history.
"""
import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import asyncpg  # noqa: E402

from app.auth.security import hash_password  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("username")
    ap.add_argument("--role", choices=["municipality", "admin"], default="municipality")
    ap.add_argument("--name", default=None, help="display name")
    ap.add_argument("--reset", action="store_true", help="change the password of an existing user")
    ap.add_argument("--disable", action="store_true", help="deactivate the user")
    a = ap.parse_args()
    dsn = os.getenv("DATABASE_URL", "postgresql://flood:flood@localhost:5433/flood_db")
    conn = await asyncpg.connect(dsn)
    try:
        if a.disable:
            tag = await conn.execute("UPDATE users SET active = FALSE WHERE username = $1", a.username)
            print("disabled" if tag.endswith("1") else "no such user")
            return
        pw = getpass.getpass("Password (min 10 chars): ")
        if len(pw) < 10 or pw != getpass.getpass("Repeat password: "):
            sys.exit("Passwords differ or are shorter than 10 characters.")
        h = hash_password(pw)
        if a.reset:
            tag = await conn.execute("UPDATE users SET password_hash=$2, active=TRUE WHERE username=$1", a.username, h)
            print("password changed" if tag.endswith("1") else "no such user")
        else:
            await conn.execute("INSERT INTO users(username, password_hash, role, display_name) VALUES ($1,$2,$3,$4)",
                               a.username, h, a.role, a.name or a.username)
            print(f"created {a.role} '{a.username}'")
    finally:
        await conn.close()


asyncio.run(main())
