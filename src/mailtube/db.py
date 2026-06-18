from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS batches (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL CHECK(source IN ('web','email')),
    requester TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    subject TEXT,
    message_id TEXT,
    message_references TEXT,
    request_issues TEXT NOT NULL DEFAULT '[]',
    reply_status TEXT NOT NULL DEFAULT 'pending',
    idempotency_key TEXT UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mail_messages (
    id TEXT PRIMARY KEY,
    mailbox TEXT NOT NULL,
    uidvalidity TEXT NOT NULL,
    uid TEXT NOT NULL,
    message_id TEXT,
    batch_id TEXT NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    processed_at TEXT NOT NULL,
    UNIQUE(mailbox, uidvalidity, uid),
    UNIQUE(message_id)
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    source TEXT NOT NULL CHECK(source IN ('web','email')),
    input_url TEXT NOT NULL,
    video_id TEXT NOT NULL,
    requested_format TEXT NOT NULL,
    requested_quality TEXT NOT NULL,
    actual_format TEXT,
    actual_quality TEXT,
    title TEXT,
    duration_seconds REAL,
    progress REAL NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'queued',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    expires_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_state_created ON jobs(state, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_batch ON jobs(batch_id);
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
    local_path TEXT,
    object_key TEXT,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    csrf_token TEXT NOT NULL,
    username TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._lock, self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(SCHEMA)
            columns = {
                str(row["name"]) for row in conn.execute("PRAGMA table_info(batches)").fetchall()
            }
            if "request_issues" not in columns:
                conn.execute(
                    "ALTER TABLE batches ADD COLUMN request_issues TEXT NOT NULL DEFAULT '[]'"
                )
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(1, ?)",
                (utcnow(),),
            )
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(2, ?)",
                (utcnow(),),
            )
            conn.execute(
                "UPDATE jobs SET state='queued', progress=0, updated_at=? "
                "WHERE state IN ('inspecting','downloading','processing','uploading')",
                (utcnow(),),
            )

    def create_batch(
        self,
        *,
        source: str,
        items: Sequence[dict[str, str]],
        requester: str | None = None,
        subject: str | None = None,
        message_id: str | None = None,
        message_references: str | None = None,
        request_issues: Sequence[str] | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[str, list[str]]:
        now = utcnow()
        batch_id = str(uuid.uuid4())
        job_ids: list[str] = []
        with self._lock, self.connect() as conn:
            if idempotency_key:
                row = conn.execute(
                    "SELECT id FROM batches WHERE idempotency_key=?", (idempotency_key,)
                ).fetchone()
                if row:
                    existing = conn.execute(
                        "SELECT id FROM jobs WHERE batch_id=? ORDER BY created_at", (row["id"],)
                    ).fetchall()
                    return str(row["id"]), [str(job["id"]) for job in existing]
            conn.execute(
                "INSERT INTO batches(id,source,requester,status,subject,message_id,"
                "message_references,request_issues,idempotency_key,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    batch_id,
                    source,
                    requester,
                    "queued",
                    subject,
                    message_id,
                    message_references,
                    json.dumps(list(request_issues or [])),
                    idempotency_key,
                    now,
                    now,
                ),
            )
            for item in items:
                job_id = str(uuid.uuid4())
                job_ids.append(job_id)
                conn.execute(
                    "INSERT INTO jobs(id,batch_id,source,input_url,video_id,requested_format,"
                    "requested_quality,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        job_id,
                        batch_id,
                        source,
                        item["url"],
                        item["video_id"],
                        item["format"],
                        item["quality"],
                        now,
                        now,
                    ),
                )
        return batch_id, job_ids

    def record_mail_message(
        self,
        *,
        mailbox: str,
        uidvalidity: str,
        uid: str,
        message_id: str | None,
        batch_id: str,
    ) -> None:
        with self._lock, self.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO mail_messages(id,mailbox,uidvalidity,uid,message_id,"
                "batch_id,processed_at) VALUES(?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), mailbox, uidvalidity, uid, message_id, batch_id, utcnow()),
            )

    def has_mail_message(self, mailbox: str, uidvalidity: str, uid: str) -> bool:
        with self.connect() as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM mail_messages WHERE mailbox=? AND uidvalidity=? AND uid=?",
                    (mailbox, uidvalidity, uid),
                ).fetchone()
                is not None
            )

    def claim_next_job(self) -> dict[str, Any] | None:
        with self._lock, self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE state='queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                return None
            now = utcnow()
            changed = conn.execute(
                "UPDATE jobs SET state='inspecting',started_at=COALESCE(started_at,?),"
                "updated_at=?,attempt_count=attempt_count+1 WHERE id=? AND state='queued'",
                (now, now, row["id"]),
            ).rowcount
            if not changed:
                return None
            return dict(conn.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone())

    def update_job(self, job_id: str, **values: Any) -> None:
        allowed = {
            "state",
            "progress",
            "title",
            "duration_seconds",
            "actual_format",
            "actual_quality",
            "error_code",
            "error_message",
            "finished_at",
            "expires_at",
        }
        fields = {key: value for key, value in values.items() if key in allowed}
        fields["updated_at"] = utcnow()
        assignments = ",".join(f"{key}=?" for key in fields)
        with self._lock, self.connect() as conn:
            conn.execute(
                f"UPDATE jobs SET {assignments} WHERE id=?",  # noqa: S608 - keys are allowlisted
                (*fields.values(), job_id),
            )
            row = conn.execute("SELECT batch_id FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row:
                self._refresh_batch(conn, str(row["batch_id"]))

    def _refresh_batch(self, conn: sqlite3.Connection, batch_id: str) -> None:
        states = [
            str(row["state"])
            for row in conn.execute("SELECT state FROM jobs WHERE batch_id=?", (batch_id,))
        ]
        terminal = {"ready", "failed", "cancelled", "expired"}
        if states and all(state in terminal for state in states):
            status = "complete" if any(state == "ready" for state in states) else "failed"
        elif any(state not in {"queued"} for state in states):
            status = "processing"
        else:
            status = "queued"
        conn.execute(
            "UPDATE batches SET status=?,updated_at=? WHERE id=?", (status, utcnow(), batch_id)
        )

    def add_artifact(
        self,
        *,
        job_id: str,
        local_path: str | None,
        object_key: str | None,
        filename: str,
        content_type: str,
        size_bytes: int,
        expires_at: str,
    ) -> str:
        artifact_id = str(uuid.uuid4())
        with self._lock, self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO artifacts(id,job_id,local_path,object_key,filename,"
                "content_type,size_bytes,expires_at,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    artifact_id,
                    job_id,
                    local_path,
                    object_key,
                    filename,
                    content_type,
                    size_bytes,
                    expires_at,
                    utcnow(),
                ),
            )
        return artifact_id

    def list_jobs(self, *, limit: int = 100, state: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT j.*,a.id artifact_id,a.filename,a.content_type,a.size_bytes,a.expires_at artifact_expires_at FROM jobs j LEFT JOIN artifacts a ON a.job_id=j.id"
        params: list[Any] = []
        if state:
            query += " WHERE j.state=?"
            params.append(state)
        query += " ORDER BY j.created_at DESC LIMIT ?"
        params.append(min(max(limit, 1), 500))
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(query, params)]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT j.*,a.id artifact_id,a.local_path,a.object_key,a.filename,a.content_type,"
                "a.size_bytes,a.expires_at artifact_expires_at FROM jobs j "
                "LEFT JOIN artifacts a ON a.job_id=j.id WHERE j.id=?",
                (job_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT a.*,j.state,j.title FROM artifacts a JOIN jobs j ON j.id=a.job_id "
                "WHERE a.id=?",
                (artifact_id,),
            ).fetchone()
            return dict(row) if row else None

    def retry_job(self, job_id: str) -> bool:
        with self._lock, self.connect() as conn:
            changed = conn.execute(
                "UPDATE jobs SET state='queued',progress=0,error_code=NULL,error_message=NULL,"
                "finished_at=NULL,updated_at=? WHERE id=? AND state IN ('failed','cancelled')",
                (utcnow(), job_id),
            ).rowcount
            return bool(changed)

    def cancel_job(self, job_id: str) -> bool:
        with self._lock, self.connect() as conn:
            changed = conn.execute(
                "UPDATE jobs SET state='cancelled',finished_at=?,updated_at=? "
                "WHERE id=? AND state IN ('queued','inspecting','downloading','processing','uploading')",
                (utcnow(), utcnow(), job_id),
            ).rowcount
            return bool(changed)

    def delete_job(self, job_id: str) -> dict[str, Any] | None:
        job = self.get_job(job_id)
        if not job or job["state"] not in {"ready", "failed", "cancelled", "expired"}:
            return None
        with self._lock, self.connect() as conn:
            conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        return job

    def expired_artifacts(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [
                dict(row)
                for row in conn.execute("SELECT * FROM artifacts WHERE expires_at<=?", (utcnow(),))
            ]

    def expire_artifact(self, artifact_id: str, job_id: str) -> None:
        with self._lock, self.connect() as conn:
            conn.execute("DELETE FROM artifacts WHERE id=?", (artifact_id,))
            conn.execute(
                "UPDATE jobs SET state='expired',updated_at=? WHERE id=?", (utcnow(), job_id)
            )

    def create_session(self, token: str, csrf_token: str, username: str, hours: int) -> str:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires = (datetime.now(UTC) + timedelta(hours=hours)).isoformat()
        with self._lock, self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE expires_at<=?", (utcnow(),))
            conn.execute(
                "INSERT INTO sessions(token_hash,csrf_token,username,expires_at,created_at) "
                "VALUES(?,?,?,?,?)",
                (token_hash, csrf_token, username, expires, utcnow()),
            )
        return expires

    def get_session(self, token: str) -> dict[str, Any] | None:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE token_hash=? AND expires_at>?",
                (token_hash, utcnow()),
            ).fetchone()
            return dict(row) if row else None

    def delete_session(self, token: str) -> None:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self._lock, self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))

    def get_runtime_settings(self) -> dict[str, Any]:
        with self.connect() as conn:
            rows = conn.execute("SELECT key,value FROM settings").fetchall()
        result: dict[str, Any] = {}
        for row in rows:
            try:
                result[str(row["key"])] = json.loads(str(row["value"]))
            except json.JSONDecodeError:
                result[str(row["key"])] = str(row["value"])
        return result

    def set_runtime_settings(self, values: dict[str, Any]) -> None:
        now = utcnow()
        with self._lock, self.connect() as conn:
            for key, value in values.items():
                conn.execute(
                    "INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                    (key, json.dumps(value), now),
                )
            conn.execute(
                "INSERT INTO audit_events(id,event_type,summary,created_at) VALUES(?,?,?,?)",
                (str(uuid.uuid4()), "settings.updated", ", ".join(sorted(values)), now),
            )

    def ready_email_batches(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM batches WHERE source='email' AND status IN ('complete','failed') "
                    "AND reply_status='pending' ORDER BY created_at"
                )
            ]

    def recent_email_batch_count(self, requester: str, since: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) count FROM batches "
                "WHERE source='email' AND requester=? AND created_at>=?",
                (requester, since),
            ).fetchone()
            return int(row["count"])

    def jobs_for_batch(self, batch_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT j.*,a.local_path,a.object_key,a.filename,a.content_type,a.size_bytes,"
                    "a.expires_at artifact_expires_at FROM jobs j LEFT JOIN artifacts a ON a.job_id=j.id "
                    "WHERE j.batch_id=? ORDER BY j.created_at",
                    (batch_id,),
                )
            ]

    def mark_batch_reply(self, batch_id: str, status: str) -> None:
        with self._lock, self.connect() as conn:
            conn.execute(
                "UPDATE batches SET reply_status=?,updated_at=? WHERE id=?",
                (status, utcnow(), batch_id),
            )

    def backup(self, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.connect() as source, sqlite3.connect(destination) as target:
            source.backup(target)
