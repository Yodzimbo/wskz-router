import asyncio
import json
import logging
import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agent.router_agent import RouterAgent, build_router_agent, get_router_agent
from app.config import Settings, get_settings
from app.departments import Department
from app.logging import JsonFormatter
from app.main import app
from tests.unit.conftest import FakeSMTP

SETTINGS = Settings(agent_retries=1, agent_timeout_s=5)
URL = "/api/v1/messages"
REQUEST = {"email": "jan.nowak@example.com", "message": "Nie działa mi komputer"}
DECISION_LOGGER = "app.api.messages"


def calls(department: str) -> FunctionModel:
    def respond(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        args = {"department": department, "subject": "Awaria komputera", "body": "Pomocy."}
        return ModelResponse(parts=[ToolCallPart("send_email", args)])

    return FunctionModel(respond)


@pytest.fixture
def agent() -> Iterator[RouterAgent]:
    router_agent = build_router_agent(SETTINGS)
    app.dependency_overrides[get_router_agent] = lambda: router_agent
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    yield router_agent
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_route_ok(agent: RouterAgent, client: TestClient, fake_smtp: type[FakeSMTP]) -> None:
    with agent.override(model=calls(Department.HELP_DESK)):
        response = client.post(URL, json=REQUEST)

    assert response.status_code == 200
    body = response.json()
    assert body["recipient"] == Department.HELP_DESK.value
    assert body["reply_to"] == REQUEST["email"]
    assert body["subject"] == "Awaria komputera"
    assert body["fallback_used"] is False
    assert body["duration_ms"] >= 0
    [mail] = fake_smtp.sent
    assert mail["Reply-To"] == REQUEST["email"]


def test_other_marks_fallback(
    agent: RouterAgent, client: TestClient, fake_smtp: type[FakeSMTP]
) -> None:
    with agent.override(model=calls(Department.OTHER)):
        response = client.post(URL, json=REQUEST)

    assert response.status_code == 200
    assert response.json()["fallback_used"] is True


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "to-nie-jest-email", "message": "Nie działa mi komputer"},
        {"email": "jan.nowak@example.com", "message": ""},
        {"email": "jan.nowak@example.com", "message": "   \n "},
        {"email": "jan.nowak@example.com", "message": "x" * 5001},
        {"email": "jan.nowak@example.com"},
    ],
)
def test_validation_errors(
    agent: RouterAgent, client: TestClient, fake_smtp: type[FakeSMTP], payload: dict[str, str]
) -> None:
    with agent.override(model=calls(Department.HELP_DESK)):
        response = client.post(URL, json=payload)

    assert response.status_code == 422
    assert fake_smtp.sent == []


def test_no_tool_call_returns_502(
    agent: RouterAgent, client: TestClient, fake_smtp: type[FakeSMTP]
) -> None:
    def text_only(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart("Nie wiem.")])

    with agent.override(model=FunctionModel(text_only)):
        response = client.post(URL, json=REQUEST)

    assert response.status_code == 502
    assert response.json()["error"] == "agent_no_tool_call"
    assert fake_smtp.sent == []


