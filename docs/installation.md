# Installation

Use a 64-bit `amd64` or `arm64` host with Docker Engine/Desktop and Compose v2. Home-network deployment is recommended; public hosting-provider IP addresses are frequently restricted by YouTube.

Run `scripts/install.sh` from a trusted checkout, or use the published raw URL after releases exist. The script checks architecture, pulls the image, resolves an immutable digest, runs the Textual wizard without a Docker-socket mount, validates Compose, starts services, and waits for health.

The generated configuration lives at `~/.config/mailtube` by default. It is owner-readable only. Back it up securely. For Windows, run `scripts/install.ps1` in PowerShell with Docker Desktop active.

After setup, use `docker compose --env-file ~/.config/mailtube/.env -f ~/.config/mailtube/compose.yml logs -f` for logs and `mailtube doctor` inside the container for a redacted report.
