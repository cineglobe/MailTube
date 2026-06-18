from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_shell_installer_supports_pipe_to_shell_and_preserves_tailscale_routes() -> None:
    installer = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
    assert "test -t 0" not in installer
    assert "< /dev/tty" in installer
    assert "MAILTUBE_SETUP_FILE" in installer
    assert "run --rm --no-deps secrets-init" in installer
    assert "tailscale serve --bg" not in installer
    assert "tailscale serve --https=<HTTPS_PORT>" in installer
