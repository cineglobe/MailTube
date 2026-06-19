import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_shell_installer_supports_pipe_to_shell_and_preserves_tailscale_routes() -> None:
    installer = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
    assert "test -t 0" not in installer
    assert "< /dev/tty" in installer
    assert "MAILTUBE_SETUP_FILE" in installer
    assert "run --rm --no-deps secrets-init" in installer
    assert "tailscale serve --bg --yes" in installer
    assert "mailtube configure-tailscale" in installer
    assert "mailtube doctor" in installer
    assert "show_fireworks" in installer
    assert "Detected a previous MailTube setup" in installer
    assert "mailtube refresh-compose" in installer
    assert "MAILTUBE_EXISTING_CONFIG" in installer
    assert 'sudo tailscale serve --https="$TAILSCALE_HTTPS_PORT"' in installer
    assert "dashboard_url=${dashboard_url:-${public_url:-" not in installer


def test_dashboard_url_resolution_runs_under_dash() -> None:
    installer = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
    block = installer.split("# dashboard-url:start", 1)[1].split("# dashboard-url:end", 1)[0]
    script = (
        "set -eu\n"
        "dashboard_url=''\n"
        "public_url='https://mailtube.example.test:36005'\n"
        "host_port='36005'\n"
        f"{block}\n"
        "printf '%s\\n' \"$dashboard_url\"\n"
    )

    dash = shutil.which("dash")
    assert dash is not None
    result = subprocess.run(  # noqa: S603 - fixed executable and test-owned script
        [dash, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout == "https://mailtube.example.test:36005\n"
