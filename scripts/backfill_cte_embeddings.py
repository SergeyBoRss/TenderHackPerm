import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import AsyncDatabase
from app.services.cte_embeddings import CteEmbeddingBackfillService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild cte embeddings from terminal")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Batch size for cte backfill. Defaults to EMBEDDINGS_BATCH_SIZE.",
    )
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Rebuild all embeddings even if input_hash already matches.",
    )
    return parser.parse_args()


async def run_backfill(batch_size: int | None, force_rebuild: bool) -> None:
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
        result = await CteEmbeddingBackfillService(db).backfill(
            batch_size=batch_size,
            force_rebuild=force_rebuild,
        )
        print(result)
    finally:
        await db.close()


def main() -> None:
    configure_logging()
    args = parse_args()
    asyncio.run(
        run_backfill(
            batch_size=args.batch_size,
            force_rebuild=args.force_rebuild,
        )
    )


if __name__ == "__main__":
    main()
