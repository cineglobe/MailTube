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

from mailtube import __version__
from mailtube.api.schemas import CreateJobsRequest, LoginRequest, RuntimeSettingsUpdate
from mailtube.config import Settings
from mailtube.db import Database
from mailtube.downloader import YtDlpDownloader
from mailtube.email.service import EmailService
from mailtube.jobs import JobCoordinator
from mailtube.security.auth import AuthService
from mailtube.storage import LocalStorage, S3Storage, Storage

logger = logging.getLogger(__name__)


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
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db = Database(settings.db_path)
        self.storage: Storage = (
            S3Storage(settings) if settings.storage_backend == "s3" else LocalStorage()
        )
        self.downloader = YtDlpDownloader(settings)
        self.auth = AuthService(self.db, settings)
        self.coordinator = JobCoordinator(settings, self.db, self.downloader, self.storage)
        self.email: EmailService | None = None
        self.email_task: asyncio.Task[None] | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime = settings or Settings()
    state_holder: dict[str, AppState] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime.prepare_directories()
        runtime.validate_runtime_secrets()
        app_state = AppState(runtime)
        state_holder["state"] = app_state
        app.state.mailtube = app_state
        app_state.db.initialize()
        await app_state.coordinator.start()
        if runtime.email_enabled:
            app_state.email = EmailService(runtime, app_state.db, app_state.storage)
            app_state.email_task = asyncio.create_task(
                app_state.email.run(), name="mailtube-email-service"
            )
        yield
        if app_state.email:
            await app_state.email.stop()
        if app_state.email_task:
            app_state.email_task.cancel()
            await asyncio.gather(app_state.email_task, return_exceptions=True)
        await app_state.coordinator.stop()

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
            "email": {
                "ok": not app_state.settings.email_enabled or app_state.email_task is not None,
                "detail": "enabled" if app_state.settings.email_enabled else "disabled",
            },
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
        overrides = app_state.db.get_runtime_settings()
        return {
            "sender_policy": overrides.get("sender_policy", app_state.settings.sender_policy),
            "sender_allowlist": overrides.get(
                "sender_allowlist", app_state.settings.sender_allowlist
            ),
            "retention_hours": overrides.get("retention_hours", app_state.settings.retention_hours),
            "max_urls_per_batch": overrides.get(
                "max_urls_per_batch", app_state.settings.max_urls_per_batch
            ),
            "max_concurrent_jobs": overrides.get(
                "max_concurrent_jobs", app_state.settings.max_concurrent_jobs
            ),
            "email_enabled": app_state.settings.email_enabled,
            "delivery_mode": app_state.settings.delivery_mode,
            "storage_backend": app_state.settings.storage_backend,
            "update_channel": app_state.settings.update_channel,
        }

    @app.patch("/api/v1/settings")
    def update_settings(
        payload: RuntimeSettingsUpdate,
        _: dict[str, Any] = Depends(require_csrf),
        app_state: AppState = Depends(get_state),
    ) -> dict[str, Any]:
        values = payload.model_dump(exclude_none=True)
        if not values:
            raise HTTPException(status_code=422, detail="No settings supplied")
        app_state.db.set_runtime_settings(values)
        return {"ok": True, "updated": sorted(values)}

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
