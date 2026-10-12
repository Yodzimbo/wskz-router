import asyncio
import contextlib
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Response, status

from app.config import Settings, get_settings
from app.schemas import HealthResponse, MailHealth, OllamaHealth

router = APIRouter(tags=["health"])


def _with_tag(model: str) -> str:
    # Ollama lists untagged models as "<name>:latest".
    return model if ":" in model else f"{model}:latest"


async def check_ollama(client: httpx.AsyncClient, model: str) -> OllamaHealth:
    """Server reachable and model pulled; lists local models only, never runs inference."""
    try:
        response = await client.get("/api/tags")
        response.raise_for_status()
        models = response.json().get("models", [])
    except (httpx.HTTPError, ValueError):
        # ValueError: body is not JSON - treat like an unreachable server, never a 500.
        return OllamaHealth(reachable=False, model_present=False)
    names = {entry.get("name") for entry in models}
    return OllamaHealth(reachable=True, model_present=_with_tag(model) in names)


async def check_smtp(host: str, port: int, timeout_s: float) -> MailHealth:
    """SMTP server greets with 220.

    Reads the banner over plain TCP and only says QUIT: no SMTP client outside app/mail/ (INV1).
    """
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout_s)
    except (OSError, TimeoutError):
        return MailHealth(reachable=False)
    try:
        banner = await asyncio.wait_for(reader.readline(), timeout_s)
        writer.write(b"QUIT\r\n")
    except (OSError, TimeoutError):
        banner = b""
    finally:
        writer.close()
        with contextlib.suppress(OSError):
            await writer.wait_closed()
    return MailHealth(reachable=banner.startswith(b"220"))


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
)
async def health(
    response: Response, settings: Annotated[Settings, Depends(get_settings)]
) -> HealthResponse:
    """200 when Ollama has the configured model and the mail server is up, otherwise 503."""
    async with httpx.AsyncClient(
        base_url=settings.ollama_base_url, timeout=settings.health_timeout_s
    ) as client:
        ollama, mail = await asyncio.gather(
            check_ollama(client, settings.ollama_model),
            check_smtp(settings.smtp_host, settings.smtp_port, settings.health_timeout_s),
        )
    healthy = ollama.reachable and ollama.model_present and mail.reachable
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="ok" if healthy else "degraded", ollama=ollama, mail=mail)
