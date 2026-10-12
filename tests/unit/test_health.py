import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import health
from app.main import app
from app.schemas import MailHealth, OllamaHealth

client = TestClient(app)


def _stub_checks(
    monkeypatch: pytest.MonkeyPatch, *, model_present: bool = True, mail_reachable: bool = True
) -> None:
    ollama = OllamaHealth(reachable=True, model_present=model_present)
    mail = MailHealth(reachable=mail_reachable)

    async def fake_ollama(_client: httpx.AsyncClient, _model: str) -> OllamaHealth:
        return ollama

    async def fake_smtp(_host: str, _port: int, _timeout_s: float) -> MailHealth:
        return mail

    monkeypatch.setattr(health, "check_ollama", fake_ollama)
    monkeypatch.setattr(health, "check_smtp", fake_smtp)


def test_health_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_checks(monkeypatch)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "ollama": {"reachable": True, "model_present": True},
        "mail": {"reachable": True},
    }


def test_health_mail_down(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_checks(monkeypatch, mail_reachable=False)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["mail"] == {"reachable": False}


def test_health_model_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_checks(monkeypatch, model_present=False)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["ollama"] == {"reachable": True, "model_present": False}


def _ollama_client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url="http://ollama:11434", transport=handler)


async def test_health_ollama_unreachable() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async with _ollama_client(httpx.MockTransport(refuse)) as ollama:
        result = await health.check_ollama(ollama, "qwen2.5:3b")

    assert result == OllamaHealth(reachable=False, model_present=False)


async def test_check_ollama_non_json_body() -> None:
    def garbage(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>proxy error</html>")

    async with _ollama_client(httpx.MockTransport(garbage)) as ollama:
        result = await health.check_ollama(ollama, "qwen2.5:3b")

    assert result == OllamaHealth(reachable=False, model_present=False)


@pytest.mark.parametrize(
    ("configured", "pulled", "expected"),
    [
        ("llama3.2", "llama3.2:latest", True),
        ("qwen2.5:3b", "qwen2.5:3b", True),
        ("qwen2.5:3b", "qwen2.5:7b", False),
    ],
)
async def test_check_ollama_matches_latest_tag(
    configured: str, pulled: str, expected: bool
) -> None:
    def tags(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": pulled, "model": pulled}]})

    async with _ollama_client(httpx.MockTransport(tags)) as ollama:
        result = await health.check_ollama(ollama, configured)

    assert result == OllamaHealth(reachable=True, model_present=expected)


async def _serve(greeting: bytes | None) -> asyncio.Server:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if greeting is None:
            await asyncio.sleep(1)  # silent server: client must time out
        else:
            writer.write(greeting)
            await writer.drain()
        writer.close()

    return await asyncio.start_server(handle, "127.0.0.1", 0)


@pytest.mark.parametrize(
    ("greeting", "expected"),
    [(b"220 mailpit ESMTP\r\n", True), (b"554 no service\r\n", False), (None, False)],
)
async def test_check_smtp_banner(greeting: bytes | None, expected: bool) -> None:
    server = await _serve(greeting)
    port = server.sockets[0].getsockname()[1]
    async with server:
        result = await health.check_smtp("127.0.0.1", port, timeout_s=0.2)

    assert result == MailHealth(reachable=expected)


async def test_check_smtp_closed_port() -> None:
    server = await _serve(b"220 ok\r\n")
    port = server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()

    result = await health.check_smtp("127.0.0.1", port, timeout_s=0.2)

    assert result == MailHealth(reachable=False)
