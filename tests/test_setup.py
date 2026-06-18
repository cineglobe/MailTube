import stat
from io import StringIO
from pathlib import Path

import pytest
from textual.widgets import Input

from mailtube.setup.wizard import (
    AccessScreen,
    EmailScreen,
    MailTubeSetupApp,
    PreflightScreen,
    WelcomeScreen,
    load_setup_data,
    run_setup,
)


@pytest.mark.asyncio
async def test_wizard_keyboard_flow_reaches_email_screen(tmp_path: Path) -> None:
    app = MailTubeSetupApp(tmp_path)
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, WelcomeScreen)
        await pilot.click("#go-preflight")
        assert isinstance(app.screen, PreflightScreen)
        await pilot.click("#go-access")
        assert isinstance(app.screen, AccessScreen)
        app.screen.query_one("#admin-password", Input).value = "correct horse battery"
        app.screen.query_one("#admin-confirm", Input).value = "correct horse battery"
        await pilot.click("#go-email")
        assert isinstance(app.screen, EmailScreen)


def test_generated_configuration_is_private_and_uses_separate_host_port(tmp_path: Path) -> None:
    app = MailTubeSetupApp(tmp_path)
    app.data.admin_password = "correct horse battery"
    app.data.storage_backend = "local"
    app.data.delivery_mode = "attachments"
    app.data.port = 8765
    app.write_configuration()
    env_path = tmp_path / ".env"
    compose_path = tmp_path / "compose.yml"
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(compose_path.stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "secrets" / "session_secret").stat().st_mode) == 0o600
    env = env_path.read_text()
    assert 'MAILTUBE_HTTP_PORT="8765"' in env
    assert 'MAILTUBE_PORT="8080"' in env
    assert "correct horse battery" not in env
    assert "MAILTUBE_SESSION_SECRET_FILE" in env
    compose = compose_path.read_text()
    assert "${MAILTUBE_BIND_ADDRESS}:${MAILTUBE_HTTP_PORT}:8080" in compose
    assert "secrets-init:" in compose
    assert "mailtube-secrets:/run/secrets:ro" in compose
    assert "${MAILTUBE_COOKIES_SOURCE}:/cookie-source:ro" in compose
    assert ":/source/youtube-cookies.txt:ro" not in compose
    assert "condition: service_completed_successfully" in compose
    assert "cap_add: [DAC_OVERRIDE]" in compose
    assert "init: true" not in compose
    assert "\nsecrets:\n" not in compose


def test_non_interactive_setup_rejects_open_permissions(tmp_path: Path) -> None:
    setup_path = tmp_path / "setup.json"
    setup_path.write_text("{}", encoding="utf-8")
    setup_path.chmod(0o644)
    with pytest.raises(ValueError, match="mode 0600"):
        load_setup_data(setup_path)


def test_non_interactive_setup_writes_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_path = tmp_path / "setup.json"
    setup_path.write_text(
        """{
          "bind_mode": "localhost",
          "port": 8123,
          "public_url": "http://127.0.0.1:8123",
          "allowed_hosts": ["localhost", "127.0.0.1"],
          "admin_password": "correct horse battery",
          "delivery_mode": "attachments",
          "storage_preset": "local"
        }""",
        encoding="utf-8",
    )
    setup_path.chmod(0o600)
    config_dir = tmp_path / "generated"
    monkeypatch.setenv("MAILTUBE_CONFIG_DIR", str(config_dir))
    run_setup(setup_path)
    assert 'MAILTUBE_HTTP_PORT="8123"' in (config_dir / ".env").read_text()
    assert "secrets-init:" in (config_dir / "compose.yml").read_text()


def test_non_interactive_setup_accepts_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.stdin",
        StringIO(
            """{
              "admin_password": "correct horse battery",
              "delivery_mode": "attachments",
              "storage_preset": "local"
            }"""
        ),
    )
    data = load_setup_data(Path("-"))
    assert data.storage_backend == "local"
