from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status

from app.db.deps import get_db
from app.db.session import AsyncDatabase
from app.schemas.analytics import (
    CteDetailResponse,
    CteSearchRequest,
    CteSearchResponse,
    CteUpdateRequest,
    ManualCteCreateRequest,
    ManualCteCreateResponse,
)
from app.services.cte_embeddings import CteEmbeddingBackfillService, EmbeddingRuntimeError
from app.services.pricing_statistics import PricingStatisticsService


router = APIRouter(prefix="/cte", tags=["cte"])


@router.get("/{cte_id}", response_model=CteDetailResponse)
async def get_cte(
    cte_id: int,
    db: AsyncDatabase = Depends(get_db),
) -> CteDetailResponse:
    service = PricingStatisticsService(db)
    result = await service.get_cte(cte_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"CTE {cte_id} not found")
    return CteDetailResponse.model_validate(
        {
            "cte_id": result["id"],
            "name": result["name"],
            "category_id": result["category_id"],
            "category_name": result["category_name"],
            "manufacturer_id": result.get("manufacturer_id"),
            "manufacturer_name": result.get("manufacturer_name"),
            "characteristics": result.get("characteristics"),
            "has_embedding": result.get("has_embedding", False),
        }
    )


@router.post("/search", response_model=CteSearchResponse)
async def search_cte_candidates(
    payload: CteSearchRequest,
    db: AsyncDatabase = Depends(get_db),
) -> CteSearchResponse:
    service = PricingStatisticsService(db)
    try:
        result = await service.search_cte_candidates(
            name=payload.name,
            characteristics=payload.characteristics,
            unit_value=payload.unit_value,
            supplier_inns=payload.supplier_inns,
            date_from=payload.date_from,
            date_to=payload.date_to,
            max_candidates=payload.max_candidates,
        )
    except EmbeddingRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return CteSearchResponse.model_validate(asdict(result))


@router.post("/manual", response_model=ManualCteCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_manual_cte(
    payload: ManualCteCreateRequest,
    db: AsyncDatabase = Depends(get_db),
) -> ManualCteCreateResponse:
    service = PricingStatisticsService(db)
    result = await service.create_manual_cte(
        name=payload.name,
        characteristics=payload.characteristics,
        category_name=payload.category_name,
        manufacturer_name=payload.manufacturer_name,
    )
    embedding_service = CteEmbeddingBackfillService(db)
    try:
        embedding_created = await embedding_service.generate_for_cte(int(result["id"]), force_rebuild=True)
    except EmbeddingRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return ManualCteCreateResponse.model_validate(
        {
            "cte_id": result["id"],
            "name": result["name"],
            "category_id": result["category_id"],
            "category_name": result["category_name"],
            "manufacturer_id": result.get("manufacturer_id"),
            "manufacturer_name": result.get("manufacturer_name"),
            "characteristics": result.get("characteristics"),
            "embedding_created": embedding_created,
        }
    )


@router.patch("/{cte_id}", response_model=CteDetailResponse)
async def update_cte(
    cte_id: int,
    payload: CteUpdateRequest,
    db: AsyncDatabase = Depends(get_db),
) -> CteDetailResponse:
    service = PricingStatisticsService(db)
    result = await service.update_cte(
        cte_id=cte_id,
        name=payload.name,
        category_name=payload.category_name,
        manufacturer_name=payload.manufacturer_name,
        clear_manufacturer=payload.clear_manufacturer,
        characteristics=payload.characteristics,
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"CTE {cte_id} not found")

    embedding_service = CteEmbeddingBackfillService(db)
    try:
        embedding_created = await embedding_service.generate_for_cte(cte_id, force_rebuild=True)
    except EmbeddingRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return CteDetailResponse.model_validate(
        {
            "cte_id": result["id"],
            "name": result["name"],
            "category_id": result["category_id"],
            "category_name": result["category_name"],
            "manufacturer_id": result.get("manufacturer_id"),
            "manufacturer_name": result.get("manufacturer_name"),
            "characteristics": result.get("characteristics"),
            "has_embedding": embedding_created,
        }
    )
