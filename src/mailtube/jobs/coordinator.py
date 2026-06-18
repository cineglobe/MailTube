from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mailtube.config import Settings
from mailtube.db import Database, utcnow
from mailtube.downloader import YtDlpDownloader
from mailtube.storage import Storage

logger = logging.getLogger(__name__)


class JobCoordinator:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        downloader: YtDlpDownloader,
        storage: Storage,
    ) -> None:
        self.settings = settings
        self.db = db
        self.downloader = downloader
        self.storage = storage
        self._stopped = asyncio.Event()
        self._workers: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        self._workers = [
            asyncio.create_task(self._worker(index), name=f"mailtube-worker-{index}")
            for index in range(self.settings.max_concurrent_jobs)
        ]
        self._workers.append(asyncio.create_task(self._cleanup_loop(), name="mailtube-cleanup"))

    async def stop(self) -> None:
        self._stopped.set()
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)

    async def cancel(self, job_id: str) -> bool:
        changed = self.db.cancel_job(job_id)
        await self.downloader.cancel(job_id)
        return changed

    async def _worker(self, index: int) -> None:
        while not self._stopped.is_set():
            job = await asyncio.to_thread(self.db.claim_next_job)
            if not job:
                try:
                    await asyncio.wait_for(self._stopped.wait(), timeout=0.75)
                except TimeoutError:
                    pass
                continue
            job_id = str(job["id"])
            try:
                await self._process(job)
            except asyncio.CancelledError:
                await self.downloader.cancel(job_id)
                raise
            except Exception as exc:
                logger.warning("Job %s failed: %s", job_id, type(exc).__name__)
                self.db.update_job(
                    job_id,
                    state="failed",
                    error_code=type(exc).__name__.lower(),
                    error_message=self._safe_error(exc),
                    finished_at=utcnow(),
                )

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        message = str(exc).strip().splitlines()[-1] if str(exc).strip() else type(exc).__name__
        return message[:400]

    async def _process(self, job: dict[str, object]) -> None:
        job_id = str(job["id"])
        self.db.update_job(job_id, state="downloading", progress=0)

        async def progress(value: float) -> None:
            current = self.db.get_job(job_id)
            if current and current["state"] == "cancelled":
                raise asyncio.CancelledError
            self.db.update_job(job_id, progress=value)

        result = await self.downloader.download(
            job_id=job_id,
            url=str(job["input_url"]),
            output_format=str(job["requested_format"]),
            quality=str(job["requested_quality"]),
            progress=progress,
        )
        current = self.db.get_job(job_id)
        if not current or current["state"] == "cancelled":
            result.path.unlink(missing_ok=True)
            return
        self.db.update_job(job_id, state="processing", progress=100)
        object_key: str | None = None
        if (
            job["source"] == "email"
            and self.settings.storage_backend == "s3"
            and self.settings.delivery_mode in {"links", "hybrid"}
        ):
            self.db.update_job(job_id, state="uploading")
            object_key = await asyncio.to_thread(
                self.storage.upload,
                result.path,
                job_id=job_id,
                filename=result.filename,
                content_type=result.content_type,
            )
        expires = datetime.now(UTC) + timedelta(hours=self.settings.retention_hours)
        self.db.add_artifact(
            job_id=job_id,
            local_path=str(result.path),
            object_key=object_key,
            filename=result.filename,
            content_type=result.content_type,
            size_bytes=result.path.stat().st_size,
            expires_at=expires.isoformat(),
        )
        self.db.update_job(
            job_id,
            state="ready",
            progress=100,
            title=result.title,
            actual_format=result.actual_format,
            actual_quality=result.actual_quality,
            expires_at=expires.isoformat(),
            finished_at=utcnow(),
        )

    async def _cleanup_loop(self) -> None:
        while not self._stopped.is_set():
            for artifact in await asyncio.to_thread(self.db.expired_artifacts):
                local = artifact.get("local_path")
                if local:
                    Path(str(local)).unlink(missing_ok=True)
                    parent = Path(str(local)).parent
                    try:
                        parent.rmdir()
                    except OSError:
                        pass
                await asyncio.to_thread(self.storage.delete, artifact.get("object_key"))
                self.db.expire_artifact(str(artifact["id"]), str(artifact["job_id"]))
            try:
                await asyncio.wait_for(
                    self._stopped.wait(), timeout=self.settings.cleanup_interval_seconds
                )
            except TimeoutError:
                pass
