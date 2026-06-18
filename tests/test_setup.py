import stat
from pathlib import Path

import pytest
from textual.widgets import Input

from mailtube.setup.wizard import (
    AccessScreen,
    EmailScreen,
    MailTubeSetupApp,
    PreflightScreen,
    WelcomeScreen,
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
    assert "${MAILTUBE_BIND_ADDRESS}:${MAILTUBE_HTTP_PORT}:8080" in compose_path.read_text()
