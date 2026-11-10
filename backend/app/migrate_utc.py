"""Inspect or migrate legacy PostgreSQL timestamps assumed to represent UTC."""

import argparse
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

try:
    from .db import DATABASE_URL
except ImportError:
    from app.db import DATABASE_URL

TIMESTAMP_COLUMNS = {
    "users": ("last_login_at", "created_at", "updated_at"),
    "passkey_credentials": ("created_at", "last_used_at"),
    "sources": ("expire_at", "last_sync_at", "created_at", "updated_at"),
    "nodes": ("latency_updated_at", "created_at"),
    "settings": ("updated_at",),
}


async def migrate(apply: bool) -> None:
    if not DATABASE_URL.startswith("postgresql+asyncpg://"):
        raise RuntimeError("This migration supports PostgreSQL only")
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.begin() as connection:
            rows = await connection.execute(text("""
                SELECT table_name, column_name, data_type FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name IN ('users', 'passkey_credentials', 'sources', 'nodes', 'settings')
                  AND data_type LIKE 'timestamp%'
            """))
            for table, column, data_type in rows:
                if column not in TIMESTAMP_COLUMNS.get(table, ()):
                    raise RuntimeError(f"Unexpected timestamp column: {table}.{column}")
                if data_type == "timestamp without time zone":
                    print(f"{'Migrate' if apply else 'Would migrate'} {table}.{column} (assuming UTC)")
                    if apply:
                        await connection.execute(text(
                            f'ALTER TABLE "{table}" ALTER COLUMN "{column}" '
                            f'TYPE TIMESTAMP WITH TIME ZONE USING "{column}" AT TIME ZONE \'UTC\''
                        ))
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply changes instead of showing a dry run")
    parser.add_argument("--assume-utc", action="store_true", help="Confirm all legacy timestamps represent UTC")
    args = parser.parse_args()
    if args.apply and not args.assume_utc:
        parser.error("--apply requires --assume-utc after verifying the original time zone")
    asyncio.run(migrate(args.apply))


if __name__ == "__main__":
    main()
