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
