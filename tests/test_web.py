from __future__ import annotations

from fastapi.testclient import TestClient

from findex.index import InvertedIndex
from findex.web.app import create_app, get_service
from findex.web.config import Settings
from findex.web.service import WebDocument, WebSearch


def fake_service() -> WebSearch:
    idx = InvertedIndex()
    idx.add_document(0, "Alpha", "fastapi asyncio search")
    idx.add_document(1, "Beta", "asyncio event loop")
    return WebSearch(
        idx,
        {
            0: WebDocument(0, "Alpha", "fastapi asyncio search"),
            1: WebDocument(1, "Beta", "asyncio event loop"),
        },
    )


def test_search_success_with_dependency_override() -> None:
    app = create_app(Settings())
    app.dependency_overrides[get_service] = fake_service
    with TestClient(app) as client:
        response = client.get("/search?q=asyncio&k=1")
    app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["pages"] == 2
    assert body["results"][0]["title"] == "Alpha"


def test_search_pagination_returns_second_page() -> None:
    app = create_app(Settings())
    app.dependency_overrides[get_service] = fake_service
    with TestClient(app) as client:
        response = client.get("/search?q=asyncio&k=1&page=2")
    app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 2
    assert body["results"][0]["title"] == "Beta"


def test_search_validation_422() -> None:
    app = create_app(Settings())
    app.dependency_overrides[get_service] = fake_service
    with TestClient(app) as client:
        assert client.get("/search?q=&k=1").status_code == 422
        assert client.get("/search?q=asyncio&k=0").status_code == 422
    app.dependency_overrides.clear()


def test_unknown_document_404() -> None:
    app = create_app(Settings())
    app.dependency_overrides[get_service] = fake_service
    with TestClient(app) as client:
        assert client.get("/docs/999").status_code == 404
    app.dependency_overrides.clear()


def test_health_503_when_index_not_loaded() -> None:
    app = create_app(Settings())
    with TestClient(app) as client:
        app.state.web_search = None
        response = client.get("/health")
    assert response.status_code == 503
