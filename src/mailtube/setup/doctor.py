from __future__ import annotations

import json
import shutil
import sqlite3

from mailtube.config import Settings


def run_doctor(settings: Settings) -> int:
    checks: dict[str, dict[str, object]] = {}
    checks["data_directory"] = {
        "ok": settings.data_dir.exists() and settings.data_dir.is_dir(),
        "path": str(settings.data_dir),
    }
    checks["work_directory"] = {
        "ok": settings.work_dir.exists() and settings.work_dir.is_dir(),
        "path": str(settings.work_dir),
    }
    checks["executables"] = {
        "ok": all(shutil.which(name) for name in ("yt-dlp", "ffmpeg", "ffprobe", "deno")),
        "yt_dlp": bool(shutil.which("yt-dlp")),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
        "deno": bool(shutil.which("deno")),
    }
    database_ok = False
    if settings.db_path.exists():
        try:
            with sqlite3.connect(settings.db_path) as conn:
                database_ok = conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        except sqlite3.Error:
            database_ok = False
    checks["database"] = {"ok": database_ok, "path": str(settings.db_path)}
    checks["configuration"] = {
        "ok": bool(settings.admin_password_hash.get_secret_value())
        and len(settings.session_secret.get_secret_value()) >= 32,
        "email_enabled": settings.email_enabled,
        "storage_backend": settings.storage_backend,
        "sender_policy": settings.sender_policy,
    }
    print(json.dumps({"mailtube_doctor": checks}, indent=2))
    return 0 if all(bool(check["ok"]) for check in checks.values()) else 1
