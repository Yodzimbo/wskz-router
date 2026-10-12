from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.departments import Department


class OllamaHealth(BaseModel):
    reachable: bool
    model_present: bool


class MailHealth(BaseModel):
    reachable: bool


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    ollama: OllamaHealth
    mail: MailHealth


class MessageRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"email": "jan.nowak@example.com", "message": "Nie działa mi komputer"}]
        }
    )

    email: EmailStr = Field(description="Sender's address; becomes Reply-To of the routed e-mail.")
    message: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
    ] = Field(description="Free-form message in Polish.")


class RoutingResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "recipient": Department.HELP_DESK.value,
                    "reply_to": "jan.nowak@example.com",
                    "subject": "Awaria komputera",
                    "fallback_used": False,
                    "duration_ms": 5900,
                }
            ]
        }
    )

    recipient: Department = Field(description="Department the agent sent the e-mail to.")
    reply_to: str
    subject: str
    fallback_used: bool = Field(
        description="True when the agent chose the fallback department (other@)."
    )
    duration_ms: int


ErrorCode = Literal[
    "agent_no_tool_call", "model_unavailable", "mail_delivery_failed", "agent_timeout"
]


class ErrorResponse(BaseModel):
    error: ErrorCode
    detail: str
