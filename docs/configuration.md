# Configuration

Environment variables use the `MAILTUBE_` prefix. The setup wizard owns credentials; the dashboard exposes only safe operational settings. Generated credentials remain in mode-`0600` host files. A one-shot Compose service copies them into a Docker-managed volume, and the application mounts that volume read-only. This avoids host UID mismatches while keeping credentials out of `docker inspect` environment output.

Critical values include bind/public URL/allowed hosts, Argon2id password hash and session secret, concurrency and batch/duration/file limits, retention, IMAP/SMTP credentials and sender policy, delivery mode, S3 credentials, cookies path, and PO-provider URL. Restart after changing environment-backed values.

Keep allowlist-only sender policy unless broad access is intentional. Any-sender mode never disables batch, duration, disk, queue, or file-size limits. Cookie files must use Netscape format, be read-only in the container, and mode `0600` on the host.

For automation, run `mailtube setup --non-interactive /path/to/setup.json` or set `MAILTUBE_SETUP_FILE` when using the release installer. Start with `docs/setup.example.json`. The JSON file must be owner-only on POSIX systems and may contain only documented setup fields.
