from fastapi import APIRouter, Depends, HTTPException, status

from app.db.deps import get_db
from app.db.session import AsyncDatabase
from app.schemas.analytics import (
    EmbeddingBackfillRequest,
    EmbeddingBackfillResponse,
    EmbeddingExcelImportRequest,
    EmbeddingExcelImportResponse,
)
from app.services.cte_embeddings import CteEmbeddingBackfillService, EmbeddingRuntimeError
from app.services.embedding_imports import EmbeddingImportService, EmbeddingImportValidationError


router = APIRouter(prefix="/embeddings", tags=["embeddings"])


@router.post("/backfill", response_model=EmbeddingBackfillResponse)
async def backfill_cte_embeddings(
    payload: EmbeddingBackfillRequest,
    db: AsyncDatabase = Depends(get_db),
) -> EmbeddingBackfillResponse:
    service = CteEmbeddingBackfillService(db)
    try:
        result = await service.backfill(
            batch_size=payload.batch_size,
            force_rebuild=payload.force_rebuild,
        )
    except EmbeddingRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return EmbeddingBackfillResponse.model_validate(result)


@router.post("/import-from-excel", response_model=EmbeddingExcelImportResponse)
async def import_embeddings_from_excel(
    payload: EmbeddingExcelImportRequest,
    db: AsyncDatabase = Depends(get_db),
) -> EmbeddingExcelImportResponse:
    service = EmbeddingImportService(db)
    try:
        result = await service.import_from_excel(
            file_path=payload.file_path,
            batch_size=payload.batch_size,
            truncate=payload.truncate,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EmbeddingImportValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return EmbeddingExcelImportResponse.model_validate(result)
