import sqlite3
from pathlib import Path

from mailtube.db import Database

ITEM = {
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "video_id": "dQw4w9WgXcQ",
    "format": "mp4",
    "quality": "720p",
}


def test_wal_idempotency_and_recovery(tmp_path: Path) -> None:
    db = Database(tmp_path / "mailtube.db")
    db.initialize()
    first_batch, first_jobs = db.create_batch(source="web", items=[ITEM], idempotency_key="web:one")
    second_batch, second_jobs = db.create_batch(
        source="web", items=[ITEM], idempotency_key="web:one"
    )
    assert (first_batch, first_jobs) == (second_batch, second_jobs)
    claimed = db.claim_next_job()
    assert claimed and claimed["state"] == "inspecting"
    db.initialize()
    recovered = db.get_job(first_jobs[0])
    assert recovered and recovered["state"] == "queued"
    with db.connect() as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_sessions_are_stored_hashed(tmp_path: Path) -> None:
    db = Database(tmp_path / "mailtube.db")
    db.initialize()
    db.create_session("plain-token", "csrf", "admin", 1)
    with db.connect() as connection:
        value = connection.execute("SELECT token_hash FROM sessions").fetchone()[0]
    assert value != "plain-token"
    session = db.get_session("plain-token")
    assert session and session["csrf_token"] == "csrf"


def test_migrates_existing_batches_with_request_issues(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE batches (id TEXT PRIMARY KEY, source TEXT, requester TEXT, "
            "status TEXT, subject TEXT, message_id TEXT, message_references TEXT, "
            "reply_status TEXT, idempotency_key TEXT, created_at TEXT, updated_at TEXT)"
        )
    Database(path).initialize()
    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(batches)")}
    assert "request_issues" in columns
