# Security model

MailTube is a single-admin appliance, not a public conversion API. Its trust boundary includes the authenticated dashboard, configured mailbox, private object bucket, and host-controlled configuration.

Controls include Argon2id, hashed opaque sessions, SameSite cookies, mutation CSRF tokens, login lockout, host validation, restrictive response headers, strict URL normalization, argument-array subprocesses, UUID paths, non-root/read-only containers, queue and disk limits, private object keys, and redacted diagnostics.

The dashboard is a static Next.js export. Its CSP permits the framework's inline bootstrap scripts but denies third-party scripts, frames, plugins, remote images, cross-origin connections, and form targets. No user-controlled content is rendered into the static HTML.

Cookies can grant YouTube account access. Prefer no cookies; if unavoidable, use a dedicated account and protect the file as a secret. Presigned URLs grant access until expiry. Never publish `.env`, diagnostic output before review, downloaded media, or signed URLs.

The update service does not mount the Docker socket. A host scheduler verifies the signed image and rolls back after failed health checks.
