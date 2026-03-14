from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status

from app.db.deps import get_db
from app.db.session import AsyncDatabase
from app.schemas.analytics import BasketNmckRequest, BasketNmckResponse, PricingEstimateRequest, PricingEstimateResponse
from app.services.pricing_statistics import PricingStatisticsService


router = APIRouter(prefix="/analytics", tags=["analytics"])


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
            target_quantity=payload.target_quantity,
            reference_date=payload.reference_date,
            vector_limit=payload.vector_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return PricingEstimateResponse.model_validate(asdict(result))

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
