from email.message import EmailMessage
from types import TracebackType
from typing import Self

import pytest
from pydantic_ai import models

from app.mail import sender

# Unit tests run without Ollama: any request to a real model fails instead of hitting the network.
models.ALLOW_MODEL_REQUESTS = False


class FakeSMTP:
    """Stands in for smtplib.SMTP; records connections and sent messages."""

    sent: list[EmailMessage] = []
    connections: list[tuple[str, int, float]] = []
    error: OSError | None = None

    def __init__(self, host: str, port: int, timeout: float) -> None:
        if FakeSMTP.error is not None:
            raise FakeSMTP.error
        FakeSMTP.connections.append((host, port, timeout))

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    def send_message(self, message: EmailMessage) -> None:
        FakeSMTP.sent.append(message)


@pytest.fixture
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> type[FakeSMTP]:
    FakeSMTP.sent, FakeSMTP.connections, FakeSMTP.error = [], [], None
    monkeypatch.setattr(sender.smtplib, "SMTP", FakeSMTP)
    return FakeSMTP
