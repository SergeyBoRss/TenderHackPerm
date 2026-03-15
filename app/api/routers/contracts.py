from fastapi import APIRouter, Depends, HTTPException, status

from app.db.deps import get_db
from app.db.session import AsyncDatabase
from app.schemas.analytics import ContractDetailResponse
from app.services.pricing_statistics import PricingStatisticsService


router = APIRouter(prefix="/contracts", tags=["contracts"])


@router.get("/{contract_id}", response_model=ContractDetailResponse)
async def get_contract(
    contract_id: int,
    db: AsyncDatabase = Depends(get_db),
) -> ContractDetailResponse:
    service = PricingStatisticsService(db)
    result = await service.get_contract(contract_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Contract {contract_id} not found")

    return ContractDetailResponse.model_validate(
        {
            "id": result["id"],
            "purchase_name_id": result["purchase_name_id"],
            "purchase_name": result["purchase_name"],
            "procurement_method_id": result["procurement_method_id"],
            "procurement_method": result["procurement_method"],
            "initial_price": float(result["initial_price"]),
            "final_price": float(result["final_price"]),
            "reduction_percent": float(result["reduction_percent"]),
            "vat_rate": float(result["vat_rate"]),
            "signed_at": result["signed_at"],
            "customer": {
                "id": result["customer_id"],
                "name": result.get("customer_name"),
                "inn": result.get("customer_inn"),
                "region": result.get("customer_region"),
            },
            "supplier": {
                "id": result["supplier_id"],
                "name": result.get("supplier_name"),
                "inn": result.get("supplier_inn"),
                "region": result.get("supplier_region"),
            },
            "items": [
                {
                    "id": item["id"],
                    "cte_id": item["cte_id"],
                    "cte_name": item["cte_name"],
                    "quantity": float(item["quantity"]),
                    "unit_id": item["unit_id"],
                    "unit_value": item["unit_value"],
                    "unit_price": float(item["unit_price"]),
                    "line_total": float(item["line_total"]),
                }
                for item in result["items"]
            ],
        }
    )
