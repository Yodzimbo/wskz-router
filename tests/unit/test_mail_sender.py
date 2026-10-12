import pytest

from app.config import Settings
from app.mail import sender
from app.mail.sender import MailDeliveryError, send_mail
from tests.unit.conftest import FakeSMTP

SETTINGS = Settings(smtp_host="smtp.test", smtp_port=2525, mail_from="router@example.com")


async def test_message_headers(fake_smtp: type[FakeSMTP]) -> None:
    await send_mail(
        to="dept@example.com",
        subject="Awaria komputera",
        body="Treść",
        reply_to="jan.nowak@example.com",
        settings=SETTINGS,
    )

    assert fake_smtp.connections == [("smtp.test", 2525, SETTINGS.smtp_timeout_s)]
    [message] = fake_smtp.sent
    assert message["To"] == "dept@example.com"
    assert message["From"] == "router@example.com"
    assert message["Reply-To"] == "jan.nowak@example.com"
    assert message["Subject"] == "Awaria komputera"
    assert message.get_content().strip() == "Treść"


async def test_subject_crlf_is_flattened(fake_smtp: type[FakeSMTP]) -> None:
    await send_mail(
        to="dept@example.com",
        subject="a\r\nBcc: x@example.com\n  b",
        body="x",
        reply_to="jan.nowak@example.com",
        settings=SETTINGS,
    )

    [message] = fake_smtp.sent
    assert message["Subject"] == "a Bcc: x@example.com b"
    assert message["Bcc"] is None
    assert "\nBcc:" not in message.as_string()


async def test_long_subject_is_truncated(fake_smtp: type[FakeSMTP]) -> None:
    await send_mail(
        to="d@example.com", subject="x" * 500, body="x", reply_to="a@example.com", settings=SETTINGS
    )

    assert len(fake_smtp.sent[0]["Subject"]) == sender.MAX_SUBJECT_LENGTH


@pytest.mark.parametrize(
    "error", [ConnectionRefusedError(111, "refused"), TimeoutError("timed out")]
)
async def test_smtp_error_raises_mail_delivery_error(
    fake_smtp: type[FakeSMTP], error: OSError
) -> None:
    fake_smtp.error = error

    with pytest.raises(MailDeliveryError):
        await send_mail(
            to="d@example.com", subject="s", body="b", reply_to="a@example.com", settings=SETTINGS
        )

    assert fake_smtp.sent == []
