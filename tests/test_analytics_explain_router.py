from datetime import date
from unittest.mock import AsyncMock

from app.services.pricing_statistics import (
    BasketNmckExplainEstimate,
    BasketNmckExplainItemEstimate,
    BasketNmckSelectedCteExplain,
    NmckCandidateExplain,
    WeightExplain,
)


def test_explain_nmck_route_returns_nested_details(client, monkeypatch):
    candidate = NmckCandidateExplain(
        contract_id=11,
        contract_item_id=22,
        candidate_cte_id=333,
        candidate_quantity=100.0,
        unit_price=12.5,
        signed_at=date(2025, 1, 10),
        customer_region="Пермский край",
        source_exact=True,
        source_vector=False,
        embedding_similarity=0.87,
        exact_weight=WeightExplain(value=1.0, reason="Совпали категория, производитель и регион"),
        region_weight=WeightExplain(value=1.0, reason="Регион совпал"),
        embedding_weight=WeightExplain(value=0.87, reason="Из cosine similarity"),
        time_weight=WeightExplain(value=0.8, reason="Контракт относительно свежий"),
        quantity_weight=WeightExplain(value=0.95, reason="Объем близок к целевому"),
        final_weight=WeightExplain(value=0.6612, reason="Произведение четырех весов"),
        used_in_median=True,
        exclusion_reason=None,
    )
    explain_result = BasketNmckExplainEstimate(
        target_region="Пермский край",
        reference_date=date(2026, 3, 15),
        total_positions=1,
        positions_with_price=1,
        estimated_total_price=1250.0,
        items=[
            BasketNmckExplainItemEstimate(
                item_name="Пакет мусорный",
                quantity=100.0,
                estimated_unit_price=12.5,
                line_total=1250.0,
                selected_cte_count=1,
                selected_ctes=[
                    BasketNmckSelectedCteExplain(
                        cte_id=333,
                        cte_name="пакет мусорный 20л",
                        estimated_unit_price=12.5,
                        total_candidates=5,
                        filtered_candidates=4,
                        exact_candidates=3,
                        vector_candidates=2,
                        q1=11.0,
                        q3=13.0,
                        iqr_low=8.0,
                        iqr_high=16.0,
                        min_candidate_unit_price=10.0,
                        max_candidate_unit_price=99.0,
                        min_filtered_unit_price=10.0,
                        max_filtered_unit_price=13.5,
                        considered_contracts=[candidate],
                        excluded_contracts=[],
                    )
                ],
            )
        ],
    )
    explain_mock = AsyncMock(return_value=explain_result)
    monkeypatch.setattr(
        "app.api.routers.analytics_explain.PricingStatisticsService.explain_nmck_for_basket",
        explain_mock,
    )

    response = client.post(
        "/api/v1/analytics/explain/nmck",
        json={
            "target_region": "Пермский край",
            "items": [{"item_name": "Пакет мусорный", "quantity": 100, "cte_ids": [333]}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["estimated_total_price"] == 1250.0
    assert payload["items"][0]["selected_ctes"][0]["considered_contracts"][0]["final_weight"]["value"] == 0.6612
    explain_mock.assert_awaited_once()
