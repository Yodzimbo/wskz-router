import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agent.router_agent import RouterAgent, build_router_agent, get_router_agent
from app.config import Settings, get_settings
from app.departments import Department
from app.main import app
from tests.unit.conftest import FakeSMTP

SETTINGS = Settings(agent_retries=1, agent_timeout_s=5)
URL = "/api/v1/messages"
REQUEST = {"email": "jan.nowak@example.com", "message": "Nie działa mi komputer"}


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


def test_model_unavailable_returns_502(
    agent: RouterAgent, client: TestClient, fake_smtp: type[FakeSMTP]
) -> None:
    def down(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        raise ModelAPIError("ollama", "connection refused")

    with agent.override(model=FunctionModel(down)):
        response = client.post(URL, json=REQUEST)

    assert response.status_code == 502
    assert response.json()["error"] == "model_unavailable"


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

    assert set(operation["responses"]) >= {"200", "422", "502", "504"}
    examples = spec["components"]["schemas"]["MessageRequest"]["examples"]
    assert examples[0]["message"] == "Nie działa mi komputer"
