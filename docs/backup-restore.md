# Backup and restore

Run `mailtube backup /data/backups/mailtube.db` inside the container. This uses SQLite's online backup API and is safe while the service is running. Copy the resulting file and the protected configuration directory to encrypted backup storage.

To restore, stop MailTube, preserve the current database, replace `/data/mailtube.db` with a verified backup owned by UID/GID 10001, and start the same or a schema-compatible newer image. Run `mailtube doctor` and inspect health before accepting requests. Object-storage contents require a separate provider backup policy.
