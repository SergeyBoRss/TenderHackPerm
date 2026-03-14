from pathlib import Path

from openpyxl import load_workbook

from app.core.config import settings
from app.db.session import AsyncDatabase
from app.repositories.procurement_analysis import ProcurementAnalysisRepository

EXPECTED_HEADERS = (
    "cte_id",
    "model_name",
    "embedding_dimensions",
    "input_text",
    "input_hash",
    "embedding",
    "created_at",
    "updated_at",
)


class EmbeddingImportValidationError(ValueError):
    pass


class EmbeddingImportService:
    def __init__(self, db: AsyncDatabase):
        self.db = db
        self.repository = ProcurementAnalysisRepository(db)

    async def import_from_excel(
        self,
        *,
        file_path: str | None = None,
        batch_size: int = 1000,
        truncate: bool = False,
    ) -> dict[str, int | str]:
        path = Path(file_path or settings.import_cte_embeddings_file)
        if not path.exists():
            raise FileNotFoundError(f"Embeddings file not found: {path}")
        if batch_size <= 0:
            raise EmbeddingImportValidationError("batch_size must be positive")

        imported = 0
        batch: list[tuple[int, str, int, str, str, str]] = []

        if truncate:
            async with self.db.transaction() as conn:
                await self.repository.truncate_cte_embeddings(conn)

        workbook = load_workbook(path, read_only=True, data_only=True)
        worksheet = workbook.active
        rows = worksheet.iter_rows(values_only=True)

        try:
            try:
                headers = next(rows)
            except StopIteration as exc:
                raise EmbeddingImportValidationError("Embeddings xlsx is empty") from exc

            if tuple(headers) != EXPECTED_HEADERS:
                raise EmbeddingImportValidationError(f"Unexpected headers: {headers}")

            for row_number, row in enumerate(rows, start=2):
                if row is None or all(value is None for value in row):
                    continue

                cte_id, model_name, embedding_dimensions, input_text, input_hash, embedding, *_ = row
                if None in (cte_id, model_name, embedding_dimensions, input_text, input_hash, embedding):
                    raise EmbeddingImportValidationError(
                        f"Row {row_number}: required columns contain null values"
                    )

                batch.append(
                    (
                        int(cte_id),
                        str(model_name),
                        int(embedding_dimensions),
                        str(input_text),
                        str(input_hash),
                        str(embedding),
                    )
                )

                if len(batch) < batch_size:
                    continue

                async with self.db.transaction() as conn:
                    await self.repository.upsert_cte_embeddings_batch(conn, batch)
                imported += len(batch)
                batch.clear()

            if batch:
                async with self.db.transaction() as conn:
                    await self.repository.upsert_cte_embeddings_batch(conn, batch)
                imported += len(batch)
        finally:
            workbook.close()

        return {
            "file_path": str(path),
            "imported_embeddings": imported,
        }
