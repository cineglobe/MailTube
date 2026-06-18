# Privacy and retention

MailTube has no analytics or telemetry. It stores job metadata, redacted requester identity, local artifacts, and optional private object keys only as needed to operate the queue and deliver results.

Local and remote artifacts expire after 24 hours by default. Cleanup removes application-controlled files and objects; provider lifecycle rules are recommended as backup. SQLite audit and job records can outlive artifacts but must not contain credentials, cookies, full URLs, or presigned links.
