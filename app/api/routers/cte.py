from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status

from app.db.deps import get_db
from app.db.session import AsyncDatabase
from app.schemas.analytics import CteSearchRequest, CteSearchResponse, ManualCteCreateRequest, ManualCteCreateResponse
from app.services.cte_embeddings import CteEmbeddingBackfillService, EmbeddingRuntimeError
from app.services.pricing_statistics import PricingStatisticsService


router = APIRouter(prefix="/cte", tags=["cte"])


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
