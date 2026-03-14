from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status

from app.db.deps import get_db
from app.db.session import AsyncDatabase
from app.schemas.analytics import BasketNmckExplainResponse, BasketNmckRequest
from app.services.pricing_statistics import PricingStatisticsService


router = APIRouter(prefix="/analytics/explain", tags=["analytics-explain"])


@router.post("/nmck", response_model=BasketNmckExplainResponse)
async def explain_basket_nmck(
    payload: BasketNmckRequest,
    db: AsyncDatabase = Depends(get_db),
) -> BasketNmckExplainResponse:
    service = PricingStatisticsService(db)
    try:
        result = await service.explain_nmck_for_basket(
            items=[item.model_dump() for item in payload.items],
            target_region=payload.target_region,
            reference_date=payload.reference_date,
            vector_limit=payload.vector_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return BasketNmckExplainResponse.model_validate(asdict(result))
