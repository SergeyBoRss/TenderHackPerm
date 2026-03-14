from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(slots=True)
class CteRow:
    cte_id: int
    name: str
    category_name: str
    manufacturer_name: str | None
    characteristics: dict[str, str]


@dataclass(slots=True)
class ContractRow:
    contract_id: int
    purchase_name: str
    quantity: Decimal
    unit_value: str
    procurement_method: str
    initial_price: Decimal
    final_price: Decimal
    reduction_percent: Decimal
    vat_rate: Decimal
    signed_at: date
    customer_inn: str
    customer_region: str | None
    supplier_inn: str
    supplier_region: str | None
    cte_id: int
    unit_price: Decimal


@dataclass(slots=True)
class ImportSummary:
    mode: str
    cte_file: str
    contracts_file: str
    cte_rows_processed: int
    contracts_rows_processed: int
    contracts_upserted: int
    contract_items_inserted: int
