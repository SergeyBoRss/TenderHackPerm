import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from datetime import time
from datetime import timedelta

from app.db.session import AsyncDatabase
from app.services.cte_embeddings import CteEmbeddingBackfillService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EmbeddingSyncRunResult:
    processed_cte: int
    updated_embeddings: int


class EmbeddingSyncService:
    def __init__(self, db: AsyncDatabase):
        self.db = db
        self.backfill_service = CteEmbeddingBackfillService(db)

    async def run_once(
        self,
        *,
        batch_size: int | None = None,
        force_rebuild: bool = False,
    ) -> EmbeddingSyncRunResult:
        logger.info(
            "Starting embeddings sync run: batch_size=%s force_rebuild=%s",
            batch_size,
            force_rebuild,
        )
        result = await self.backfill_service.backfill(
            batch_size=batch_size,
            force_rebuild=force_rebuild,
        )
        logger.info(
            "Finished embeddings sync run: processed=%s updated=%s",
            result["processed_cte"],
            result["updated_embeddings"],
        )
        return EmbeddingSyncRunResult(
            processed_cte=int(result["processed_cte"]),
            updated_embeddings=int(result["updated_embeddings"]),
        )

    async def run_daily_at(
        self,
        *,
        run_at: time,
        batch_size: int | None = None,
        force_rebuild: bool = False,
    ) -> None:
        while True:
            sleep_seconds = self._seconds_until_next_run(run_at)
            next_run = datetime.now() + timedelta(seconds=sleep_seconds)
            logger.info(
                "Sleeping until next embeddings sync run: run_at=%s next_run=%s sleep_seconds=%s",
                run_at.strftime("%H:%M"),
                next_run.isoformat(timespec="seconds"),
                sleep_seconds,
            )
            await asyncio.sleep(sleep_seconds)
            try:
                await self.run_once(
                    batch_size=batch_size,
                    force_rebuild=force_rebuild,
                )
            except Exception:
                logger.exception("Embeddings sync iteration failed")

    @staticmethod
    def _seconds_until_next_run(run_at: time) -> int:
        now = datetime.now()
        next_run = now.replace(hour=run_at.hour, minute=run_at.minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        return max(1, int((next_run - now).total_seconds()))
