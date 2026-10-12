import logging
import time
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior, UsageLimitExceeded

from app.agent.router_agent import RouterAgent, RoutingOutcome, get_router_agent, route_message
from app.config import Settings, get_settings
from app.mail.sender import MailDeliveryError
from app.schemas import ErrorCode, ErrorResponse, MessageRequest, RoutingResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["messages"])

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_502_BAD_GATEWAY: {
        "model": ErrorResponse,
        "description": (
            "Nothing was sent: the model did not call send_email (`agent_no_tool_call`) "
            "or SMTP failed (`mail_delivery_failed`)."
        ),
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ErrorResponse,
        "description": (
            "Nothing was sent: Ollama is unreachable or returned an error "
            "(`model_unavailable`); retry later."
        ),
    },
    status.HTTP_504_GATEWAY_TIMEOUT: {
        "model": ErrorResponse,
        "description": "The agent did not finish within AGENT_TIMEOUT_S (`agent_timeout`).",
    },
}


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    payload: MessageRequest
    started: float


def log_decision(
    context: RequestContext,
    *,
    outcome: str,
    status_code: int,
    routed: RoutingOutcome | None = None,
    cause: Exception | None = None,
) -> None:
    """One JSON line per validated request (success or error, INV6: `fallback_used`).

    Never the message text nor the sender's local part; for errors only the exception type,
    because its message may quote model output.
    """
    fields = {
        "request_id": context.request_id,
        "outcome": outcome,
        "status": status_code,
        "recipient": routed.email.department.value if routed else None,
        "fallback_used": routed.fallback_used if routed else None,
        "model_requests": routed.model_requests if routed else None,
        "duration_ms": round((time.perf_counter() - context.started) * 1000),
        "smtp_ms": routed.email.smtp_ms if routed else None,
        "message_length": len(context.payload.message),
        "sender_domain": context.payload.email.rsplit("@", 1)[-1],
    }
    if cause is None:
        logger.info("routed", extra=fields)
    else:
        logger.warning("routing failed: %s", type(cause).__name__, extra=fields)


def error(
    context: RequestContext, status_code: int, code: ErrorCode, detail: str, cause: Exception
) -> JSONResponse:
    log_decision(context, outcome=code, status_code=status_code, cause=cause)
    body = ErrorResponse(error=code, detail=detail)
    return JSONResponse(status_code=status_code, content=body.model_dump())


@router.post("/messages", response_model=RoutingResponse, responses=ERROR_RESPONSES)
async def route_incoming_message(
    payload: MessageRequest,
    http_request: Request,
    agent: Annotated[RouterAgent, Depends(get_router_agent)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RoutingResponse | JSONResponse:
    """The agent reads the message and sends it by e-mail to one department, Reply-To = `email`.

    Synchronous: the response arrives after the e-mail was handed to the mail server.
    """
    context = RequestContext(
        request_id=http_request.state.request_id, payload=payload, started=time.perf_counter()
    )
    try:
        routed = await route_message(
            agent,
            sender_email=payload.email,
            message=payload.message,
            request_id=context.request_id,
            settings=settings,
        )
    except (UnexpectedModelBehavior, UsageLimitExceeded) as exc:
        return error(
            context,
            status.HTTP_502_BAD_GATEWAY,
            "agent_no_tool_call",
            "The model did not call send_email with valid arguments; no e-mail was sent.",
            exc,
        )
    except ModelAPIError as exc:  # includes ModelHTTPError (e.g. model not pulled, Ollama 5xx)
        return error(
            context,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "model_unavailable",
            "Ollama is unreachable or returned an error; no e-mail was sent.",
            exc,
        )
    except MailDeliveryError as exc:
        return error(
            context,
            status.HTTP_502_BAD_GATEWAY,
            "mail_delivery_failed",
            "The mail server is unreachable.",
            exc,
        )
    except TimeoutError as exc:
        return error(
            context,
            status.HTTP_504_GATEWAY_TIMEOUT,
            "agent_timeout",
            f"The agent did not finish within {settings.agent_timeout_s:g} s.",
            exc,
        )
    log_decision(context, outcome="sent", status_code=status.HTTP_200_OK, routed=routed)
    return RoutingResponse(
        recipient=routed.email.department,
        reply_to=payload.email,
        subject=routed.email.subject,
        fallback_used=routed.fallback_used,
        duration_ms=routed.duration_ms,
    )
