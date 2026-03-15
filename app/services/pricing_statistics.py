from dataclasses import dataclass
from datetime import date
import logging
import math
from statistics import median
from statistics import quantiles
from uuid import uuid4

from app.core.config import settings
from app.db.session import AsyncDatabase
from app.repositories.procurement_analysis import ProcurementAnalysisRepository
from app.services.cte_embeddings import EmbeddingRuntimeError, TransformerEmbeddingClient
from app.services.cte_search_text import CteSearchTextBuilder
from app.services.region_weights import RegionWeightService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PricingEstimate:
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


@dataclass(slots=True)
class CteSearchCandidate:
    cte_id: int
    name: str
    category_id: int
    category_name: str
    manufacturer_id: int | None
    manufacturer_name: str | None
    characteristics: dict | str | None
    exact_name_match: bool
    embedding_similarity: float | None


@dataclass(slots=True)
class CteSearchResult:
    query_name: str
    applied_unit_id: int | None
    applied_category_ids: list[int] | None
    total_candidates: int
    candidates: list[CteSearchCandidate]


@dataclass(slots=True)
class BasketNmckItemEstimate:
    item_name: str | None
    quantity: float
    estimated_unit_price: float | None
    line_total: float | None
    selected_cte_count: int
    selected_ctes: list["BasketNmckSelectedCteEstimate"]


@dataclass(slots=True)
class BasketNmckSelectedCteEstimate:
    cte_id: int
    cte_name: str
    estimated_unit_price: float | None


@dataclass(slots=True)
class BasketNmckEstimate:
    target_region: str
    reference_date: date
    total_positions: int
    positions_with_price: int
    estimated_total_price: float
    items: list[BasketNmckItemEstimate]


@dataclass(slots=True)
class WeightExplain:
    value: float
    reason: str


@dataclass(slots=True)
class NmckCandidateExplain:
    contract_id: int
    contract_item_id: int
    candidate_cte_id: int
    candidate_cte_name: str
    supplier_name: str | None
    candidate_quantity: float | None
    unit_price: float
    contract_total_cost: float | None
    signed_at: date
    customer_region: str | None
    source_exact: bool
    source_vector: bool
    embedding_similarity: float | None
    exact_weight: WeightExplain
    region_weight: WeightExplain
    embedding_weight: WeightExplain
    time_weight: WeightExplain
    quantity_weight: WeightExplain
    final_weight: WeightExplain
    used_in_median: bool
    exclusion_reason: str | None


@dataclass(slots=True)
class BasketNmckSelectedCteExplain:
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
    considered_contracts: list[NmckCandidateExplain]
    excluded_contracts: list[NmckCandidateExplain]


@dataclass(slots=True)
class BasketNmckExplainItemEstimate:
    item_name: str | None
    quantity: float
    estimated_unit_price: float | None
    line_total: float | None
    selected_cte_count: int
    selected_ctes: list[BasketNmckSelectedCteExplain]


@dataclass(slots=True)
class BasketNmckExplainEstimate:
    target_region: str
    reference_date: date
    total_positions: int
    positions_with_price: int
    estimated_total_price: float
    items: list[BasketNmckExplainItemEstimate]


