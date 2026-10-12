"""End-to-end tests against the running compose stack: plain HTTP to the API and Mailpit.

Each test uses its own sender address and finds its e-mail by Reply-To, so the tests never
clear the Mailpit inbox.
"""

import os
import time
import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

API_URL = os.environ.get("API_URL", "http://localhost:8000")
MAILPIT_URL = os.environ.get("MAILPIT_URL", "http://localhost:8025")
# Above AGENT_TIMEOUT_S (60 s): a slow CPU answer should end as 504 from the API, not here.
API_TIMEOUT_S = 120
MAIL_WAIT_S = 10

Mail = dict[str, Any]


@pytest.fixture(scope="session")
def api() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=API_URL, timeout=API_TIMEOUT_S) as client:
        yield client


@pytest.fixture(scope="session")
def mailpit() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=f"{MAILPIT_URL}/api/v1", timeout=10) as client:
        yield client


@pytest.fixture(scope="session", autouse=True)
def compose_running(api: httpx.Client, mailpit: httpx.Client) -> None:
    try:
        api.get("/health", timeout=5).raise_for_status()
        mailpit.get("/messages", timeout=5).raise_for_status()
    except httpx.HTTPError as exc:
        pytest.skip(f"compose not running ({exc!r}): docker compose up -d")


@pytest.fixture
def sender() -> str:
    return f"e2e-{uuid.uuid4().hex[:12]}@example.com"


def addresses(field: list[dict[str, str]] | None) -> list[str]:
    return [entry["Address"].lower() for entry in field or []]


def mails_replying_to(mailpit: httpx.Client, reply_to: str) -> list[Mail]:
    """Mails in the inbox whose Reply-To is reply_to (Mailpit lists the newest first)."""
    response = mailpit.get("/messages")
    response.raise_for_status()
    messages: list[Mail] = response.json()["messages"]
    return [m for m in messages if reply_to.lower() in addresses(m.get("ReplyTo"))]


def wait_for_mail(mailpit: httpx.Client, reply_to: str) -> list[Mail]:
    deadline = time.monotonic() + MAIL_WAIT_S
    while not (found := mails_replying_to(mailpit, reply_to)) and time.monotonic() < deadline:
        time.sleep(0.5)
    return found


def header(mailpit: httpx.Client, mail: Mail, name: str) -> list[str]:
    response = mailpit.get(f"/message/{mail['ID']}/headers")
    response.raise_for_status()
    return [value.strip() for value in response.json().get(name, [])]
