from email.message import EmailMessage
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from mailtube.config import Settings
from mailtube.email.service import EmailService


class FakeDatabase:
    def __init__(self) -> None:
        self.created = False

    def get_runtime_settings(self) -> dict[str, Any]:
        return {}

    def recent_email_batch_count(self, requester: str, since: str) -> int:
        return 0

    def create_batch(self, **kwargs: Any) -> tuple[str, list[str]]:
        self.created = True
        return "batch", ["job"]

    def record_mail_message(self, **kwargs: Any) -> None:
        return None


class FakeMailbox:
    def __init__(self, raw: bytes) -> None:
        self.raw = raw
        self.seen = False

    def uid(self, command: str, *args: Any) -> tuple[str, list[Any]]:
        if command == "fetch":
            return "OK", [(b"1 (RFC822)", self.raw)]
        if command == "store":
            self.seen = True
            return "OK", []
        raise AssertionError(command)


class FakeStorage:
    pass


class FakeResultDatabase(FakeDatabase):
    def jobs_for_batch(self, batch_id: str) -> list[dict[str, Any]]:
        return [
            {
                "state": "failed",
                "title": None,
                "requested_format": "mp4",
                "requested_quality": "1080p",
                "error_message": "YouTube requested additional verification",
                "size_bytes": None,
            }
        ]


def test_mailbox_can_accept_a_request_sent_from_its_own_address(tmp_path: Path) -> None:
    message = EmailMessage()
    message["From"] = "mailtube@example.com"
    message["To"] = "mailtube@example.com"
    message["Subject"] = "convert"
    message["Message-ID"] = "<self-test@example.com>"
    message.set_content("https://youtu.be/dQw4w9WgXcQ mp3 192k")
    mailbox = FakeMailbox(message.as_bytes())
    database = FakeDatabase()
    work = tmp_path / "work"
    work.mkdir()
    settings = Settings(
        environment="test",
        work_dir=work,
        smtp_from="mailtube@example.com",
        sender_policy="any",
        imap_password=SecretStr("app-password"),
        smtp_password=SecretStr("app-password"),
    )
    service = EmailService(settings, database, FakeStorage())  # type: ignore[arg-type]

    service._process_uid(mailbox, "1", "42")  # type: ignore[arg-type]

    assert database.created is True
    assert mailbox.seen is True


def test_failed_batch_email_does_not_claim_files_are_ready(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    settings = Settings(
        environment="test",
        work_dir=work,
        smtp_from="mailtube@example.com",
        imap_password=SecretStr("app-password"),
        smtp_password=SecretStr("app-password"),
    )
    service = EmailService(settings, FakeResultDatabase(), FakeStorage())  # type: ignore[arg-type]
    sent: list[EmailMessage] = []
    service._smtp_send = sent.append  # type: ignore[method-assign]

    service.send_batch_result(
        {
            "id": "batch",
            "requester": "requester@example.com",
            "subject": "convert",
            "request_issues": "[]",
        }
    )

    assert len(sent) == 1
    plain = sent[0].get_body(preferencelist=("plain",))
    html = sent[0].get_body(preferencelist=("html",))
    assert plain is not None
    assert html is not None
    assert "Your request could not be completed" in plain.get_content()
    assert "Your files are ready" not in html.get_content()


def test_failed_batch_email_uses_custom_html_template(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    settings = Settings(
        environment="test",
        work_dir=work,
        smtp_from="mailtube@example.com",
        imap_password=SecretStr("app-password"),
        smtp_password=SecretStr("app-password"),
        email_failure_template_html="<html><body>Custom failure: {{ items[0].error }}</body></html>",
    )
    service = EmailService(settings, FakeResultDatabase(), FakeStorage())  # type: ignore[arg-type]
    sent: list[EmailMessage] = []
    service._smtp_send = sent.append  # type: ignore[method-assign]

    service.send_batch_result(
        {
            "id": "batch",
            "requester": "requester@example.com",
            "subject": "convert",
            "request_issues": "[]",
        }
    )

    html = sent[0].get_body(preferencelist=("html",))
    assert html is not None
    assert "Custom failure: YouTube requested additional verification" in html.get_content()


def test_start_error_email_uses_custom_html_template(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    settings = Settings(
        environment="test",
        work_dir=work,
        smtp_from="mailtube@example.com",
        imap_password=SecretStr("app-password"),
        smtp_password=SecretStr("app-password"),
        email_error_template_html="<html><body>Rejected: {{ reason }}</body></html>",
    )
    service = EmailService(settings, FakeResultDatabase(), FakeStorage())  # type: ignore[arg-type]
    sent: list[EmailMessage] = []
    service._smtp_send = sent.append  # type: ignore[method-assign]

    service.send_error("requester@example.com", "convert", "No supported links")

    html = sent[0].get_body(preferencelist=("html",))
    assert html is not None
    assert "Rejected: No supported links" in html.get_content()
