from __future__ import annotations

import asyncio
import json
import logging
import secrets
import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any, cast

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import SecretStr, ValidationError

from mailtube import __version__
from mailtube.api.schemas import CreateJobsRequest, LoginRequest, RuntimeSettingsUpdate
from mailtube.config import Settings
from mailtube.db import Database
from mailtube.downloader import YtDlpDownloader
from mailtube.email.service import EmailService
from mailtube.jobs import JobCoordinator
from mailtube.security.auth import AuthService
from mailtube.security.runtime_secrets import (
    RuntimeSecretError,
    open_runtime_secret,
    seal_runtime_secret,
)
from mailtube.storage import LocalStorage, S3Storage, Storage

logger = logging.getLogger(__name__)

EDITABLE_SETTING_FIELDS = {
    "admin_username",
    "admin_password_hash",
    "max_urls_per_batch",
    "max_concurrent_jobs",
    "max_duration_seconds",
    "max_file_mb",
    "job_timeout_seconds",
    "inactivity_timeout_seconds",
    "retention_hours",
    "default_format",
    "default_mp4_quality",
    "default_mp3_quality",
    "default_wav_quality",
    "email_enabled",
    "poll_interval_seconds",
    "imap_host",
    "imap_port",
    "imap_folder",
    "imap_username",
    "smtp_host",
    "smtp_port",
    "smtp_security",
    "smtp_username",
    "smtp_from",
    "smtp_from_name",
    "sender_policy",
    "sender_allowlist",
    "delivery_mode",
    "max_attachment_mb",
    "max_email_requests_per_hour",
    "storage_backend",
    "s3_endpoint",
    "s3_region",
    "s3_bucket",
    "s3_access_key_id",
    "s3_force_path_style",
    "pot_provider_url",
    "update_channel",
}
RUNTIME_SECRET_FIELDS = {"imap_password", "smtp_password", "s3_secret_access_key"}
STORAGE_SETTING_FIELDS = {
    "storage_backend",
    "s3_endpoint",
    "s3_region",
    "s3_bucket",
    "s3_access_key_id",
    "s3_secret_access_key",
    "s3_force_path_style",
}


class SecurityHeadersMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                        (
                            b"content-security-policy",
                            b"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                            b"script-src 'self' 'unsafe-inline'; connect-src 'self'; "
                            b"frame-ancestors 'none'; base-uri 'self'; "
                            b"form-action 'self'",
                        ),
                    ]
                )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class AppState:
    def __init__(self, settings: Settings, db: Database) -> None:
        self.db = db
        self.settings = self._load_persisted_settings(settings)
        self.storage: Storage = (
            S3Storage(self.settings) if self.settings.storage_backend == "s3" else LocalStorage()
        )
        self.downloader = YtDlpDownloader(self.settings)
        self.auth = AuthService(self.db, self.settings)
        self.coordinator = JobCoordinator(self.settings, self.db, self.downloader, self.storage)
        self.email: EmailService | None = None
        self.email_task: asyncio.Task[None] | None = None

    def _load_persisted_settings(self, base: Settings) -> Settings:
        stored = self.db.get_runtime_settings()
        values = {key: value for key, value in stored.items() if key in EDITABLE_SETTING_FIELDS}
        session_secret = base.session_secret.get_secret_value()
        for field in RUNTIME_SECRET_FIELDS:
            encrypted = stored.get(f"_secret_{field}")
            if not encrypted:
                continue
            try:
                values[field] = SecretStr(
                    open_runtime_secret(str(encrypted), session_secret, base.instance_id)
                )
            except RuntimeSecretError:
                logger.warning("Ignoring an unreadable encrypted %s override", field)
        return Settings.model_validate({**base.model_dump(), **values})

    async def start(self) -> None:
        await self.coordinator.start()
        if self.settings.email_enabled:
            self._start_email()

    async def stop(self) -> None:
        await self._stop_email()
        await self.coordinator.stop()

    def _start_email(self) -> None:
        self.email = EmailService(self.settings, self.db, self.storage)
        self.email_task = asyncio.create_task(self.email.run(), name="mailtube-email-service")

    async def _stop_email(self) -> None:
        if self.email:
            await self.email.stop()
        if self.email_task:
            self.email_task.cancel()
            await asyncio.gather(self.email_task, return_exceptions=True)
        self.email = None
        self.email_task = None

    async def apply_runtime_settings(self, values: dict[str, Any]) -> list[str]:
        admin_password = values.pop("admin_password", None)
        if admin_password:
            values["admin_password_hash"] = AuthService.hash_password(str(admin_password))
        unknown = set(values) - EDITABLE_SETTING_FIELDS - RUNTIME_SECRET_FIELDS
        if unknown:
            raise ValueError(f"Unsupported settings: {', '.join(sorted(unknown))}")

        secret_updates: dict[str, str] = {}
        for key in RUNTIME_SECRET_FIELDS:
            value = values.pop(key, None)
            if value is not None:
                secret_updates[key] = str(value)
        proposed_values = {**self.settings.model_dump(), **values}
        proposed_values.update({key: SecretStr(value) for key, value in secret_updates.items()})
        proposed = Settings.model_validate(proposed_values)
        proposed.validate_runtime_secrets()

        storage_changed = bool((set(values) | set(secret_updates)) & STORAGE_SETTING_FIELDS)
        proposed_storage = self.storage
        if storage_changed:
            proposed_storage = (
                S3Storage(proposed) if proposed.storage_backend == "s3" else LocalStorage()
            )

        persisted = dict(values)
        session_secret = self.settings.session_secret.get_secret_value()
        for key, value in secret_updates.items():
            persisted[f"_secret_{key}"] = seal_runtime_secret(
                value, session_secret, self.settings.instance_id
            )
        self.db.set_runtime_settings(persisted)

        email_was_enabled = self.settings.email_enabled
        self.settings = proposed
        self.auth.settings = proposed
        self.downloader.settings = proposed
        self.coordinator.settings = proposed
        self.coordinator.resize()
        if storage_changed:
            self.storage = proposed_storage
            self.coordinator.storage = proposed_storage

        if email_was_enabled and not proposed.email_enabled:
            await self._stop_email()
        elif not email_was_enabled and proposed.email_enabled:
            self._start_email()
        elif self.email:
            self.email.settings = proposed
            self.email.storage = self.storage
        return sorted(set(values) | set(secret_updates))


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime.prepare_directories()
        runtime.validate_runtime_secrets()
        db = Database(runtime.db_path)
        db.initialize()
        app_state = AppState(runtime, db)
        app.state.mailtube = app_state
        await app_state.start()
        yield
        await app_state.stop()

    app = FastAPI(
        title="MailTube API",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=runtime.allowed_hosts)

    def get_state(request: Request) -> AppState:
        return cast(AppState, request.app.state.mailtube)

    def require_session(
        request: Request, app_state: AppState = Depends(get_state)
    ) -> dict[str, Any]:
        session = app_state.auth.session(request.cookies.get(app_state.auth.cookie_name))
        if not session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
            )
        return session

    def require_csrf(
        request: Request,
        session: dict[str, Any] = Depends(require_session),
        csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    ) -> dict[str, Any]:
        if not csrf_token or not secrets.compare_digest(csrf_token, str(session["csrf_token"])):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")
        return session

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__}

    @app.get("/api/v1/health/details")
    def health_details(
        _: dict[str, Any] = Depends(require_session),
        app_state: AppState = Depends(get_state),
    ) -> dict[str, Any]:
        disk = shutil.disk_usage(app_state.settings.work_dir)
        downloader = app_state.downloader.available()
        try:
            ejs_version = metadata.version("yt-dlp-ejs")
        except metadata.PackageNotFoundError:
            ejs_version = "missing"
        javascript_ok = bool(shutil.which("deno")) and ejs_version != "missing"
        if not app_state.settings.email_enabled:
            email_status: dict[str, Any] = {"ok": True, "detail": "disabled"}
        elif app_state.email_task and app_state.email_task.done():
            email_status = {"ok": False, "detail": "Email worker stopped unexpectedly"}
        elif app_state.email:
            email_status = app_state.email.status()
        else:
            email_status = {"ok": False, "detail": "Email worker is not running"}
        return {
            "ok": bool(downloader["ok"]) and javascript_ok,
            "version": __version__,
            "database": {"ok": app_state.settings.db_path.exists(), "detail": "SQLite WAL"},
            "downloader": downloader,
            "javascript": {
                "ok": javascript_ok,
                "detail": f"Deno and yt-dlp-ejs {ejs_version}",
            },
            "storage": {
                "ok": True,
                "detail": app_state.settings.storage_backend,
            },
            "email": email_status,
            "disk": {
                "ok": disk.free > app_state.settings.max_file_bytes,
                "free_bytes": disk.free,
                "total_bytes": disk.total,
            },
        }

    @app.post("/api/v1/auth/login")
    def login(
        payload: LoginRequest,
        request: Request,
        response: Response,
        app_state: AppState = Depends(get_state),
    ) -> dict[str, Any]:
        client = request.client.host if request.client else "unknown"
        try:
            token, csrf, expires = app_state.auth.authenticate(
                payload.username, payload.password, client
            )
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        response.set_cookie(
            app_state.auth.cookie_name,
            token,
            httponly=True,
            secure=app_state.settings.secure_cookies,
            samesite="strict",
            path="/",
            max_age=app_state.settings.session_hours * 3600,
        )
        return {"username": payload.username, "csrf_token": csrf, "expires_at": expires}

    @app.post("/api/v1/auth/logout", status_code=204)
    def logout(
        request: Request,
        response: Response,
        _: dict[str, Any] = Depends(require_csrf),
        app_state: AppState = Depends(get_state),
    ) -> Response:
        token = request.cookies.get(app_state.auth.cookie_name)
        if token:
            app_state.db.delete_session(token)
        response.delete_cookie(app_state.auth.cookie_name, path="/")
        return response

    @app.get("/api/v1/auth/session")
    def session(session_data: dict[str, Any] = Depends(require_session)) -> dict[str, Any]:
        return {
            "username": session_data["username"],
            "csrf_token": session_data["csrf_token"],
            "expires_at": session_data["expires_at"],
        }

    @app.post("/api/v1/jobs", status_code=202)
    def create_jobs(
        payload: CreateJobsRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        session_data: dict[str, Any] = Depends(require_csrf),
        app_state: AppState = Depends(get_state),
    ) -> dict[str, Any]:
        runtime_settings = app_state.db.get_runtime_settings()
        limit = int(
            runtime_settings.get("max_urls_per_batch", app_state.settings.max_urls_per_batch)
        )
        if len(payload.items) > limit:
            raise HTTPException(
                status_code=422, detail=f"A batch may contain at most {limit} links"
            )
        required_free = app_state.settings.max_file_bytes * app_state.settings.max_concurrent_jobs
        if shutil.disk_usage(app_state.settings.work_dir).free < required_free:
            raise HTTPException(
                status_code=507,
                detail="The work volume does not have enough free space for another job",
            )
        try:
            items = [item.validated_dict() for item in payload.items]
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        batch_id, job_ids = app_state.db.create_batch(
            source="web",
            items=items,
            requester=str(session_data["username"]),
            idempotency_key=f"web:{idempotency_key}" if idempotency_key else None,
        )
        return {"batch_id": batch_id, "job_ids": job_ids}

    @app.get("/api/v1/jobs")
    def list_jobs(
        limit: int = 100,
        state_filter: str | None = None,
        _: dict[str, Any] = Depends(require_session),
        app_state: AppState = Depends(get_state),
    ) -> dict[str, Any]:
        return {"items": app_state.db.list_jobs(limit=limit, state=state_filter)}

    @app.get("/api/v1/jobs/events")
    async def job_events(
        request: Request,
        _: dict[str, Any] = Depends(require_session),
        app_state: AppState = Depends(get_state),
    ) -> StreamingResponse:
        async def stream() -> AsyncIterator[str]:
            last = ""
            while not await request.is_disconnected():
                payload = json.dumps(app_state.db.list_jobs(limit=100), default=str)
                if payload != last:
                    yield f"event: jobs\ndata: {payload}\n\n"
                    last = payload
                else:
                    yield ": keepalive\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/v1/jobs/{job_id}")
    def get_job(
        job_id: str,
        _: dict[str, Any] = Depends(require_session),
        app_state: AppState = Depends(get_state),
    ) -> dict[str, Any]:
        job = app_state.db.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    @app.post("/api/v1/jobs/{job_id}/cancel")
    async def cancel_job(
        job_id: str,
        _: dict[str, Any] = Depends(require_csrf),
        app_state: AppState = Depends(get_state),
    ) -> dict[str, bool]:
        return {"ok": await app_state.coordinator.cancel(job_id)}

    @app.post("/api/v1/jobs/{job_id}/retry")
    def retry_job(
        job_id: str,
        _: dict[str, Any] = Depends(require_csrf),
        app_state: AppState = Depends(get_state),
    ) -> dict[str, bool]:
        return {"ok": app_state.db.retry_job(job_id)}

    @app.delete("/api/v1/jobs/{job_id}")
    async def delete_job(
        job_id: str,
        _: dict[str, Any] = Depends(require_csrf),
        app_state: AppState = Depends(get_state),
    ) -> dict[str, bool]:
        job = app_state.db.delete_job(job_id)
        if not job:
            raise HTTPException(status_code=409, detail="Only terminal jobs can be deleted")
        if job.get("local_path"):
            Path(str(job["local_path"])).unlink(missing_ok=True)
        await asyncio.to_thread(app_state.storage.delete, job.get("object_key"))
        return {"ok": True}

    @app.get("/api/v1/artifacts/{artifact_id}/download")
    def download_artifact(
        artifact_id: str,
        _: dict[str, Any] = Depends(require_session),
        app_state: AppState = Depends(get_state),
    ) -> FileResponse:
        artifact = app_state.db.get_artifact(artifact_id)
        if not artifact or not artifact.get("local_path"):
            raise HTTPException(status_code=404, detail="Artifact not found")
        if datetime.fromisoformat(str(artifact["expires_at"])) <= datetime.now(UTC):
            raise HTTPException(status_code=410, detail="Artifact has expired")
        path = Path(str(artifact["local_path"]))
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Artifact file is missing")
        return FileResponse(
            path,
            filename=str(artifact["filename"]),
            media_type=str(artifact["content_type"]),
        )

    @app.get("/api/v1/settings")
    def get_settings(
        _: dict[str, Any] = Depends(require_session),
        app_state: AppState = Depends(get_state),
    ) -> dict[str, Any]:
        current = app_state.settings
        result = {
            key: getattr(current, key)
            for key in EDITABLE_SETTING_FIELDS
            if key != "admin_password_hash"
        }
        result.update(
            {
                "public_url": current.public_url,
                "allowed_hosts": current.allowed_hosts,
                "secure_cookies": current.secure_cookies,
                "internal_port": current.port,
                "cookies_configured": current.cookies_file is not None,
                "has_imap_password": bool(current.imap_password.get_secret_value()),
                "has_smtp_password": bool(current.smtp_password.get_secret_value()),
                "has_s3_secret_access_key": bool(current.s3_secret_access_key.get_secret_value()),
            }
        )
        return result

    @app.patch("/api/v1/settings")
    async def update_settings(
        payload: RuntimeSettingsUpdate,
        _: dict[str, Any] = Depends(require_csrf),
        app_state: AppState = Depends(get_state),
    ) -> dict[str, Any]:
        values = payload.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=422, detail="No settings supplied")
        try:
            updated = await app_state.apply_runtime_settings(values)
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"ok": True, "updated": updated}

    @app.post("/api/v1/diagnostics/email")
    async def test_email(
        _: dict[str, Any] = Depends(require_csrf),
        app_state: AppState = Depends(get_state),
    ) -> dict[str, bool | str]:
        if not app_state.email:
            return {"ok": False, "detail": "Email integration is disabled"}
        return await asyncio.to_thread(app_state.email.test_connections)

    @app.post("/api/v1/diagnostics/storage")
    async def test_storage(
        _: dict[str, Any] = Depends(require_csrf),
        app_state: AppState = Depends(get_state),
    ) -> dict[str, bool | str]:
        return await asyncio.to_thread(app_state.storage.test)

    @app.post("/api/v1/diagnostics/downloader")
    def test_downloader(
        _: dict[str, Any] = Depends(require_csrf),
        app_state: AppState = Depends(get_state),
    ) -> dict[str, bool | str]:
        return app_state.downloader.available()

    static_root = runtime.static_dir
    next_static = static_root / "_next"
    if next_static.is_dir():
        app.mount("/_next", StaticFiles(directory=next_static), name="next-static")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> Response:
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        safe = Path(path)
        if ".." in safe.parts:
            return JSONResponse({"detail": "Not found"}, status_code=404)
        candidates = [
            static_root / safe / "index.html",
            static_root / f"{path}.html",
            static_root / safe,
        ]
        for candidate in candidates:
            if candidate.is_file() and candidate.resolve().is_relative_to(static_root.resolve()):
                return FileResponse(candidate)
        return JSONResponse({"detail": "Dashboard build is not installed"}, status_code=404)

    return app
