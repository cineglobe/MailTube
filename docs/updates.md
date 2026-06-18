# Updates

Use immutable release image digests. `scripts/update.sh` reads a stable manifest, verifies the image with keyless Cosign identity, backs up SQLite, pulls and recreates services, waits for health, and restores the previous digest on failure.

Install it as a rootless user systemd timer on Linux, launchd job on macOS, or Task Scheduler entry on Windows. Add a randomized daily delay. Stable automation stays within the installed major version; review major upgrades and migration notes manually.

Set `MAILTUBE_MANIFEST_URL` to the release's `stable-manifest.json` URL and `MAILTUBE_COSIGN_IDENTITY` to the exact GitHub Actions release-workflow certificate identity, then run `scripts/install-updater.sh`. The one-command installer does this automatically when both variables are already present. `cosign` and `jq` are required on the host.
