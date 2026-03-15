import argparse
import asyncio
import sys
from datetime import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import AsyncDatabase
from app.services.embedding_sync import EmbeddingSyncService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run scheduled embeddings sync service")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Batch size for incremental embeddings sync. Defaults to EMBEDDINGS_BATCH_SIZE.",
    )
    parser.add_argument(
        "--run-at",
        type=parse_run_at,
        default=parse_run_at("03:00"),
        help="Daily time in HH:MM when incremental embeddings sync should start.",
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run one incremental sync and exit.",
    )
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Rebuild all embeddings on each run instead of only missing or changed records.",
    )
    return parser.parse_args()


def parse_run_at(value: str) -> time:
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("run-at must be in HH:MM format")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError("run-at must contain numeric hour and minute") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise argparse.ArgumentTypeError("run-at must be a valid 24-hour time")
    return time(hour=hour, minute=minute)


async def main_async(args: argparse.Namespace) -> None:
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
        service = EmbeddingSyncService(db)
        if args.run_once:
            result = await service.run_once(
                batch_size=args.batch_size,
                force_rebuild=args.force_rebuild,
            )
            print(result)
            return

        await service.run_daily_at(
            run_at=args.run_at,
            batch_size=args.batch_size,
            force_rebuild=args.force_rebuild,
        )
    finally:
        await db.close()


def main() -> None:
    configure_logging()
    args = parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