@pytest.mark.parametrize(
    "failure",
    [ModelAPIError("ollama", "connection refused"), ModelHTTPError(404, "qwen3:4b-instruct")],
)
def test_model_unavailable_returns_503(
    agent: RouterAgent, client: TestClient, fake_smtp: type[FakeSMTP], failure: ModelAPIError
) -> None:
    def down(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        raise failure

    with agent.override(model=FunctionModel(down)):
        response = client.post(URL, json=REQUEST)

    assert response.status_code == 503
    assert response.json()["error"] == "model_unavailable"
    assert fake_smtp.sent == []


def test_smtp_down_returns_502(
    agent: RouterAgent, client: TestClient, fake_smtp: type[FakeSMTP]
) -> None:
    fake_smtp.error = ConnectionRefusedError(111, "refused")

    with agent.override(model=calls(Department.HELP_DESK)):
        response = client.post(URL, json=REQUEST)

    assert response.status_code == 502
    assert response.json()["error"] == "mail_delivery_failed"


def test_timeout_returns_504(
    agent: RouterAgent, client: TestClient, fake_smtp: type[FakeSMTP]
) -> None:
    async def slow(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        await asyncio.sleep(1)
        return ModelResponse(parts=[TextPart("za późno")])

    app.dependency_overrides[get_settings] = lambda: SETTINGS.model_copy(
        update={"agent_timeout_s": 0.05}
    )
    with agent.override(model=FunctionModel(slow)):
        response = client.post(URL, json=REQUEST)

    assert response.status_code == 504
    assert response.json()["error"] == "agent_timeout"
    assert fake_smtp.sent == []


def test_openapi_documents_examples_and_errors(client: TestClient) -> None:
    spec = client.get("/api/v1/openapi.json").json()
    operation = spec["paths"][URL]["post"]

    assert set(operation["responses"]) >= {"200", "422", "502", "503", "504"}
    examples = spec["components"]["schemas"]["MessageRequest"]["examples"]
    assert examples[0]["message"] == "Nie działa mi komputer"


def decisions(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == DECISION_LOGGER]


def test_decision_log_has_fields_and_no_content(
    agent: RouterAgent,
    client: TestClient,
    fake_smtp: type[FakeSMTP],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=DECISION_LOGGER)
    with agent.override(model=calls(Department.HELP_DESK)):
        response = client.post(URL, json=REQUEST)

    [record] = decisions(caplog)
    line = JsonFormatter().format(record)
    entry = json.loads(line)
    assert entry["request_id"] == response.headers["X-Request-ID"]
    assert entry["outcome"] == "sent"
    assert entry["status"] == 200
    assert entry["recipient"] == Department.HELP_DESK.value
    assert entry["fallback_used"] is False
    assert entry["model_requests"] == 1
    assert entry["duration_ms"] >= 0
    assert entry["smtp_ms"] >= 0
    assert entry["message_length"] == len(REQUEST["message"])
    assert entry["sender_domain"] == "example.com"
    for secret in (REQUEST["message"], "jan.nowak"):
        assert secret not in caplog.text
        assert secret not in line


def test_fallback_is_logged(
    agent: RouterAgent,
    client: TestClient,
    fake_smtp: type[FakeSMTP],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=DECISION_LOGGER)
    with agent.override(model=calls(Department.OTHER)):
        client.post(URL, json={**REQUEST, "message": "Gdzie mogę zostawić rower?"})

    [record] = decisions(caplog)
    assert record.fallback_used is True
    assert record.recipient == Department.OTHER.value
    assert "rower" not in caplog.text


def test_error_is_logged_with_code(
    agent: RouterAgent,
    client: TestClient,
    fake_smtp: type[FakeSMTP],
    caplog: pytest.LogCaptureFixture,
) -> None:
    def down(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        raise ModelAPIError("ollama", "connection refused")

    caplog.set_level(logging.INFO, logger=DECISION_LOGGER)
    with agent.override(model=FunctionModel(down)):
        client.post(URL, json=REQUEST)

    [record] = decisions(caplog)
    assert record.outcome == "model_unavailable"
    assert record.status == 503
    assert record.recipient is None
    assert record.levelname == "WARNING"


def test_validation_error_is_not_logged_as_decision(
    agent: RouterAgent, client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=DECISION_LOGGER)
    response = client.post(URL, json={"email": "zly", "message": "x"})

    assert response.status_code == 422
    assert re.fullmatch("[0-9a-f]{32}", response.headers["X-Request-ID"])
    assert decisions(caplog) == []


def test_valid_request_id_is_echoed_to_response_mail_and_log(
    agent: RouterAgent,
    client: TestClient,
    fake_smtp: type[FakeSMTP],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=DECISION_LOGGER)
    with agent.override(model=calls(Department.HELP_DESK)):
        response = client.post(URL, json=REQUEST, headers={"X-Request-ID": "abc-123"})

    assert response.headers["X-Request-ID"] == "abc-123"
    assert fake_smtp.sent[0]["X-Request-ID"] == "abc-123"
    assert fake_smtp.sent[0]["Reply-To"] == REQUEST["email"]
    [record] = decisions(caplog)
    assert record.request_id == "abc-123"


@pytest.mark.parametrize("incoming", ["a\r\nBcc: x@example.com", "x" * 65, "a b", ""])
def test_invalid_request_id_is_replaced(
    agent: RouterAgent, client: TestClient, fake_smtp: type[FakeSMTP], incoming: str
) -> None:
    with agent.override(model=calls(Department.HELP_DESK)):
        response = client.post(URL, json=REQUEST, headers={"X-Request-ID": incoming})

    request_id = response.headers["X-Request-ID"]
    assert request_id != incoming
    assert re.fullmatch("[0-9a-f]{32}", request_id)
    assert fake_smtp.sent[0]["X-Request-ID"] == request_id