class PricingStatisticsService:
    def __init__(self, db: AsyncDatabase):
        self.db = db
        self.repository = ProcurementAnalysisRepository(db)
        self.region_weights = RegionWeightService(self.repository)
        self.embedding_client = TransformerEmbeddingClient()

    async def list_suppliers(self) -> list[dict]:
        return await self.repository.fetch_suppliers()

    async def list_units(self) -> list[dict]:
        return await self.repository.fetch_units()

    async def list_categories(self) -> list[dict]:
        return await self.repository.fetch_categories()

    async def create_manual_cte(
        self,
        *,
        name: str,
        characteristics: dict | str | None,
        category_name: str,
        manufacturer_name: str | None,
    ) -> dict:
        normalized_characteristics = CteSearchTextBuilder.normalize_characteristics(characteristics)
        cte_id = -int(uuid4().int % 9_000_000_000_000_000_000) - 1
        return await self.repository.create_manual_cte(
            cte_id=cte_id,
            name=name.strip(),
            category_name=category_name.strip(),
            manufacturer_name=manufacturer_name.strip() if manufacturer_name else None,
            characteristics=normalized_characteristics,
        )

    async def get_cte(self, cte_id: int) -> dict | None:
        result = await self.repository.fetch_target_cte_context(cte_id)
        if not result:
            return None
        result["has_embedding"] = bool(result.get("embedding_text"))
        return result

    async def update_cte(
        self,
        *,
        cte_id: int,
        name: str | None,
        category_name: str | None,
        manufacturer_name: str | None,
        clear_manufacturer: bool,
        characteristics: dict | str | None,
    ) -> dict | None:
        normalized_characteristics = (
            CteSearchTextBuilder.normalize_characteristics(characteristics) if characteristics is not None else None
        )
        result = await self.repository.update_cte(
            cte_id=cte_id,
            name=name.strip() if name is not None else None,
            category_name=category_name.strip() if category_name is not None else None,
            manufacturer_name=manufacturer_name.strip() if manufacturer_name else None,
            clear_manufacturer=clear_manufacturer,
            characteristics=normalized_characteristics,
        )
        if result is None:
            return None
        result["has_embedding"] = False
        return result

    async def estimate_for_cte(
        self,
        cte_id: int,
        target_region: str,
        target_quantity: float | None = None,
        reference_date: date | None = None,
        vector_limit: int | None = None,
    ) -> PricingEstimate:
        estimate, _, _ = await self._estimate_for_cte_with_details(
            cte_id=cte_id,
            target_region=target_region,
            target_quantity=target_quantity,
            reference_date=reference_date,
            vector_limit=vector_limit,
        )
        return estimate

    async def _estimate_for_cte_with_details(
        self,
        *,
        cte_id: int,
        target_region: str,
        target_quantity: float | None,
        reference_date: date | None,
        vector_limit: int | None,
    ) -> tuple[PricingEstimate, dict, list[dict]]:
        target = await self.repository.fetch_target_cte_context(cte_id)
        if not target:
            raise ValueError(f"CTE {cte_id} not found")

        current_reference_date = reference_date or date.today()
        exact_candidates = await self.repository.fetch_exact_candidates(
            target_category_id=int(target["category_id"]),
            target_manufacturer_id=int(target["manufacturer_id"]) if target.get("manufacturer_id") else None,
            target_embedding_text=target.get("embedding_text"),
        )

        vector_candidates: list[dict] = []
        if target.get("embedding_text"):
            vector_candidates = await self.repository.fetch_vector_candidates(
                target_embedding_text=target["embedding_text"],
                limit=vector_limit or settings.analytics_vector_limit,
            )

        merged_candidates: dict[int, dict] = {}
        for candidate in exact_candidates:
            enriched = dict(candidate)
            enriched["source_exact"] = True
            enriched["source_vector"] = False
            merged_candidates[int(candidate["contract_item_id"])] = enriched

        for candidate in vector_candidates:
            key = int(candidate["contract_item_id"])
            if key in merged_candidates:
                merged_candidates[key]["source_vector"] = True
                if candidate.get("embedding_similarity") is not None:
                    merged_candidates[key]["embedding_similarity"] = candidate["embedding_similarity"]
                continue
            enriched = dict(candidate)
            enriched["source_exact"] = False
            enriched["source_vector"] = True
            merged_candidates[key] = enriched

        total_candidates = len(merged_candidates)
        q1, q3, low, high = self._iqr_bounds(list(merged_candidates.values()))
        filtered_candidates = self._filter_outliers(list(merged_candidates.values()))
        filtered_candidate_ids = {int(candidate["contract_item_id"]) for candidate in filtered_candidates}

        weighted_points: list[tuple[float, float]] = []
        candidate_debug_rows: list[dict] = []
        for candidate in merged_candidates.values():
            exact_branch = await self._exact_branch_explanation(target, candidate, target_region)
            embedding_weight = self._embedding_weight(candidate.get("embedding_similarity"))
            embedding_reason = self._embedding_weight_reason(candidate.get("embedding_similarity"), embedding_weight)
            time_weight = self._time_weight(candidate["signed_at"], current_reference_date)
            time_reason = self._time_weight_reason(candidate["signed_at"], current_reference_date, time_weight)
            quantity_weight = self._quantity_weight(
                target_quantity=target_quantity,
                candidate_quantity=float(candidate["quantity"]) if candidate.get("quantity") is not None else None,
            )
            quantity_reason = self._quantity_weight_reason(
                target_quantity=target_quantity,
                candidate_quantity=float(candidate["quantity"]) if candidate.get("quantity") is not None else None,
                quantity_weight=quantity_weight,
            )
            final_weight = exact_branch["exact_weight"] * embedding_weight * time_weight * quantity_weight
            included_after_iqr = int(candidate["contract_item_id"]) in filtered_candidate_ids
            exclusion_reason = self._candidate_exclusion_reason(
                unit_price=float(candidate["unit_price"]),
                included_after_iqr=included_after_iqr,
                final_weight=final_weight,
                low=low,
                high=high,
            )
            used_in_median = included_after_iqr and final_weight > 0

            candidate_debug_rows.append(
                {
                    "contract_id": int(candidate["contract_id"]),
                    "contract_item_id": int(candidate["contract_item_id"]),
                    "cte_id": int(candidate["cte_id"]),
                    "candidate_cte_name": str(candidate["candidate_cte_name"]),
                    "supplier_name": candidate.get("supplier_name"),
                    "quantity": float(candidate["quantity"]) if candidate.get("quantity") is not None else None,
                    "unit_price": float(candidate["unit_price"]),
                    "contract_total_cost": (
                        float(candidate["unit_price"]) * float(candidate["quantity"])
                        if candidate.get("quantity") is not None
                        else None
                    ),
                    "signed_at": candidate["signed_at"],
                    "customer_region": candidate.get("customer_region"),
                    "source_exact": bool(candidate.get("source_exact")),
                    "source_vector": bool(candidate.get("source_vector")),
                    "embedding_similarity": float(candidate["embedding_similarity"])
                    if candidate.get("embedding_similarity") is not None
                    else None,
                    "exact_weight": exact_branch["exact_weight"],
                    "exact_weight_reason": exact_branch["exact_reason"],
                    "region_weight": exact_branch["region_weight"],
                    "region_weight_reason": exact_branch["region_reason"],
                    "embedding_weight": embedding_weight,
                    "embedding_weight_reason": embedding_reason,
                    "time_weight": time_weight,
                    "time_weight_reason": time_reason,
                    "quantity_weight": quantity_weight,
                    "quantity_weight_reason": quantity_reason,
                    "final_weight": final_weight,
                    "final_weight_reason": (
                        "Итоговый вес получен как произведение exact_weight, embedding_weight, "
                        "time_weight и quantity_weight"
                    ),
                    "included_after_iqr": included_after_iqr,
                    "used_in_median": used_in_median,
                    "exclusion_reason": exclusion_reason,
                }
            )

            if not used_in_median:
                continue
            weighted_points.append((float(candidate["unit_price"]), final_weight))

        estimated_unit_price = self._weighted_median(weighted_points)

        return (
            PricingEstimate(
                cte_id=cte_id,
                target_region=target_region,
                reference_date=current_reference_date,
                estimated_unit_price=estimated_unit_price,
                total_candidates=total_candidates,
                filtered_candidates=len(filtered_candidates),
                exact_candidates=sum(1 for item in merged_candidates.values() if item["source_exact"]),
                vector_candidates=sum(1 for item in merged_candidates.values() if item["source_vector"]),
                q1=q1,
                q3=q3,
                iqr_low=low,
                iqr_high=high,
            ),
            target,
            candidate_debug_rows,
        )

    async def search_cte_candidates(
        self,
        name: str,
        characteristics: dict | str | None,
        unit_id: int | None,
        category_ids: list[int] | None,
        max_candidates: int,
    ) -> CteSearchResult:
        capped_limit = max(1, min(max_candidates, 100))
        query_text = CteSearchTextBuilder.build(
            name=name,
            category_name=None,
            manufacturer_name=None,
            characteristics=characteristics,
        )
        query_embedding = await self.embedding_client.embed_query(query_text)
        query_embedding_text = self.embedding_client.to_vector_literal(query_embedding)

        normalized_category_ids = sorted(set(category_ids)) if category_ids else None
        exact_matches = await self.repository.fetch_cte_name_exact_matches(
            query_name=name,
            unit_id=unit_id,
            category_ids=normalized_category_ids,
            limit=capped_limit,
        )
        vector_matches = await self.repository.fetch_cte_vector_matches(
            target_embedding_text=query_embedding_text,
            unit_id=unit_id,
            category_ids=normalized_category_ids,
            limit=capped_limit,
        )

        merged: dict[int, dict] = {}
        for candidate in exact_matches:
            merged[int(candidate["cte_id"])] = dict(candidate)

        for candidate in vector_matches:
            key = int(candidate["cte_id"])
            if key in merged:
                if candidate.get("embedding_similarity") is not None:
                    merged[key]["embedding_similarity"] = candidate["embedding_similarity"]
                continue
            merged[key] = dict(candidate)

        ordered = sorted(
            merged.values(),
            key=lambda item: (
                not bool(item.get("exact_name_match")),
                -(float(item["embedding_similarity"]) if item.get("embedding_similarity") is not None else -1.0),
                int(item["cte_id"]),
            ),
        )[:capped_limit]

        return CteSearchResult(
            query_name=name,
            applied_unit_id=unit_id,
            applied_category_ids=normalized_category_ids,
            total_candidates=len(ordered),
            candidates=[
                CteSearchCandidate(
                    cte_id=int(item["cte_id"]),
                    name=str(item["name"]),
                    category_id=int(item["category_id"]),
                    category_name=str(item["category_name"]),
                    manufacturer_id=int(item["manufacturer_id"]) if item.get("manufacturer_id") is not None else None,
                    manufacturer_name=item.get("manufacturer_name"),
                    characteristics=item.get("characteristics"),
                    exact_name_match=bool(item.get("exact_name_match")),
                    embedding_similarity=float(item["embedding_similarity"])
                    if item.get("embedding_similarity") is not None
                    else None,
                )
                for item in ordered
            ],
        )

    async def estimate_nmck_for_basket(
        self,
        *,
        items: list[dict],
        target_region: str,
        reference_date: date | None = None,
        vector_limit: int | None = None,
    ) -> BasketNmckEstimate:
        current_reference_date = reference_date or date.today()
        results: list[BasketNmckItemEstimate] = []
        estimated_total_price = 0.0
        positions_with_price = 0

        for item in items:
            cte_ids = [int(value) for value in item["cte_ids"]]
            quantity = float(item["quantity"])
            selected_ctes: list[BasketNmckSelectedCteEstimate] = []
            unit_prices: list[float] = []

            for cte_id in cte_ids:
                estimate, target, candidate_debug_rows = await self._estimate_for_cte_with_details(
                    cte_id=cte_id,
                    target_region=target_region,
                    target_quantity=quantity,
                    reference_date=current_reference_date,
                    vector_limit=vector_limit,
                )
                selected_ctes.append(
                    BasketNmckSelectedCteEstimate(
                        cte_id=cte_id,
                        cte_name=str(target["name"]),
                        estimated_unit_price=estimate.estimated_unit_price,
                    )
                )
                if estimate.estimated_unit_price is not None:
                    unit_prices.append(float(estimate.estimated_unit_price))
                self._log_nmck_cte_details(
                    item_name=item.get("item_name"),
                    quantity=quantity,
                    target_region=target_region,
                    target=target,
                    estimate=estimate,
                    candidate_debug_rows=candidate_debug_rows,
                )

            estimated_unit_price = median(unit_prices) if unit_prices else None
            line_total = None
            if estimated_unit_price is not None:
                line_total = estimated_unit_price * quantity
                estimated_total_price += line_total
                positions_with_price += 1

            results.append(
                BasketNmckItemEstimate(
                    item_name=item.get("item_name"),
                    quantity=quantity,
                    estimated_unit_price=estimated_unit_price,
                    line_total=line_total,
                    selected_cte_count=len(selected_ctes),
                    selected_ctes=selected_ctes,
                )
            )

        return BasketNmckEstimate(
            target_region=target_region,
            reference_date=current_reference_date,
            total_positions=len(items),
            positions_with_price=positions_with_price,
            estimated_total_price=estimated_total_price,
            items=results,
        )

    async def explain_nmck_for_basket(
        self,
        *,
        items: list[dict],
        target_region: str,
        reference_date: date | None = None,
        vector_limit: int | None = None,
    ) -> BasketNmckExplainEstimate:
        current_reference_date = reference_date or date.today()
        results: list[BasketNmckExplainItemEstimate] = []
        estimated_total_price = 0.0
        positions_with_price = 0

        for item in items:
            cte_ids = [int(value) for value in item["cte_ids"]]
            quantity = float(item["quantity"])
            selected_ctes: list[BasketNmckSelectedCteExplain] = []
            unit_prices: list[float] = []

            for cte_id in cte_ids:
                estimate, target, candidate_debug_rows = await self._estimate_for_cte_with_details(
                    cte_id=cte_id,
                    target_region=target_region,
                    target_quantity=quantity,
                    reference_date=current_reference_date,
                    vector_limit=vector_limit,
                )
                if estimate.estimated_unit_price is not None:
                    unit_prices.append(float(estimate.estimated_unit_price))

                considered_contracts = [self._candidate_explain_from_row(row) for row in candidate_debug_rows]
                excluded_contracts = [candidate for candidate in considered_contracts if not candidate.used_in_median]
                filtered_unit_prices = [
                    candidate.unit_price for candidate in considered_contracts if candidate.used_in_median
                ]
                all_unit_prices = [candidate.unit_price for candidate in considered_contracts]

                selected_ctes.append(
                    BasketNmckSelectedCteExplain(
                        cte_id=cte_id,
                        cte_name=str(target["name"]),
                        estimated_unit_price=estimate.estimated_unit_price,
                        total_candidates=estimate.total_candidates,
                        filtered_candidates=estimate.filtered_candidates,
                        exact_candidates=estimate.exact_candidates,
                        vector_candidates=estimate.vector_candidates,
                        q1=estimate.q1,
                        q3=estimate.q3,
                        iqr_low=estimate.iqr_low,
                        iqr_high=estimate.iqr_high,
                        min_candidate_unit_price=min(all_unit_prices) if all_unit_prices else None,
                        max_candidate_unit_price=max(all_unit_prices) if all_unit_prices else None,
                        min_filtered_unit_price=min(filtered_unit_prices) if filtered_unit_prices else None,
                        max_filtered_unit_price=max(filtered_unit_prices) if filtered_unit_prices else None,
                        considered_contracts=considered_contracts,
                        excluded_contracts=excluded_contracts,
                    )
                )

            estimated_unit_price = median(unit_prices) if unit_prices else None
            line_total = None
            if estimated_unit_price is not None:
                line_total = estimated_unit_price * quantity
                estimated_total_price += line_total
                positions_with_price += 1

            results.append(
                BasketNmckExplainItemEstimate(
                    item_name=item.get("item_name"),
                    quantity=quantity,
                    estimated_unit_price=estimated_unit_price,
                    line_total=line_total,
                    selected_cte_count=len(selected_ctes),
                    selected_ctes=selected_ctes,
                )
            )

        return BasketNmckExplainEstimate(
            target_region=target_region,
            reference_date=current_reference_date,
            total_positions=len(items),
            positions_with_price=positions_with_price,
            estimated_total_price=estimated_total_price,
            items=results,
        )

    def _log_nmck_cte_details(
        self,
        *,
        item_name: str | None,
        quantity: float,
        target_region: str,
        target: dict,
        estimate: PricingEstimate,
        candidate_debug_rows: list[dict],
    ) -> None:
        logger.info(
            "NMCK item debug: item_name=%s cte_id=%s cte_name=%s quantity=%s target_region=%s estimated_unit_price=%s total_candidates=%s filtered_candidates=%s logged_candidates=%s q1=%s q3=%s iqr_low=%s iqr_high=%s",
            item_name,
            estimate.cte_id,
            target["name"],
            quantity,
            target_region,
            estimate.estimated_unit_price,
            estimate.total_candidates,
            estimate.filtered_candidates,
            min(3, len(candidate_debug_rows)),
            estimate.q1,
            estimate.q3,
            estimate.iqr_low,
            estimate.iqr_high,
        )
        top_candidates = sorted(
            candidate_debug_rows,
            key=lambda row: (not row["used_in_median"], -row["final_weight"], row["unit_price"]),
        )[:3]
        for candidate in top_candidates:
            logger.info(
                "NMCK candidate debug: item_name=%s cte_id=%s contract_id=%s contract_item_id=%s candidate_cte_id=%s candidate_quantity=%s unit_price=%s signed_at=%s customer_region=%s source_exact=%s source_vector=%s embedding_similarity=%s exact_weight=%s embedding_weight=%s time_weight=%s quantity_weight=%s final_weight=%s used_in_median=%s exclusion_reason=%s",
                item_name,
                estimate.cte_id,
                candidate["contract_id"],
                candidate["contract_item_id"],
                candidate["cte_id"],
                candidate["quantity"],
                candidate["unit_price"],
                candidate["signed_at"],
                candidate["customer_region"],
                candidate["source_exact"],
                candidate["source_vector"],
                candidate["embedding_similarity"],
                candidate["exact_weight"],
                candidate["embedding_weight"],
                candidate["time_weight"],
                candidate["quantity_weight"],
                candidate["final_weight"],
                candidate["used_in_median"],
                candidate["exclusion_reason"],
            )

    async def _exact_branch_explanation(self, target: dict, candidate: dict, target_region: str) -> dict:
        same_category = int(candidate["category_id"]) == int(target["category_id"])
        same_manufacturer = bool(target.get("manufacturer_id")) and candidate.get("manufacturer_id") == target.get(
            "manufacturer_id"
        )
        same_region = self._normalize_region(candidate.get("customer_region")) == self._normalize_region(target_region)

        if same_category and same_manufacturer and same_region:
            return {
                "exact_weight": 1.0,
                "exact_reason": "Совпали категория, производитель и регион; exact-ветка получила максимальный вес",
                "region_weight": 1.0,
                "region_reason": "Регион полностью совпал с целевым, дополнительное снижение не применялось",
            }

        region_info = await self.region_weights.explain_weight(target_region, candidate.get("customer_region"))
        regional_weight = float(region_info["weight"])
        if same_category and same_manufacturer:
            return {
                "exact_weight": regional_weight,
                "exact_reason": (
                    "Совпали категория и производитель, поэтому exact-ветка опирается на региональный вес без "
                    "дополнительного штрафа"
                ),
                "region_weight": regional_weight,
                "region_reason": str(region_info["reason"]),
            }
        if same_category:
            return {
                "exact_weight": regional_weight * settings.analytics_category_only_multiplier,
                "exact_reason": (
                    "Совпала только категория, поэтому применен региональный вес и понижающий коэффициент "
                    f"{settings.analytics_category_only_multiplier:.4f}"
                ),
                "region_weight": regional_weight,
                "region_reason": str(region_info["reason"]),
            }
        return {
            "exact_weight": regional_weight * settings.analytics_fallback_multiplier,
            "exact_reason": (
                "Категория и производитель не совпали, поэтому применен fallback exact-ветки с коэффициентом "
                f"{settings.analytics_fallback_multiplier:.4f}"
            ),
            "region_weight": regional_weight,
            "region_reason": str(region_info["reason"]),
        }

    @staticmethod
    def _normalize_region(region: str | None) -> str:
        if not region:
            return ""
        return " ".join(region.strip().lower().replace("ё", "е").split())

    @staticmethod
    def _embedding_weight(similarity: float | None) -> float:
        if similarity is None:
            return settings.analytics_missing_embedding_weight
        return max(0.0, min(1.0, float(similarity)))

    @staticmethod
    def _embedding_weight_reason(similarity: float | None, weight: float) -> str:
        if similarity is None:
            return (
                "Для кандидата нет embedding similarity, поэтому использован вес отсутствующего embedding "
                f"{settings.analytics_missing_embedding_weight:.4f}"
            )
        return f"Вес embedding равен cosine similarity кандидата, после ограничения до диапазона 0..1: {weight:.4f}"

    @staticmethod
    def _quantity_weight(target_quantity: float | None, candidate_quantity: float | None) -> float:
        if target_quantity is None or candidate_quantity is None:
            return 1.0
        if target_quantity <= 0 or candidate_quantity <= 0:
            return 1.0
        quantity_distance = abs(math.log(target_quantity + 1.0) - math.log(candidate_quantity + 1.0))
        raw_weight = math.exp(-settings.analytics_quantity_weight_alpha * quantity_distance)
        return max(settings.analytics_quantity_weight_min, raw_weight)

    @staticmethod
    def _quantity_weight_reason(
        target_quantity: float | None,
        candidate_quantity: float | None,
        quantity_weight: float,
    ) -> str:
        if target_quantity is None:
            return "Целевой объем не передан, поэтому quantity_weight принят равным 1.0"
        if candidate_quantity is None:
            return "У исторической позиции нет количества, поэтому quantity_weight принят равным 1.0"
        if target_quantity <= 0 or candidate_quantity <= 0:
            return "Одно из количеств неположительное, поэтому quantity_weight принят равным 1.0"
        quantity_distance = abs(math.log(target_quantity + 1.0) - math.log(candidate_quantity + 1.0))
        return (
            f"Логарифмическая дистанция объемов {quantity_distance:.4f}; итоговый quantity_weight после "
            f"экспоненциального затухания и нижней границы равен {quantity_weight:.4f}"
        )

    @staticmethod
    def _time_weight(signed_at: date, reference_date: date) -> float:
        age_days = max(0, (reference_date - signed_at).days)
        return 0.5 ** (age_days / settings.analytics_time_half_life_days)

    @staticmethod
    def _time_weight_reason(signed_at: date, reference_date: date, time_weight: float) -> str:
        age_days = max(0, (reference_date - signed_at).days)
        return (
            f"Контракту {age_days} дней относительно даты расчета; time_weight рассчитан по half-life "
            f"{settings.analytics_time_half_life_days:.1f} дней и равен {time_weight:.4f}"
        )

    @staticmethod
    def _candidate_exclusion_reason(
        *,
        unit_price: float,
        included_after_iqr: bool,
        final_weight: float,
        low: float | None,
        high: float | None,
    ) -> str | None:
        if low is not None and unit_price < low:
            return f"Цена {unit_price:.4f} ниже нижней IQR-границы {low:.4f}"
        if high is not None and unit_price > high:
            return f"Цена {unit_price:.4f} выше верхней IQR-границы {high:.4f}"
        if not included_after_iqr:
            return "Кандидат исключен после IQR-фильтрации"
        if final_weight <= 0:
            return "Итоговый вес кандидата равен нулю, поэтому он не участвует во взвешенной медиане"
        return None

    @staticmethod
    def _candidate_explain_from_row(row: dict) -> NmckCandidateExplain:
        return NmckCandidateExplain(
            contract_id=int(row["contract_id"]),
            contract_item_id=int(row["contract_item_id"]),
            candidate_cte_id=int(row["cte_id"]),
            candidate_cte_name=str(row["candidate_cte_name"]),
            supplier_name=row.get("supplier_name"),
            candidate_quantity=row["quantity"],
            unit_price=float(row["unit_price"]),
            contract_total_cost=float(row["contract_total_cost"]) if row.get("contract_total_cost") is not None else None,
            signed_at=row["signed_at"],
            customer_region=row["customer_region"],
            source_exact=bool(row["source_exact"]),
            source_vector=bool(row["source_vector"]),
            embedding_similarity=row["embedding_similarity"],
            exact_weight=WeightExplain(value=float(row["exact_weight"]), reason=str(row["exact_weight_reason"])),
            region_weight=WeightExplain(value=float(row["region_weight"]), reason=str(row["region_weight_reason"])),
            embedding_weight=WeightExplain(
                value=float(row["embedding_weight"]),
                reason=str(row["embedding_weight_reason"]),
            ),
            time_weight=WeightExplain(value=float(row["time_weight"]), reason=str(row["time_weight_reason"])),
            quantity_weight=WeightExplain(
                value=float(row["quantity_weight"]),
                reason=str(row["quantity_weight_reason"]),
            ),
            final_weight=WeightExplain(value=float(row["final_weight"]), reason=str(row["final_weight_reason"])),
            used_in_median=bool(row["used_in_median"]),
            exclusion_reason=row["exclusion_reason"],
        )

    def _filter_outliers(self, candidates: list[dict]) -> list[dict]:
        q1, q3, low, high = self._iqr_bounds(candidates)
        if low is None or high is None:
            return candidates
        return [
            candidate
            for candidate in candidates
            if low <= float(candidate["unit_price"]) <= high
        ]

    def _iqr_bounds(self, candidates: list[dict]) -> tuple[float | None, float | None, float | None, float | None]:
        prices = sorted(float(candidate["unit_price"]) for candidate in candidates)
        if len(prices) < 4:
            return None, None, None, None
        q1, _, q3 = quantiles(prices, n=4, method="inclusive")
        iqr = q3 - q1
        low = q1 - settings.analytics_iqr_multiplier * iqr
        high = q3 + settings.analytics_iqr_multiplier * iqr
        return q1, q3, low, high

    @staticmethod
    def _weighted_median(weighted_points: list[tuple[float, float]]) -> float | None:
        if not weighted_points:
            return None
        ordered = sorted(weighted_points, key=lambda item: item[0])
        total_weight = sum(weight for _, weight in ordered)
        threshold = total_weight / 2
        cumulative = 0.0
        for value, weight in ordered:
            cumulative += weight
            if cumulative >= threshold:
                return value
        return ordered[-1][0]
