from __future__ import annotations

import asyncio
import email
import imaplib
import json
import logging
import re
import shutil
import smtplib
from datetime import UTC, datetime, timedelta
from email.header import decode_header
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from mailtube.config import Settings
from mailtube.db import Database
from mailtube.email.parser import message_body, parse_requests
from mailtube.storage import Storage

logger = logging.getLogger(__name__)


def decode_subject(value: str | None) -> str:
    if not value:
        return "MailTube request"
    decoded: list[str] = []
    for part, encoding in decode_header(value):
        if isinstance(part, bytes):
            decoded.append(part.decode(encoding or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return re.sub(r"[\x00-\x1f\x7f]+", " ", "".join(decoded))[:500].strip()


def human_size(size: int | None) -> str:
    if not size:
        return ""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return ""


class EmailService:
    def __init__(self, settings: Settings, db: Database, storage: Storage) -> None:
        self.settings = settings
        self.db = db
        self.storage = storage
        template_dir = Path(__file__).resolve().parents[1] / "templates" / "email"
        self.templates = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        poll = asyncio.create_task(self._poll_loop(), name="mailtube-imap")
        notify = asyncio.create_task(self._notify_loop(), name="mailtube-email-notifier")
        try:
            await asyncio.gather(poll, notify)
        finally:
            poll.cancel()
            notify.cancel()

    async def stop(self) -> None:
        self._stopped.set()

    async def _poll_loop(self) -> None:
        while not self._stopped.is_set():
            try:
                await asyncio.to_thread(self.poll_once)
            except Exception as exc:
                logger.warning("IMAP poll failed: %s", type(exc).__name__)
            try:
                await asyncio.wait_for(
                    self._stopped.wait(), timeout=self.settings.poll_interval_seconds
                )
            except TimeoutError:
                pass

    async def _notify_loop(self) -> None:
        while not self._stopped.is_set():
            for batch in self.db.ready_email_batches():
                try:
                    await asyncio.to_thread(self.send_batch_result, batch)
                    self.db.mark_batch_reply(str(batch["id"]), "sent")
                except Exception as exc:
                    logger.warning(
                        "Email reply failed for batch %s: %s", batch["id"], type(exc).__name__
                    )
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=5)
            except TimeoutError:
                pass

    def _runtime_sender_policy(self) -> tuple[str, set[str]]:
        runtime = self.db.get_runtime_settings()
        policy = str(runtime.get("sender_policy", self.settings.sender_policy))
        allowlist = runtime.get("sender_allowlist", self.settings.sender_allowlist)
        return policy, {str(address).lower() for address in allowlist}

    def poll_once(self) -> None:
        with imaplib.IMAP4_SSL(self.settings.imap_host, self.settings.imap_port) as mailbox:
            mailbox.login(
                self.settings.imap_username, self.settings.imap_password.get_secret_value()
            )
            mailbox.select(self.settings.imap_folder)
            uid_response = mailbox.response("UIDVALIDITY")[1]
            uidvalidity = (
                uid_response[0].decode(errors="replace")
                if uid_response and uid_response[0]
                else "unknown"
            )
            status, data = mailbox.uid("search", None, "UNSEEN")  # type: ignore[arg-type]
            if status != "OK" or not data or not data[0]:
                return
            for raw_uid in data[0].split():
                uid = raw_uid.decode()
                if self.db.has_mail_message(self.settings.imap_username, uidvalidity, uid):
                    mailbox.uid("store", uid, "+FLAGS", "\\Seen")
                    continue
                self._process_uid(mailbox, uid, uidvalidity)

    def _process_uid(self, mailbox: imaplib.IMAP4_SSL, raw_uid: str, uidvalidity: str) -> None:
        status, data = mailbox.uid("fetch", raw_uid, "(RFC822)")
        if status != "OK" or not data or not isinstance(data[0], tuple):
            return
        raw = data[0][1]
        if not isinstance(raw, bytes):
            return
        if len(raw) > 2 * 1024 * 1024:
            mailbox.uid("store", raw_uid, "+FLAGS", "\\Seen")
            return
        message = email.message_from_bytes(raw)
        if message.get("X-MailTube-Generated") == "yes":
            mailbox.uid("store", raw_uid, "+FLAGS", "\\Seen")
            return
        auto_submitted = (message.get("Auto-Submitted") or "").lower()
        if auto_submitted and auto_submitted != "no":
            mailbox.uid("store", raw_uid, "+FLAGS", "\\Seen")
            return
        sender = parseaddr(message.get("Reply-To") or message.get("From") or "")[1].lower()
        if not sender or sender == self.settings.smtp_from.lower():
            mailbox.uid("store", raw_uid, "+FLAGS", "\\Seen")
            return
        policy, allowlist = self._runtime_sender_policy()
        subject = decode_subject(message.get("Subject"))
        if policy == "allowlist" and sender not in allowlist:
            self.send_error(
                sender, subject, "This sender is not in the MailTube allowlist.", message
            )
            mailbox.uid("store", raw_uid, "+FLAGS", "\\Seen")
            return
        since = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        if (
            self.db.recent_email_batch_count(sender, since)
            >= self.settings.max_email_requests_per_hour
        ):
            self.send_error(
                sender,
                subject,
                "This sender has reached the hourly MailTube request limit.",
                message,
            )
            mailbox.uid("store", raw_uid, "+FLAGS", "\\Seen")
            return
        body = message_body(message)
        defaults = {
            "mp4": self.settings.default_mp4_quality,
            "mp3": self.settings.default_mp3_quality,
            "wav": self.settings.default_wav_quality,
        }
        requests, issues = parse_requests(
            body,
            default_format=self.settings.default_format,
            defaults=defaults,
            max_items=self.settings.max_urls_per_batch,
        )
        if not requests and not issues:
            requests, issues = parse_requests(
                subject,
                default_format=self.settings.default_format,
                defaults=defaults,
                max_items=1,
            )
        if not requests:
            reason = issues[0].message if issues else "No valid YouTube links were found."
            self.send_error(sender, subject, reason, message)
            mailbox.uid("store", raw_uid, "+FLAGS", "\\Seen")
            return
        required_free = self.settings.max_file_bytes * self.settings.max_concurrent_jobs
        if shutil.disk_usage(self.settings.work_dir).free < required_free:
            self.send_error(
                sender,
                subject,
                "MailTube does not currently have enough free work-volume space.",
                message,
            )
            mailbox.uid("store", raw_uid, "+FLAGS", "\\Seen")
            return
        message_id = message.get("Message-ID")
        batch_id, _ = self.db.create_batch(
            source="email",
            items=[request.as_dict() for request in requests],
            requester=sender,
            subject=subject,
            message_id=message_id,
            message_references=message.get("References"),
            request_issues=[f"Line {issue.line}: {issue.message}" for issue in issues],
            idempotency_key=f"email:{message_id}" if message_id else None,
        )
        self.db.record_mail_message(
            mailbox=self.settings.imap_username,
            uidvalidity=uidvalidity,
            uid=raw_uid,
            message_id=message_id,
            batch_id=batch_id,
        )
        mailbox.uid("store", raw_uid, "+FLAGS", "\\Seen")

    def _smtp_send(self, message: EmailMessage) -> None:
        if self.settings.smtp_security == "tls":
            with smtplib.SMTP_SSL(self.settings.smtp_host, self.settings.smtp_port) as server:
                server.login(
                    self.settings.smtp_username, self.settings.smtp_password.get_secret_value()
                )
                server.send_message(message)
        else:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port) as server:
                server.starttls()
                server.login(
                    self.settings.smtp_username, self.settings.smtp_password.get_secret_value()
                )
                server.send_message(message)

    def _base_message(
        self,
        to_address: str,
        subject: str,
        message_id: str | None,
        references: str | None,
    ) -> EmailMessage:
        result = EmailMessage()
        result["From"] = f"{self.settings.smtp_from_name} <{self.settings.smtp_from}>"
        result["To"] = to_address
        result["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        result["Auto-Submitted"] = "auto-replied"
        result["X-MailTube-Generated"] = "yes"
        if message_id:
            result["In-Reply-To"] = message_id
            result["References"] = f"{references or ''} {message_id}".strip()
        return result

    def send_error(
        self, to_address: str, subject: str, reason: str, original: Any | None = None
    ) -> None:
        message = self._base_message(
            to_address,
            subject,
            original.get("Message-ID") if original else None,
            original.get("References") if original else None,
        )
        safe_reason = reason[:500]
        message.set_content(f"MailTube could not start your request.\n\n{safe_reason}")
        html_body = self.templates.get_template("error.html.j2").render(reason=safe_reason)
        message.add_alternative(html_body, subtype="html")
        self._smtp_send(message)

    def send_batch_result(self, batch: dict[str, Any]) -> None:
        jobs = self.db.jobs_for_batch(str(batch["id"]))
        rendered: list[dict[str, Any]] = []
        attachments: list[dict[str, Any]] = []
        attachment_limit = self.settings.max_attachment_mb * 1024 * 1024
        selected_attachment_size = 0
        for job in jobs:
            item: dict[str, Any] = {
                "title": str(job.get("title") or "YouTube conversion"),
                "format": str(job["requested_format"]).upper(),
                "quality": str(job["requested_quality"]),
                "size": human_size(job.get("size_bytes")),
                "url": None,
                "error": None,
            }
            if job["state"] != "ready":
                item["error"] = str(job.get("error_message") or "Conversion failed")[:300]
            elif self.settings.delivery_mode == "links" and job.get("object_key"):
                item["url"] = self.storage.presign(
                    str(job["object_key"]),
                    str(job["filename"]),
                    self.settings.retention_hours * 3600,
                )
            elif job.get("local_path"):
                size = int(job.get("size_bytes") or 0)
                fits = selected_attachment_size + size <= attachment_limit
                if self.settings.delivery_mode in {"attachments", "hybrid"} and fits:
                    attachments.append(job)
                    selected_attachment_size += size
                elif job.get("object_key"):
                    item["url"] = self.storage.presign(
                        str(job["object_key"]),
                        str(job["filename"]),
                        self.settings.retention_hours * 3600,
                    )
                else:
                    item["error"] = "The file is too large for the configured attachment limit."
            rendered.append(item)
        try:
            request_issues = json.loads(str(batch.get("request_issues") or "[]"))
        except json.JSONDecodeError:
            request_issues = []
        for issue in request_issues:
            rendered.append(
                {
                    "title": "Request not queued",
                    "format": "",
                    "quality": "",
                    "size": "",
                    "url": None,
                    "error": str(issue)[:300],
                }
            )
        message = self._base_message(
            str(batch["requester"]),
            str(batch.get("subject") or "MailTube request"),
            batch.get("message_id"),
            batch.get("message_references"),
        )
        ready = sum(1 for job in jobs if job["state"] == "ready")
        message.set_content(
            f"MailTube completed {ready} of {len(jobs)} requested conversions. "
            f"Download links expire after {self.settings.retention_hours} hours."
        )
        message.add_alternative(
            self.templates.get_template("result.html.j2").render(
                items=rendered, retention_hours=self.settings.retention_hours
            ),
            subtype="html",
        )
        for artifact in attachments:
            path = Path(str(artifact["local_path"]))
            if not path.is_file():
                continue
            content_type = str(artifact.get("content_type") or "application/octet-stream")
            major, minor = content_type.split("/", 1)
            message.add_attachment(
                path.read_bytes(),
                maintype=major,
                subtype=minor,
                filename=str(artifact["filename"]),
            )
        self._smtp_send(message)

    def test_connections(self) -> dict[str, bool | str]:
        try:
            with imaplib.IMAP4_SSL(self.settings.imap_host, self.settings.imap_port) as mailbox:
                mailbox.login(
                    self.settings.imap_username, self.settings.imap_password.get_secret_value()
                )
            if self.settings.smtp_security == "tls":
                server: smtplib.SMTP = smtplib.SMTP_SSL(
                    self.settings.smtp_host, self.settings.smtp_port
                )
            else:
                server = smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port)
                server.starttls()
            with server:
                server.login(
                    self.settings.smtp_username, self.settings.smtp_password.get_secret_value()
                )
            return {"ok": True, "detail": "IMAP and SMTP authentication succeeded"}
        except Exception as exc:
            return {"ok": False, "detail": f"Email test failed: {type(exc).__name__}"}
