# Configuration

Environment variables use the `MAILTUBE_` prefix. Initial credentials are written to mode-`0600` host files. A one-shot Compose service copies them into a Docker-managed volume, and the application mounts that volume read-only. This avoids host UID mismatches while keeping credentials out of `docker inspect` environment output.

The authenticated dashboard can change email, SMTP, sender policy, delivery, S3-compatible storage, conversion defaults, resource limits, retention, administrator credentials, and the email polling interval. Password and secret-key inputs are write-only. Dashboard-provided secrets are encrypted with AES-GCM using key material derived from the instance session secret before they are persisted in SQLite; plaintext values are never returned by the API. Non-secret overrides are also stored in SQLite and survive container upgrades.

Host publication settings—including the Docker bind address and port, Tailscale Serve route, allowed Host headers, and secure-cookie transport—remain installer-managed. Changing these from inside the container would require Docker-socket or unrestricted host access, which MailTube intentionally does not have. Rerun the installer and resume the existing setup to change them safely.

Critical values include bind/public URL/allowed hosts, Argon2id password hash and session secret, concurrency and batch/duration/file limits, retention, IMAP/SMTP credentials and sender policy, delivery mode, S3 credentials, cookies path, and PO-provider URL. Dashboard changes apply immediately. Restart after manually changing environment-backed host configuration.

Keep allowlist-only sender policy unless broad access is intentional. Any-sender mode never disables batch, duration, disk, queue, or file-size limits. Cookie files must use Netscape format, be read-only in the container, and mode `0600` on the host.

For automation, run `mailtube setup --non-interactive /path/to/setup.json` or set `MAILTUBE_SETUP_FILE` when using the release installer. Start with `docs/setup.example.json`. The JSON file must be owner-only on POSIX systems and may contain only documented setup fields.
