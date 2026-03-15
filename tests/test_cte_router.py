from unittest.mock import AsyncMock

from app.services.pricing_statistics import CteSearchCandidate, CteSearchResult


def test_search_cte_uses_new_filters(client, monkeypatch):
    service_result = CteSearchResult(
        query_name="пакет",
        applied_unit_id=7,
        applied_category_ids=[10, 12],
        total_candidates=1,
        candidates=[
            CteSearchCandidate(
                cte_id=101,
                name="пакет мусорный",
                category_id=10,
                category_name="Пакеты",
                manufacturer_id=None,
                manufacturer_name=None,
                characteristics={"объем": "20 л"},
                exact_name_match=False,
                embedding_similarity=0.91,
            )
        ],
    )
    search_mock = AsyncMock(return_value=service_result)
    monkeypatch.setattr("app.api.routers.cte.PricingStatisticsService.search_cte_candidates", search_mock)

    response = client.post(
        "/api/v1/cte/search",
        json={
            "name": "пакет",
            "characteristics": {},
            "unit_id": 7,
            "category_ids": [10, 12],
            "max_candidates": 20,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["applied_unit_id"] == 7
    assert payload["applied_category_ids"] == [10, 12]
    assert payload["total_candidates"] == 1
    search_mock.assert_awaited_once()
    kwargs = search_mock.await_args.kwargs
    assert kwargs["unit_id"] == 7
    assert kwargs["category_ids"] == [10, 12]
    assert "date_from" not in kwargs
    assert "date_to" not in kwargs


def test_manual_cte_creates_embedding(client, monkeypatch):
    create_mock = AsyncMock(
        return_value={
            "id": -123,
            "name": "пакет мусорный 20л",
            "category_id": 5,
            "category_name": "Пакеты",
            "manufacturer_id": None,
            "manufacturer_name": None,
            "characteristics": {"объем": "20 л"},
        }
    )
    generate_mock = AsyncMock(return_value=True)
    monkeypatch.setattr("app.api.routers.cte.PricingStatisticsService.create_manual_cte", create_mock)
    monkeypatch.setattr("app.api.routers.cte.CteEmbeddingBackfillService.generate_for_cte", generate_mock)

    response = client.post(
        "/api/v1/cte/manual",
        json={
            "name": "пакет мусорный 20л",
            "category_name": "Пакеты",
            "characteristics": {"объем": "20 л"},
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["cte_id"] == -123
    assert payload["embedding_created"] is True
    create_mock.assert_awaited_once()
    generate_mock.assert_awaited_once_with(-123, force_rebuild=True)


def test_patch_cte_rebuilds_embedding(client, monkeypatch):
    update_mock = AsyncMock(
        return_value={
            "id": 555,
            "name": "пакет мусорный 30л",
            "category_id": 5,
            "category_name": "Пакеты",
            "manufacturer_id": 8,
            "manufacturer_name": "NoName",
            "characteristics": {"объем": "30 л"},
        }
    )
    generate_mock = AsyncMock(return_value=True)
    monkeypatch.setattr("app.api.routers.cte.PricingStatisticsService.update_cte", update_mock)
    monkeypatch.setattr("app.api.routers.cte.CteEmbeddingBackfillService.generate_for_cte", generate_mock)

    response = client.patch(
        "/api/v1/cte/555",
        json={
            "name": "пакет мусорный 30л",
            "manufacturer_name": "NoName",
            "characteristics": "Объем:30 л",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["cte_id"] == 555
    assert payload["has_embedding"] is True
    update_mock.assert_awaited_once()
    generate_mock.assert_awaited_once_with(555, force_rebuild=True)
