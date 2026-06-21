import stat
from io import StringIO
from pathlib import Path

import pytest
from textual.widgets import Input, Select, Switch

from mailtube.setup.wizard import (
    AccessScreen,
    EmailScreen,
    MailTubeSetupApp,
    PreflightScreen,
    WelcomeScreen,
    configure_tailscale,
    load_setup_data,
    refresh_compose,
    run_setup,
    validate_setup_data,
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
        await pilot.pause()
        imap_host = app.screen.query_one("#imap-host", Input)
        smtp_host = app.screen.query_one("#smtp-host", Input)
        assert imap_host.outer_size.height == 3
        assert smtp_host.outer_size.height == 3
        assert imap_host.styles.border.top[0] == "solid"
        app.screen.query_one("#email-preset", Select).value = "generic"
        imap_host.value = "imap.example.com"
        smtp_host.value = "smtp.example.com"
        app.screen.query_one("#email-preset", Select).value = "gmail"
        await pilot.pause()
        assert imap_host.value == "imap.gmail.com"
        assert app.screen.query_one("#imap-port", Input).value == "993"
        assert smtp_host.value == "smtp.gmail.com"
        assert app.screen.query_one("#smtp-port", Input).value == "587"


@pytest.mark.asyncio
async def test_automatic_updates_are_enabled_by_default_in_terminal_setup(tmp_path: Path) -> None:
    app = MailTubeSetupApp(tmp_path)
    async with app.run_test(size=(100, 60)) as pilot:
        app.push_screen("policy")
        await pilot.pause()
        assert app.screen.query_one("#auto-update", Switch).value is True
        app.screen.query_one("#auto-update", Switch).value = False
        app.screen.capture()  # type: ignore[attr-defined]
        assert app.data.auto_update_enabled is False


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
    assert 'MAILTUBE_POLL_INTERVAL_SECONDS="15"' in env
    assert 'MAILTUBE_IMAP_HOST="imap.gmail.com"' in env
    assert 'MAILTUBE_IMAP_PORT="993"' in env
    assert 'MAILTUBE_SMTP_HOST="smtp.gmail.com"' in env
    assert 'MAILTUBE_SMTP_PORT="587"' in env
    assert 'MAILTUBE_UPDATE_CHANNEL="stable"' in env
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


def test_setup_rejects_mail_hosts_containing_ports(tmp_path: Path) -> None:
    app = MailTubeSetupApp(tmp_path)
    app.data.admin_password = "correct horse battery"
    app.data.imap_host = "imap.gmail.com:993imap.gmail.com:993"
    with pytest.raises(ValueError, match="enter the port separately"):
        validate_setup_data(app.data)


def test_disabling_automatic_updates_writes_off_channel(tmp_path: Path) -> None:
    app = MailTubeSetupApp(tmp_path)
    app.data.admin_password = "correct horse battery"
    app.data.delivery_mode = "attachments"
    app.data.storage_preset = "local"
    app.data.auto_update_enabled = False
    app.write_configuration()
    assert 'MAILTUBE_UPDATE_CHANNEL="off"' in (tmp_path / ".env").read_text()


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


def test_refresh_compose_preserves_preferences_and_secrets_but_updates_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = MailTubeSetupApp(tmp_path)
    app.data.admin_password = "correct horse battery"
    app.data.delivery_mode = "attachments"
    app.data.storage_preset = "local"
    app.write_configuration()
    env_before = (tmp_path / ".env").read_bytes()
    secret_before = (tmp_path / "secrets" / "session_secret").read_bytes()
    (tmp_path / "compose.yml").write_text("old generated compose", encoding="utf-8")

    monkeypatch.setenv("MAILTUBE_IMAGE", "ghcr.io/cineglobe/mailtube@sha256:new")
    refreshed = refresh_compose(tmp_path)

    assert "secrets-init:" in refreshed.read_text(encoding="utf-8")
    env_after = (tmp_path / ".env").read_bytes()
    assert env_after != env_before
    assert b'MAILTUBE_IMAGE="ghcr.io/cineglobe/mailtube@sha256:new"' in env_after
    assert b'MAILTUBE_HTTP_PORT="8080"' in env_after
    assert (tmp_path / "secrets" / "session_secret").read_bytes() == secret_before
    assert stat.S_IMODE(refreshed.stat().st_mode) == 0o600


def test_configure_tailscale_adds_https_origin_and_preserves_secrets(tmp_path: Path) -> None:
    app = MailTubeSetupApp(tmp_path)
    app.data.admin_password = "correct horse battery"
    app.data.delivery_mode = "attachments"
    app.data.storage_preset = "local"
    app.write_configuration()
    secret_before = (tmp_path / "secrets" / "session_secret").read_bytes()

    url = configure_tailscale(tmp_path, "OpenClaw.TailExample.ts.net.")

    env = (tmp_path / ".env").read_text(encoding="utf-8")
    assert url == "https://openclaw.tailexample.ts.net"
    assert 'MAILTUBE_PUBLIC_URL="https://openclaw.tailexample.ts.net"' in env
    assert "openclaw.tailexample.ts.net" in env
    assert 'MAILTUBE_SECURE_COOKIES="true"' in env
    assert (tmp_path / "secrets" / "session_secret").read_bytes() == secret_before
