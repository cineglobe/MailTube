# Installation

Use a 64-bit `amd64` or `arm64` host with Docker Engine/Desktop and Compose v2. Home-network deployment is recommended; public hosting-provider IP addresses are frequently restricted by YouTube.

Run the published installer directly:

```bash
curl -fsSL https://github.com/cineglobe/MailTube/releases/latest/download/install.sh | sh
```

The script reopens `/dev/tty` for the Textual wizard when its stdin is a pipe. It checks architecture, pulls the image, resolves an immutable digest, runs setup without a Docker-socket mount, validates Compose, initializes and verifies the private secrets volume, starts services, waits for health, and installs the default six-hour signed stable-update timer when enabled in setup.

For unattended deployment, copy `docs/setup.example.json`, fill it in, restrict it to mode `0600`, and set `MAILTUBE_SETUP_FILE` to its absolute path before running the installer. Unknown fields and unsafe permissions are rejected. The file contains credentials; delete or archive it securely after setup.

The generated configuration lives at `~/.config/mailtube` by default. It is owner-readable only. Back it up securely. For Windows, run `scripts/install.ps1` in PowerShell with Docker Desktop active.

After setup, use `docker compose --env-file ~/.config/mailtube/.env -f ~/.config/mailtube/compose.yml logs -f` for logs and `mailtube doctor` inside the container for a redacted report.

If the configured public URL uses HTTPS, MailTube enables Secure session cookies. Use that HTTPS address for login and authenticated diagnostics. A browser correctly refuses to send those cookies to `http://127.0.0.1`, even though the local health endpoint remains available.

## Resume a partial installation

Running the installer again detects a previously written configuration in `~/.config/mailtube`. Choose **resume** to keep the existing preferences and secrets, refresh generated Compose plumbing from the current image, and continue validation and startup. Choose **start fresh** to move the old directory to a timestamped backup before opening the wizard again. Automation can set `MAILTUBE_EXISTING_CONFIG=resume` or `MAILTUBE_EXISTING_CONFIG=replace` explicitly.
