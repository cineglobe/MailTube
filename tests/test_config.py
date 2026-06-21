from pathlib import Path

import pytest
from pydantic import ValidationError

from mailtube.config import Settings


def test_secret_file_environment_variant(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    secret = tmp_path / "session-secret"
    secret.write_text("x" * 48 + "\n")
    monkeypatch.setenv("MAILTUBE_SESSION_SECRET_FILE", str(secret))
    settings = Settings(environment="test")
    assert settings.session_secret.get_secret_value() == "x" * 48


def test_comma_separated_environment_lists(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("MAILTUBE_ALLOWED_HOSTS", "localhost,127.0.0.1,mailtube")
    monkeypatch.setenv("MAILTUBE_SENDER_ALLOWLIST", "one@example.com,two@example.com")
    settings = Settings(environment="test")
    assert settings.allowed_hosts == ["localhost", "127.0.0.1", "mailtube"]
    assert settings.sender_allowlist == ["one@example.com", "two@example.com"]


def test_email_polling_defaults_to_fifteen_seconds() -> None:
    assert Settings(environment="test").poll_interval_seconds == 15


@pytest.mark.parametrize(
    "field,value",
    [
        ("imap_host", "imap.gmail.com:993"),
        ("imap_host", "imap.gmail.com:993imap.gmail.com:993"),
        ("smtp_host", "https://smtp.gmail.com"),
    ],
)
def test_mail_hosts_reject_urls_ports_and_concatenated_values(field: str, value: str) -> None:
    with pytest.raises(ValidationError, match="enter the port separately"):
        Settings(environment="test", **{field: value})


def test_mail_hosts_are_trimmed_and_normalized() -> None:
    settings = Settings(
        environment="test",
        imap_host=" IMAP.GMAIL.COM. ",
        smtp_host=" SMTP.GMAIL.COM ",
    )
    assert settings.imap_host == "imap.gmail.com"
    assert settings.smtp_host == "smtp.gmail.com"


def test_empty_cookies_file_is_not_interpreted_as_current_directory() -> None:
    settings = Settings(environment="test", cookies_file="")
    assert settings.cookies_file is None
