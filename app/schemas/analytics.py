from datetime import date

from pydantic import BaseModel


class PricingEstimateRequest(BaseModel):
    target_region: str
    reference_date: date | None = None
    vector_limit: int | None = None


class InputPricingEstimateRequest(BaseModel):
    name: str
    characteristics: dict | None = None
    target_region: str
    reference_date: date | None = None
    vector_limit: int | None = None


class CteSearchRequest(BaseModel):
    name: str
    characteristics: dict | None = None
    limit: int = 20


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


class InputPricingEstimateResponse(BaseModel):
    query_name: str
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
    total_candidates: int
    candidates: list[CteSearchCandidateResponse]


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


class EmbeddingBackfillResponse(BaseModel):
    processed_cte: int
    updated_embeddings: int
