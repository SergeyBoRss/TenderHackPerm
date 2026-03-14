from datetime import date

from pydantic import BaseModel


class PricingEstimateRequest(BaseModel):
    target_region: str
    target_quantity: float | None = None
    reference_date: date | None = None
    vector_limit: int | None = None


class CteSearchRequest(BaseModel):
    name: str
    characteristics: dict | str | None = None
    unit_value: str | None = None
    supplier_inns: list[str] | None = None
    date_from: date | None = None
    date_to: date | None = None
    max_candidates: int = 20


class BasketNmckItemRequest(BaseModel):
    cte_ids: list[int]
    quantity: float
    item_name: str | None = None


class BasketNmckRequest(BaseModel):
    target_region: str
    items: list[BasketNmckItemRequest]
    reference_date: date | None = None
    vector_limit: int | None = None


class EmbeddingBackfillRequest(BaseModel):
    batch_size: int | None = None
    force_rebuild: bool = False


class EmbeddingExcelImportRequest(BaseModel):
    file_path: str | None = None
    batch_size: int = 1000
    truncate: bool = False


class PricingEstimateResponse(BaseModel):
    cte_id: int
    target_region: str
    reference_date: date
    estimated_unit_price: float | None
    total_candidates: int
    filtered_candidates: int
    exact_candidates: int
    vector_candidates: int
    q1: float | None
    q3: float | None
    iqr_low: float | None
    iqr_high: float | None


class CteSearchCandidateResponse(BaseModel):
    cte_id: int
    name: str
    category_id: int
    category_name: str
    manufacturer_id: int | None
    manufacturer_name: str | None
    characteristics: dict | str | None = None
    exact_name_match: bool
    embedding_similarity: float | None = None


class CteSearchResponse(BaseModel):
    query_name: str
    applied_unit_value: str | None = None
    applied_supplier_inns: list[str] | None = None
    applied_date_from: date | None = None
    applied_date_to: date | None = None
    total_candidates: int
    candidates: list[CteSearchCandidateResponse]


class SupplierOptionResponse(BaseModel):
    id: int
    name: str | None = None
    inn: str | None = None
    region: str | None = None


class SupplierOptionsResponse(BaseModel):
    total: int
    items: list[SupplierOptionResponse]


class UnitOptionResponse(BaseModel):
    id: int
    value: str


class UnitOptionsResponse(BaseModel):
    total: int
    items: list[UnitOptionResponse]


class CategoryOptionResponse(BaseModel):
    id: int
    name: str


class CategoryOptionsResponse(BaseModel):
    total: int
    items: list[CategoryOptionResponse]


class ManualCteCreateRequest(BaseModel):
    name: str
    characteristics: dict | str | None = None
    category_name: str
    manufacturer_name: str | None = None


class ManualCteCreateResponse(BaseModel):
    cte_id: int
    name: str
    category_id: int
    category_name: str
    manufacturer_id: int | None = None
    manufacturer_name: str | None = None
    characteristics: dict | str | None = None
    embedding_created: bool


class CteDetailResponse(BaseModel):
    cte_id: int
    name: str
    category_id: int
    category_name: str
    manufacturer_id: int | None = None
    manufacturer_name: str | None = None
    characteristics: dict | str | None = None
    has_embedding: bool


class CteUpdateRequest(BaseModel):
    name: str | None = None
    category_name: str | None = None
    manufacturer_name: str | None = None
    clear_manufacturer: bool = False
    characteristics: dict | str | None = None


class BasketNmckItemResponse(BaseModel):
    item_name: str | None = None
    quantity: float
    estimated_unit_price: float | None
    line_total: float | None
    selected_cte_count: int
    selected_ctes: list["BasketNmckSelectedCteResponse"]


class BasketNmckSelectedCteResponse(BaseModel):
    cte_id: int
    cte_name: str
    estimated_unit_price: float | None


class BasketNmckResponse(BaseModel):
    target_region: str
    reference_date: date
    total_positions: int
    positions_with_price: int
    estimated_total_price: float
    items: list[BasketNmckItemResponse]


class WeightExplainResponse(BaseModel):
    value: float
    reason: str


class NmckCandidateExplainResponse(BaseModel):
    contract_id: int
    contract_item_id: int
    candidate_cte_id: int
    candidate_quantity: float | None
    unit_price: float
    signed_at: date
    customer_region: str | None = None
    source_exact: bool
    source_vector: bool
    embedding_similarity: float | None = None
    exact_weight: WeightExplainResponse
    region_weight: WeightExplainResponse
    embedding_weight: WeightExplainResponse
    time_weight: WeightExplainResponse
    quantity_weight: WeightExplainResponse
    final_weight: WeightExplainResponse
    used_in_median: bool
    exclusion_reason: str | None = None


class BasketNmckSelectedCteExplainResponse(BaseModel):
    cte_id: int
    cte_name: str
    estimated_unit_price: float | None
    total_candidates: int
    filtered_candidates: int
    exact_candidates: int
    vector_candidates: int
    q1: float | None
    q3: float | None
    iqr_low: float | None
    iqr_high: float | None
    min_candidate_unit_price: float | None
    max_candidate_unit_price: float | None
    min_filtered_unit_price: float | None
    max_filtered_unit_price: float | None
    considered_contracts: list[NmckCandidateExplainResponse]
    excluded_contracts: list[NmckCandidateExplainResponse]


class BasketNmckExplainItemResponse(BaseModel):
    item_name: str | None = None
    quantity: float
    estimated_unit_price: float | None
    line_total: float | None
    selected_cte_count: int
    selected_ctes: list[BasketNmckSelectedCteExplainResponse]


class BasketNmckExplainResponse(BaseModel):
    target_region: str
    reference_date: date
    total_positions: int
    positions_with_price: int
    estimated_total_price: float
    items: list[BasketNmckExplainItemResponse]


class EmbeddingBackfillResponse(BaseModel):
    processed_cte: int
    updated_embeddings: int


class EmbeddingExcelImportResponse(BaseModel):
    file_path: str
    imported_embeddings: int
