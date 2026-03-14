import asyncio
import hashlib
import logging
import math
import threading
from time import perf_counter

import torch
from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.db.session import AsyncDatabase
from app.repositories.procurement_analysis import ProcurementAnalysisRepository
from app.services.cte_search_text import CteSearchTextBuilder

logger = logging.getLogger(__name__)


class EmbeddingRuntimeError(RuntimeError):
    pass


class TransformerEmbeddingClient:
    _lock = threading.Lock()
    _model: SentenceTransformer | None = None

    def __init__(self) -> None:
        self._dimensions = settings.embeddings_dimensions

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        prefixed = [f"{self._normalized_prefix(settings.embeddings_document_prefix)}{text}" for text in texts]
        return await asyncio.to_thread(self._encode_many, prefixed)

    async def embed_query(self, text: str) -> list[float]:
        prefixed = f"{self._normalized_prefix(settings.embeddings_query_prefix)}{text}"
        vectors = await asyncio.to_thread(self._encode_many, [prefixed])
        return vectors[0]

    @staticmethod
    def to_vector_literal(vector: list[float]) -> str:
        return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"

    @staticmethod
    def _normalized_prefix(prefix_value: str) -> str:
        prefix = prefix_value.strip()
        return f"{prefix} " if prefix else ""

    def _encode_many(self, texts: list[str]) -> list[list[float]]:
        try:
            model = self._get_model()
            encoded = model.encode(
                texts,
                batch_size=max(1, settings.embeddings_batch_size),
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
        except Exception as exc:
            raise EmbeddingRuntimeError(f"Embeddings generation failed: {exc}") from exc

        vectors: list[list[float]] = []
        for row in encoded.tolist():
            vector = [float(value) for value in row[: self._dimensions]]
            if len(vector) != self._dimensions:
                raise EmbeddingRuntimeError(
                    f"Embedding dimensions mismatch: expected {self._dimensions}, got {len(vector)}"
                )
            vectors.append(self._l2_normalize(vector))
        return vectors

    @staticmethod
    def _l2_normalize(vector: list[float]) -> list[float]:
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    @classmethod
    def _get_model(cls) -> SentenceTransformer:
        if cls._model is not None:
            return cls._model

        with cls._lock:
            if cls._model is not None:
                return cls._model

            device = "cpu"
            if torch.cuda.is_available():
                device = "cuda"
            elif torch.backends.mps.is_available():
                device = "mps"

            cls._model = SentenceTransformer(
                settings.embeddings_model_name,
                device=device,
                trust_remote_code=True,
            )
            cls._model.max_seq_length = settings.embeddings_max_length
            return cls._model


class CteEmbeddingBackfillService:
    def __init__(self, db: AsyncDatabase):
        self.db = db
        self.repository = ProcurementAnalysisRepository(db)
        self.embedding_client = TransformerEmbeddingClient()

    async def backfill(
        self,
        batch_size: int | None = None,
        force_rebuild: bool = False,
    ) -> dict[str, int]:
        started_at = perf_counter()
        processed_cte = 0
        updated_embeddings = 0
        current_batch_size = batch_size or settings.embeddings_batch_size
        after_cte_id = 0
        batch_number = 0
        total_cte = await self.repository.count_cte()

        logger.info(
            "Starting CTE embeddings backfill: total=%s batch_size=%s force_rebuild=%s model=%s",
            total_cte,
            current_batch_size,
            force_rebuild,
            settings.embeddings_model_name,
        )

        while True:
            batch_started_at = perf_counter()
            async with self.db.transaction() as conn:
                rows = await self.repository.fetch_cte_embedding_backfill_batch(conn, after_cte_id, current_batch_size)
                if not rows:
                    break

                batch_number += 1
                texts_to_embed: list[str] = []
                rows_to_update: list[dict] = []
                batch_processed = len(rows)

                for row in rows:
                    processed_cte += 1
                    input_text = CteSearchTextBuilder.build(
                        name=row["name"],
                        category_name=row["category_name"],
                        manufacturer_name=row.get("manufacturer_name"),
                        characteristics=row.get("characteristics") or {},
                    )
                    input_hash = hashlib.sha256(input_text.encode("utf-8")).hexdigest()
                    after_cte_id = row["id"]
                    if not force_rebuild and row.get("input_hash") == input_hash:
                        continue

                    rows_to_update.append(
                        {
                            "cte_id": row["id"],
                            "input_text": input_text,
                            "input_hash": input_hash,
                        }
                    )
                    texts_to_embed.append(input_text)

                if not rows_to_update:
                    self._log_progress(
                        batch_number=batch_number,
                        processed_cte=processed_cte,
                        total_cte=total_cte,
                        updated_in_batch=0,
                        updated_embeddings=updated_embeddings,
                        batch_processed=batch_processed,
                        batch_started_at=batch_started_at,
                        started_at=started_at,
                    )
                    continue

                vectors = await self.embedding_client.embed_documents(texts_to_embed)
                db_rows = [
                    (
                        payload["cte_id"],
                        settings.embeddings_model_name,
                        settings.embeddings_dimensions,
                        payload["input_text"],
                        payload["input_hash"],
                        self.embedding_client.to_vector_literal(vector),
                    )
                    for payload, vector in zip(rows_to_update, vectors, strict=True)
                ]
                await self.repository.upsert_cte_embeddings_batch(conn=conn, rows=db_rows)
                updated_embeddings += len(db_rows)
                self._log_progress(
                    batch_number=batch_number,
                    processed_cte=processed_cte,
                    total_cte=total_cte,
                    updated_in_batch=len(db_rows),
                    updated_embeddings=updated_embeddings,
                    batch_processed=batch_processed,
                    batch_started_at=batch_started_at,
                    started_at=started_at,
                )

        elapsed = perf_counter() - started_at
        logger.info(
            "Finished CTE embeddings backfill: processed=%s updated=%s total=%s elapsed=%.1fs",
            processed_cte,
            updated_embeddings,
            total_cte,
            elapsed,
        )

        return {
            "processed_cte": processed_cte,
            "updated_embeddings": updated_embeddings,
        }

    @staticmethod
    def _log_progress(
        *,
        batch_number: int,
        processed_cte: int,
        total_cte: int,
        updated_in_batch: int,
        updated_embeddings: int,
        batch_processed: int,
        batch_started_at: float,
        started_at: float,
    ) -> None:
        batch_elapsed = max(perf_counter() - batch_started_at, 1e-9)
        total_elapsed = max(perf_counter() - started_at, 1e-9)
        percent = (processed_cte / total_cte * 100.0) if total_cte else 100.0
        batch_rate = batch_processed / batch_elapsed
        avg_rate = processed_cte / total_elapsed
        logger.info(
            "CTE embeddings backfill progress: batch=%s processed=%s/%s (%.1f%%) updated_batch=%s updated_total=%s batch_rate=%.1f cte/s avg_rate=%.1f cte/s",
            batch_number,
            processed_cte,
            total_cte,
            percent,
            updated_in_batch,
            updated_embeddings,
            batch_rate,
            avg_rate,
        )
