"""The only module that talks SMTP (INV1). Called only by the agent tool."""

import asyncio
import smtplib
from email.message import EmailMessage

from app.config import Settings

MAX_SUBJECT_LENGTH = 150


class MailDeliveryError(Exception):
    """The SMTP server refused the message or could not be reached."""


def normalize_subject(subject: str) -> str:
    # The subject comes from the model: collapse CR/LF and runs of whitespace into single
    # spaces so it can never start a new header (header injection).
    return " ".join(subject.split())[:MAX_SUBJECT_LENGTH]


def build_message(
    *, to: str, subject: str, body: str, reply_to: str, sender: str, request_id: str
) -> EmailMessage:
    message = EmailMessage()  # default policy: rejects CR/LF in header values
    message["From"] = sender
    message["To"] = to
    message["Reply-To"] = reply_to
    message["Subject"] = normalize_subject(subject)
    # Same id as the API response and the decision log line.
    message["X-Request-ID"] = request_id
    message.set_content(body)
    return message


def _deliver(message: EmailMessage, settings: Settings) -> None:
    with smtplib.SMTP(
        settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_s
    ) as smtp:
        smtp.send_message(message)


async def send_mail(
    *, to: str, subject: str, body: str, reply_to: str, request_id: str, settings: Settings
) -> None:
    message = build_message(
        to=to,
        subject=subject,
        body=body,
        reply_to=reply_to,
        sender=settings.mail_from,
        request_id=request_id,
    )
    try:
        # smtplib is blocking; a thread keeps the event loop free for other requests.
        await asyncio.to_thread(_deliver, message, settings)
    except OSError as exc:  # refused, timeout, DNS and every SMTPException
        raise MailDeliveryError(f"{type(exc).__name__}: {exc}") from exc
