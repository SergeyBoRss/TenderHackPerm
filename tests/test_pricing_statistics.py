from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.services.pricing_statistics import PricingStatisticsService
from app.services.cte_embeddings import CteEmbeddingBackfillService


class DummyDb:
    pass


class DummyTxDb:
    @asynccontextmanager
    async def transaction(self):
        yield object()


@pytest.mark.asyncio
async def test_estimate_for_cte_details_marks_iqr_outlier_and_explains_weights(monkeypatch):
    service = PricingStatisticsService(DummyDb())

    async def fake_target(_: int) -> dict:
        return {
            "id": 101,
            "name": "пакет мусорный 20л",
            "category_id": 7,
            "manufacturer_id": 9,
            "embedding_text": "[0.1,0.2,0.3]",
        }

    async def fake_exact(**kwargs) -> list[dict]:
        return [
            {
                "contract_id": 1,
                "contract_item_id": 11,
                "cte_id": 201,
                "quantity": 100.0,
                "unit_price": 10.0,
                "signed_at": date(2026, 1, 1),
                "customer_region": "Пермский край",
                "category_id": 7,
                "manufacturer_id": 9,
                "embedding_similarity": 0.95,
            },
            {
                "contract_id": 2,
                "contract_item_id": 22,
                "cte_id": 202,
                "quantity": 110.0,
                "unit_price": 11.0,
                "signed_at": date(2025, 12, 1),
                "customer_region": "Свердловская область",
                "category_id": 7,
                "manufacturer_id": 9,
                "embedding_similarity": 0.82,
            },
            {
                "contract_id": 3,
                "contract_item_id": 33,
                "cte_id": 203,
                "quantity": 100.0,
                "unit_price": 12.0,
                "signed_at": date(2025, 11, 1),
                "customer_region": "Тюменская область",
                "category_id": 7,
                "manufacturer_id": 9,
                "embedding_similarity": 0.8,
            },
            {
                "contract_id": 4,
                "contract_item_id": 44,
                "cte_id": 204,
                "quantity": 100.0,
                "unit_price": 1000.0,
                "signed_at": date(2025, 10, 1),
                "customer_region": "Москва",
                "category_id": 7,
                "manufacturer_id": 9,
                "embedding_similarity": 0.75,
            },
        ]

    async def fake_vector(**kwargs) -> list[dict]:
        return []

    async def fake_region_weight(target_region: str, candidate_region: str | None) -> dict:
        if candidate_region == "Пермский край":
            return {
                "weight": 1.0,
                "distance_km": 0.0,
                "distance_factor": 1.0,
                "anomaly_penalty": 1.0,
                "reason": "Регион совпадает",
            }
        return {
            "weight": 0.5,
            "distance_km": 300.0,
            "distance_factor": 0.6,
            "anomaly_penalty": 0.83,
            "reason": "Регион далеко, применено снижение",
        }

    monkeypatch.setattr(service.repository, "fetch_target_cte_context", fake_target)
    monkeypatch.setattr(service.repository, "fetch_exact_candidates", fake_exact)
    monkeypatch.setattr(service.repository, "fetch_vector_candidates", fake_vector)
    monkeypatch.setattr(service.region_weights, "explain_weight", fake_region_weight)

    estimate, _, debug_rows = await service._estimate_for_cte_with_details(
        cte_id=101,
        target_region="Пермский край",
        target_quantity=100.0,
        reference_date=date(2026, 3, 15),
        vector_limit=50,
    )

    assert estimate.total_candidates == 4
    assert estimate.filtered_candidates == 3
    assert estimate.estimated_unit_price == 10.0
    assert estimate.iqr_high is not None

    used_rows = [row for row in debug_rows if row["used_in_median"]]
    excluded_rows = [row for row in debug_rows if not row["used_in_median"]]

    assert len(used_rows) == 3
    assert len(excluded_rows) == 1
    assert excluded_rows[0]["contract_item_id"] == 44
    assert "выше верхней IQR-границы" in excluded_rows[0]["exclusion_reason"]
    assert used_rows[0]["final_weight"] > 0
    assert "Совпали категория, производитель и регион" in used_rows[0]["exact_weight_reason"]
    assert "Логарифмическая дистанция объемов" in used_rows[0]["quantity_weight_reason"]


@pytest.mark.asyncio
async def test_search_cte_candidates_builds_query_embedding_for_one_request(monkeypatch):
    service = PricingStatisticsService(DummyDb())

    embed_query_mock = AsyncMock(return_value=[0.1, 0.2, 0.3])
    monkeypatch.setattr(service.embedding_client, "embed_query", embed_query_mock)
    monkeypatch.setattr(service.embedding_client, "to_vector_literal", lambda vector: "[0.1,0.2,0.3]")

    async def fake_exact_matches(**kwargs) -> list[dict]:
        assert kwargs["query_name"] == "пакет мусорный 20л"
        assert kwargs["unit_id"] == 7
        assert kwargs["category_ids"] == [10]
        return []

    async def fake_vector_matches(**kwargs) -> list[dict]:
        assert kwargs["target_embedding_text"] == "[0.1,0.2,0.3]"
        return [
            {
                "cte_id": 1001,
                "name": "пакет мусорный 20л",
                "characteristics": {"цвет": "черный"},
                "category_id": 10,
                "category_name": "Пакеты",
                "manufacturer_id": None,
                "manufacturer_name": None,
                "exact_name_match": False,
                "embedding_similarity": 0.94,
            }
        ]

    monkeypatch.setattr(service.repository, "fetch_cte_name_exact_matches", fake_exact_matches)
    monkeypatch.setattr(service.repository, "fetch_cte_vector_matches", fake_vector_matches)

    result = await service.search_cte_candidates(
        name="пакет мусорный 20л",
        characteristics={"цвет": "черный"},
        unit_id=7,
        category_ids=[10],
        max_candidates=20,
    )

    assert result.total_candidates == 1
    assert result.candidates[0].cte_id == 1001
    embed_query_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_for_cte_updates_only_one_embedding(monkeypatch):
    service = CteEmbeddingBackfillService(DummyTxDb())

    async def fake_target(cte_id: int) -> dict:
        assert cte_id == 321
        return {
            "id": 321,
            "name": "пакет мусорный 20л",
            "characteristics": {"цвет": "черный"},
        }

    async def fake_state(cte_id: int) -> dict | None:
        assert cte_id == 321
        return None

    async def fake_embed_documents(texts: list[str]) -> list[list[float]]:
        assert len(texts) == 1
        assert "Наименование: пакет мусорный 20л" in texts[0]
        return [[0.1, 0.2, 0.3]]

    upsert_mock = AsyncMock()
    monkeypatch.setattr(service.repository, "fetch_target_cte_context", fake_target)
    monkeypatch.setattr(service.repository, "fetch_cte_embedding_state", fake_state)
    monkeypatch.setattr(service.embedding_client, "embed_documents", fake_embed_documents)
    monkeypatch.setattr(service.embedding_client, "to_vector_literal", lambda vector: "[0.1,0.2,0.3]")
    monkeypatch.setattr(service.repository, "upsert_cte_embedding", upsert_mock)

    result = await service.generate_for_cte(321, force_rebuild=False)

    assert result is True
    upsert_mock.assert_awaited_once()
    kwargs = upsert_mock.await_args.kwargs
    assert kwargs["cte_id"] == 321
