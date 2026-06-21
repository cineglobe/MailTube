# Updates

Automatic signed stable updates are enabled by default in terminal setup and checked every six hours. The host-side timer runs `scripts/update.sh`, which reads the stable manifest, skips when the installed version is current, verifies the immutable image digest and provenance with Cosign, backs up SQLite, refreshes generated Compose plumbing, recreates services, waits for health, and restores the previous image, Compose file, and database on failure.

The installer creates a rootless user systemd timer on Linux, launchd job on macOS, or Task Scheduler entry on Windows. Stable automation stays within the installed major version; major upgrades require operator approval. Disable the setup toggle to omit the schedule, or choose **Disabled** under **Settings → System → Update channel** to make an installed updater skip checks.

The official stable manifest and release-workflow identity are defaults. `MAILTUBE_MANIFEST_URL` and `MAILTUBE_COSIGN_IDENTITY` remain available for a compatible self-hosted release pipeline. Cosign is bundled in the MailTube image, so no host installation is required.

The web UI cannot recreate its own container and does not receive access to the Docker socket. To force an installed Linux updater to check immediately, run `systemctl --user start mailtube-update.service` as the deployment user, then inspect `journalctl --user -u mailtube-update.service`. The **Update channel** setting records the application's release preference; it does not install the host updater.
