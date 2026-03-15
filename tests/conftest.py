import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import db


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def fake_connect() -> None:
        return None

    async def fake_close() -> None:
        return None

    monkeypatch.setattr(db, "connect", fake_connect)
    monkeypatch.setattr(db, "close", fake_close)

    with TestClient(app) as test_client:
        yield test_client
