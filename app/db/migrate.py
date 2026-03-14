import asyncio
from pathlib import Path

import asyncpg

from app.core.config import settings


MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def run_migrations() -> None:
    conn = await asyncpg.connect(
        database=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
        host=settings.postgres_host,
        port=settings.postgres_port,
    )
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        applied_rows = await conn.fetch("SELECT version FROM schema_migrations")
        applied_versions = {row["version"] for row in applied_rows}

        for migration_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if migration_file.name in applied_versions:
                continue

            sql = migration_file.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES ($1)",
                    migration_file.name,
                )
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_migrations())
