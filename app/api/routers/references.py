from fastapi import APIRouter, Depends

from app.db.deps import get_db
from app.db.session import AsyncDatabase
from app.schemas.analytics import CategoryOptionsResponse, SupplierOptionsResponse, UnitOptionsResponse
from app.services.pricing_statistics import PricingStatisticsService


router = APIRouter(prefix="/references", tags=["references"])


@router.get("/suppliers", response_model=SupplierOptionsResponse)
async def list_suppliers(
    db: AsyncDatabase = Depends(get_db),
) -> SupplierOptionsResponse:
    service = PricingStatisticsService(db)
    items = await service.list_suppliers()
    return SupplierOptionsResponse(total=len(items), items=items)


@router.get("/units", response_model=UnitOptionsResponse)
async def list_units(
    db: AsyncDatabase = Depends(get_db),
) -> UnitOptionsResponse:
    service = PricingStatisticsService(db)
    items = await service.list_units()
    return UnitOptionsResponse(total=len(items), items=items)


@router.get("/categories", response_model=CategoryOptionsResponse)
async def list_categories(
    db: AsyncDatabase = Depends(get_db),
) -> CategoryOptionsResponse:
    service = PricingStatisticsService(db)
    items = await service.list_categories()
    return CategoryOptionsResponse(total=len(items), items=items)
