from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status

from app.db.deps import get_db
from app.db.session import AsyncDatabase
from app.schemas.imports import ClearImportDataResponse, ImportResultResponse
from app.services.imports import ImportValidationError, ProcurementImportService


router = APIRouter(prefix="/imports", tags=["imports"])


@router.delete("/procurement-data", response_model=ClearImportDataResponse)
async def clear_procurement_data(db: AsyncDatabase = Depends(get_db)) -> ClearImportDataResponse:
    service = ProcurementImportService(db)
    await service.clear_all()
    return ClearImportDataResponse(status="cleared")


@router.post("/procurement-data/load", response_model=ImportResultResponse)
async def load_procurement_data(db: AsyncDatabase = Depends(get_db)) -> ImportResultResponse:
    service = ProcurementImportService(db)
    try:
        result = await service.load(refresh=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ImportValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ImportResultResponse.model_validate(asdict(result))


@router.post("/procurement-data/refresh", response_model=ImportResultResponse)
async def refresh_procurement_data(db: AsyncDatabase = Depends(get_db)) -> ImportResultResponse:
    service = ProcurementImportService(db)
    try:
        result = await service.load(refresh=True)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ImportValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ImportResultResponse.model_validate(asdict(result))
