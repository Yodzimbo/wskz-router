import logging

from fastapi import FastAPI

from app.api import health, messages

# Uvicorn configures only its own loggers; without this the routing decisions are not logged.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s - %(message)s")

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
