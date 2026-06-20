# Gmail

Use a dedicated mailbox. Enable Google 2-Step Verification, create an App Password, then select the Gmail preset in setup. Some managed, security-key-only, or Advanced Protection accounts cannot create App Passwords.

MailTube uses `imap.gmail.com:993` with TLS and `smtp.gmail.com:587` with STARTTLS. The wizard tests both logins before activation. Gmail limits total message attachments to 25 MB; encoding overhead means MailTube's default safe attachment total is 18 MiB. S3 links are recommended.

The mailbox is checked every 15 seconds by default. The interval can be changed in **Settings → Email**. MailTube accepts a request sent from the configured mailbox to itself; loop protection relies on generated-message headers rather than blocking the mailbox's own sender address. **Health → Email** reports the last successful poll or a sanitized connection failure, and its Test button verifies both IMAP and SMTP authentication.

If Google rejects login, confirm IMAP access is available, the address is exact, the value is an App Password rather than the account password, and the host is not blocked by an organization policy.
