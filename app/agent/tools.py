"""The agent's only tool: it sends the e-mail (INV1).

The model chooses only department, subject and body (INV2); the recipient address comes
from the enum, Reply-To from the request (INV3).
"""

import time
from dataclasses import dataclass

from pydantic_ai import ModelRetry, RunContext

from app.config import Settings
from app.departments import Department
from app.mail.sender import normalize_subject, send_mail


@dataclass(frozen=True)
class RouterDeps:
    """Per-request data the tool needs and the model never sees as a parameter."""

    sender_email: str
    message: str
    request_id: str
    settings: Settings


@dataclass(frozen=True)
class RoutedEmail:
    department: Department
    subject: str
    smtp_ms: int


def compose_body(summary: str, deps: RouterDeps) -> str:
    # The original message is appended verbatim, so the department gets the full context
    # even when the model's summary misses something.
    original = f"Oryginalna wiadomość od {deps.sender_email}:\n{deps.message}"
    return f"{summary.strip()}\n\n---\n{original}\n"


async def send_email(
    ctx: RunContext[RouterDeps], department: Department, subject: str, body: str
) -> RoutedEmail:
    """Send the user's message to the chosen department.

    Args:
        department: Recipient department e-mail address.
        subject: Short e-mail subject in Polish.
        body: E-mail body in Polish summarising the user's request.
    """
    # Validate before sending: a ModelRetry after the SMTP call would send a second e-mail.
    subject = normalize_subject(subject)
    if not subject or not body.strip():
        raise ModelRetry("subject and body must not be empty")
    started = time.perf_counter()
    await send_mail(
        to=department.value,
        subject=subject,
        body=compose_body(body, ctx.deps),
        reply_to=ctx.deps.sender_email,
        request_id=ctx.deps.request_id,
        settings=ctx.deps.settings,
    )
    smtp_ms = round((time.perf_counter() - started) * 1000)
    return RoutedEmail(department=department, subject=subject, smtp_ms=smtp_ms)
