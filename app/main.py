import re
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, Request, Response

from app.api import health, messages
from app.logging import configure_logging

# A client-supplied id is echoed into the response and the e-mail headers, so only safe tokens.
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}")

configure_logging()

app = FastAPI(
    title="wskz-router",
    version="0.1.0",
    description=(
        "AI message router: a local LLM agent (Ollama) reads the message and sends it "
        "by e-mail to the right department, with Reply-To set to the sender."
    ),
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
    redoc_url=None,
)
app.include_router(health.router)
app.include_router(messages.router)


@app.middleware("http")
async def assign_request_id(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Correlates the response, the decision log line and the e-mail (`X-Request-ID`)."""
    incoming = request.headers.get("X-Request-ID", "")
    request_id = incoming if REQUEST_ID_PATTERN.fullmatch(incoming) else uuid4().hex
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
