from typing import Literal

from pydantic import BaseModel


class OllamaHealth(BaseModel):
    reachable: bool
    model_present: bool


class MailHealth(BaseModel):
    reachable: bool


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    ollama: OllamaHealth
    mail: MailHealth
