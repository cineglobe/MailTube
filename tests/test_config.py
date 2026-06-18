from pathlib import Path

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
