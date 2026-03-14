from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status

from app.db.deps import get_db
from app.db.session import AsyncDatabase
from app.schemas.analytics import (
    BasketNmckRequest,
    BasketNmckResponse,
    CteSearchRequest,
    CteSearchResponse,
    EmbeddingBackfillRequest,
    EmbeddingBackfillResponse,
    InputPricingEstimateRequest,
    InputPricingEstimateResponse,
    PricingEstimateRequest,
    PricingEstimateResponse,
)
from app.services.cte_embeddings import CteEmbeddingBackfillService, EmbeddingRuntimeError
from app.services.pricing_statistics import PricingStatisticsService


router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.post("/cte/search", response_model=CteSearchResponse)
async def search_cte_candidates(
    payload: CteSearchRequest,
    db: AsyncDatabase = Depends(get_db),
) -> CteSearchResponse:
    service = PricingStatisticsService(db)
    try:
        result = await service.search_cte_candidates(
            name=payload.name,
            characteristics=payload.characteristics,
            limit=payload.limit,
        )
    except EmbeddingRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return CteSearchResponse.model_validate(asdict(result))


@router.post("/pricing/cte/{cte_id}", response_model=PricingEstimateResponse)
async def estimate_cte_pricing(
    cte_id: int,
    payload: PricingEstimateRequest,
    db: AsyncDatabase = Depends(get_db),
) -> PricingEstimateResponse:
    service = PricingStatisticsService(db)
    try:
        result = await service.estimate_for_cte(
            cte_id=cte_id,
            target_region=payload.target_region,
            reference_date=payload.reference_date,
            vector_limit=payload.vector_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return PricingEstimateResponse.model_validate(asdict(result))


@router.post("/pricing/query", response_model=InputPricingEstimateResponse)
async def estimate_query_pricing(
    payload: InputPricingEstimateRequest,
    db: AsyncDatabase = Depends(get_db),
) -> InputPricingEstimateResponse:
    service = PricingStatisticsService(db)
    try:
        result = await service.estimate_for_input(
            name=payload.name,
            characteristics=payload.characteristics,
            target_region=payload.target_region,
            reference_date=payload.reference_date,
            vector_limit=payload.vector_limit,
        )
    except EmbeddingRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return InputPricingEstimateResponse.model_validate(asdict(result))


@router.post("/nmck", response_model=BasketNmckResponse)
async def estimate_basket_nmck(
    payload: BasketNmckRequest,
    db: AsyncDatabase = Depends(get_db),
) -> BasketNmckResponse:
    service = PricingStatisticsService(db)
    try:
        result = await service.estimate_nmck_for_basket(
            items=[item.model_dump() for item in payload.items],
            target_region=payload.target_region,
            reference_date=payload.reference_date,
            vector_limit=payload.vector_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return BasketNmckResponse.model_validate(asdict(result))


@router.post("/embeddings/backfill", response_model=EmbeddingBackfillResponse)
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
