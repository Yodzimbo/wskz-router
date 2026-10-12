from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_docs_served_under_api_v1() -> None:
    docs = client.get("/api/v1/docs")
    openapi = client.get("/api/v1/openapi.json")

    assert docs.status_code == 200
    assert "swagger-ui" in docs.text
    assert "/api/v1/openapi.json" in docs.text
    assert openapi.status_code == 200
    assert "/health" in openapi.json()["paths"]


def test_default_docs_disabled() -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404
