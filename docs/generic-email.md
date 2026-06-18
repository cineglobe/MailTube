# Generic IMAP and SMTP

Configure the IMAP host, port, TLS mode, mailbox folder, username, and password separately from SMTP host, port, STARTTLS/TLS mode, username, password, and From address. Use provider-specific app passwords where available.

MailTube polls by UIDVALIDITY and UID, records Message-ID idempotency, ignores automatic/bounce/self-generated mail, marks messages seen only after the batch is durable, and sends one threaded result for the whole email. Attachments are never treated as commands.
