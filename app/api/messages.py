import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior, UsageLimitExceeded

from app.agent.router_agent import RouterAgent, get_router_agent, route_message
from app.config import Settings, get_settings
from app.mail.sender import MailDeliveryError
from app.schemas import ErrorCode, ErrorResponse, MessageRequest, RoutingResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["messages"])

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_502_BAD_GATEWAY: {
        "model": ErrorResponse,
        "description": (
            "Nothing was sent: the model did not call send_email (`agent_no_tool_call`), "
            "Ollama is unreachable (`model_unavailable`) or SMTP failed (`mail_delivery_failed`)."
        ),
    },
    status.HTTP_504_GATEWAY_TIMEOUT: {
        "model": ErrorResponse,
        "description": "The agent did not finish within AGENT_TIMEOUT_S (`agent_timeout`).",
    },
}


def error(status_code: int, code: ErrorCode, detail: str, cause: Exception) -> JSONResponse:
    # Exception type only: its message may quote model output.
    logger.warning("routing failed error=%s cause=%s", code, type(cause).__name__)
    body = ErrorResponse(error=code, detail=detail)
    return JSONResponse(status_code=status_code, content=body.model_dump())


@router.post("/messages", response_model=RoutingResponse, responses=ERROR_RESPONSES)
async def route_incoming_message(
    request: MessageRequest,
    agent: Annotated[RouterAgent, Depends(get_router_agent)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RoutingResponse | JSONResponse:
    """The agent reads the message and sends it by e-mail to one department, Reply-To = `email`.

    Synchronous: the response arrives after the e-mail was handed to the mail server.
    """
    try:
        outcome = await route_message(
            agent, sender_email=request.email, message=request.message, settings=settings
        )
    except (UnexpectedModelBehavior, UsageLimitExceeded) as exc:
        return error(
            status.HTTP_502_BAD_GATEWAY,
            "agent_no_tool_call",
            "The model did not call send_email with valid arguments; no e-mail was sent.",
            exc,
        )
    except ModelAPIError as exc:
        return error(
            status.HTTP_502_BAD_GATEWAY, "model_unavailable", "Ollama is unreachable.", exc
        )
    except MailDeliveryError as exc:
        return error(
            status.HTTP_502_BAD_GATEWAY,
            "mail_delivery_failed",
            "The mail server is unreachable.",
            exc,
        )
    except TimeoutError as exc:
        return error(
            status.HTTP_504_GATEWAY_TIMEOUT,
            "agent_timeout",
            f"The agent did not finish within {settings.agent_timeout_s:g} s.",
            exc,
        )
    return RoutingResponse(
        recipient=outcome.email.department,
        reply_to=request.email,
        subject=outcome.email.subject,
        fallback_used=outcome.fallback_used,
        duration_ms=outcome.duration_ms,
    )
