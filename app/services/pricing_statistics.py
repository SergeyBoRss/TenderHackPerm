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
    applied_unit_value: str | None
    applied_supplier_inns: list[str] | None
    applied_date_from: date | None
    applied_date_to: date | None
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
        filtered_candidates = self._filter_outliers(list(merged_candidates.values()))
        filtered_candidate_ids = {int(candidate["contract_item_id"]) for candidate in filtered_candidates}

        weighted_points: list[tuple[float, float]] = []
        candidate_debug_rows: list[dict] = []
        for candidate in merged_candidates.values():
            exact_weight = await self._exact_branch_weight(target, candidate, target_region)
            embedding_weight = self._embedding_weight(candidate.get("embedding_similarity"))
            time_weight = self._time_weight(candidate["signed_at"], current_reference_date)
            quantity_weight = self._quantity_weight(
                target_quantity=target_quantity,
                candidate_quantity=float(candidate["quantity"]) if candidate.get("quantity") is not None else None,
            )
            final_weight = exact_weight * embedding_weight * time_weight * quantity_weight
            included_after_iqr = int(candidate["contract_item_id"]) in filtered_candidate_ids

            candidate_debug_rows.append(
                {
                    "contract_item_id": int(candidate["contract_item_id"]),
                    "cte_id": int(candidate["cte_id"]),
                    "quantity": float(candidate["quantity"]) if candidate.get("quantity") is not None else None,
                    "unit_price": float(candidate["unit_price"]),
                    "signed_at": candidate["signed_at"],
                    "customer_region": candidate.get("customer_region"),
                    "source_exact": bool(candidate.get("source_exact")),
                    "source_vector": bool(candidate.get("source_vector")),
                    "embedding_similarity": float(candidate["embedding_similarity"])
                    if candidate.get("embedding_similarity") is not None
                    else None,
                    "exact_weight": exact_weight,
                    "embedding_weight": embedding_weight,
                    "time_weight": time_weight,
                    "quantity_weight": quantity_weight,
                    "final_weight": final_weight,
                    "included_after_iqr": included_after_iqr,
                }
            )

            if not included_after_iqr or final_weight <= 0:
                continue
            weighted_points.append((float(candidate["unit_price"]), final_weight))

        estimated_unit_price = self._weighted_median(weighted_points)
        q1, q3, low, high = self._iqr_bounds(list(merged_candidates.values()))

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
        unit_value: str | None,
        supplier_inns: list[str] | None,
        date_from: date | None,
        date_to: date | None,
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

        normalized_supplier_inns = supplier_inns or None
        exact_matches = await self.repository.fetch_cte_name_exact_matches(
            query_name=name,
            unit_value=unit_value,
            supplier_inns=normalized_supplier_inns,
            date_from=date_from,
            date_to=date_to,
            limit=capped_limit,
        )
        vector_matches = await self.repository.fetch_cte_vector_matches(
            target_embedding_text=query_embedding_text,
            unit_value=unit_value,
            supplier_inns=normalized_supplier_inns,
            date_from=date_from,
            date_to=date_to,
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
            applied_unit_value=unit_value,
            applied_supplier_inns=normalized_supplier_inns,
            applied_date_from=date_from,
            applied_date_to=date_to,
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
            key=lambda row: (not row["included_after_iqr"], -row["final_weight"], row["unit_price"]),
        )[:3]
        for candidate in top_candidates:
            logger.info(
                "NMCK candidate debug: item_name=%s cte_id=%s contract_item_id=%s candidate_cte_id=%s candidate_quantity=%s unit_price=%s signed_at=%s customer_region=%s source_exact=%s source_vector=%s embedding_similarity=%s exact_weight=%s embedding_weight=%s time_weight=%s quantity_weight=%s final_weight=%s included_after_iqr=%s",
                item_name,
                estimate.cte_id,
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
                candidate["included_after_iqr"],
            )

    async def _exact_branch_weight(self, target: dict, candidate: dict, target_region: str) -> float:
        same_category = int(candidate["category_id"]) == int(target["category_id"])
        same_manufacturer = bool(target.get("manufacturer_id")) and candidate.get("manufacturer_id") == target.get(
            "manufacturer_id"
        )
        same_region = self._normalize_region(candidate.get("customer_region")) == self._normalize_region(target_region)

        if same_category and same_manufacturer and same_region:
            return 1.0

        regional_weight = await self.region_weights.get_weight(target_region, candidate.get("customer_region"))
        if same_category and same_manufacturer:
            return regional_weight
        if same_category:
            return regional_weight * settings.analytics_category_only_multiplier
        return regional_weight * settings.analytics_fallback_multiplier

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
    def _quantity_weight(target_quantity: float | None, candidate_quantity: float | None) -> float:
        if target_quantity is None or candidate_quantity is None:
            return 1.0
        if target_quantity <= 0 or candidate_quantity <= 0:
            return 1.0
        quantity_distance = abs(math.log(target_quantity + 1.0) - math.log(candidate_quantity + 1.0))
        raw_weight = math.exp(-settings.analytics_quantity_weight_alpha * quantity_distance)
        return max(settings.analytics_quantity_weight_min, raw_weight)

    @staticmethod
    def _time_weight(signed_at: date, reference_date: date) -> float:
        age_days = max(0, (reference_date - signed_at).days)
        return 0.5 ** (age_days / settings.analytics_time_half_life_days)

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
