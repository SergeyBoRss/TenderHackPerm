import asyncio

from app.core.config import settings
from app.db.session import AsyncDatabase
from app.services.cte_embeddings import CteEmbeddingBackfillService


async def main() -> None:
    db = AsyncDatabase(
        db_name=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
        host=settings.postgres_host,
        port=settings.postgres_port,
        min_size=1,
        max_size=1,
        ssl_mode=settings.postgres_ssl_mode,
    )
    await db.connect()
    try:
        result = await CteEmbeddingBackfillService(db).backfill()
        print(result)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
