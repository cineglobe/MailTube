from __future__ import annotations

import asyncio
import mimetypes
import os
import re
import signal
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from mailtube.config import Settings

ProgressCallback = Callable[[float], Awaitable[None]]
PERCENT_RE = re.compile(r"__MT_PROGRESS__:(\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    filename: str
    content_type: str
    title: str
    actual_format: str
    actual_quality: str


class DownloadError(RuntimeError):
    pass


class YtDlpDownloader:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    def _format_args(self, output_format: str, quality: str) -> list[str]:
        if output_format == "mp4":
            height = None if quality == "best" else int(quality.rstrip("p"))
            limit = "" if height is None else f"[height<={height}]"
            selector = f"bv*{limit}[ext=mp4]+ba[ext=m4a]/b{limit}[ext=mp4]/bv*{limit}+ba/b{limit}"
            return ["--format", selector, "--merge-output-format", "mp4"]
        if output_format == "mp3":
            return ["--extract-audio", "--audio-format", "mp3", "--audio-quality", quality]
        sample_rate = "48000" if quality == "48khz" else "44100"
        return [
            "--extract-audio",
            "--audio-format",
            "wav",
            "--postprocessor-args",
            f"ffmpeg:-threads 1 -ar {sample_rate} -acodec pcm_s16le",
        ]

    async def download(
        self,
        *,
        job_id: str,
        url: str,
        output_format: str,
        quality: str,
        progress: ProgressCallback,
    ) -> DownloadResult:
        job_dir = self.settings.work_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        output = job_dir / f"{job_id}.%(ext)s"
        args = [
            "yt-dlp",
            "--no-playlist",
            "--newline",
            "--no-warnings",
            "--js-runtimes",
            "deno",
            "--restrict-filenames",
            "--match-filter",
            f"duration <= {self.settings.max_duration_seconds}",
            "--max-filesize",
            str(self.settings.max_file_bytes),
            "--progress-template",
            "download:__MT_PROGRESS__:%(progress._percent_str)s",
            "--output",
            str(output),
            "--print",
            "after_move:__MT_TITLE__:%(title)s",
            *self._format_args(output_format, quality),
        ]
        if self.settings.cookies_file:
            args.extend(["--cookies", str(self.settings.cookies_file)])
        if self.settings.pot_provider_url:
            args.extend(
                [
                    "--extractor-args",
                    f"youtubepot-bgutilhttp:base_url={self.settings.pot_provider_url}",
                ]
            )
        args.append(url)
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        self._processes[job_id] = process
        title = ""
        recent: list[str] = []
        try:
            assert process.stdout is not None
            async with asyncio.timeout(self.settings.job_timeout_seconds):
                while True:
                    raw = await asyncio.wait_for(
                        process.stdout.readline(),
                        timeout=self.settings.inactivity_timeout_seconds,
                    )
                    if not raw:
                        break
                    line = raw.decode(errors="replace").strip()
                    match = PERCENT_RE.search(line.replace("%", ""))
                    if match:
                        await progress(min(float(match.group(1)), 100.0))
                    elif line.startswith("__MT_TITLE__:"):
                        title = line.removeprefix("__MT_TITLE__:")[:500]
                    elif line:
                        recent.append(line[-300:])
                        recent = recent[-5:]
                return_code = await process.wait()
            if return_code != 0:
                raise DownloadError(self._safe_failure(recent))
            files = [
                path
                for path in job_dir.iterdir()
                if path.is_file() and path.suffix not in {".part", ".ytdl", ".json"}
            ]
            if not files:
                raise DownloadError("yt-dlp completed without producing a file")
            path = max(files, key=lambda candidate: candidate.stat().st_mtime)
            size = path.stat().st_size
            if size > self.settings.max_file_bytes:
                path.unlink(missing_ok=True)
                raise DownloadError("The converted file exceeds the configured size limit")
            extension = path.suffix.lower().lstrip(".")
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            filename = f"{job_id[:8]}.{extension}"
            final_path = path.with_name(filename)
            if final_path != path:
                path.rename(final_path)
            return DownloadResult(
                path=final_path,
                filename=filename,
                content_type=content_type,
                title=title or "YouTube conversion",
                actual_format=extension,
                actual_quality=quality,
            )
        except TimeoutError as exc:
            await self.cancel(job_id)
            raise DownloadError("The conversion timed out") from exc
        except asyncio.CancelledError:
            await self.cancel(job_id)
            raise
        finally:
            self._processes.pop(job_id, None)

    async def cancel(self, job_id: str) -> None:
        process = self._processes.get(job_id)
        if not process or process.returncode is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
            await asyncio.wait_for(process.wait(), timeout=5)
        except (ProcessLookupError, TimeoutError):
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    @staticmethod
    def _safe_failure(lines: list[str]) -> str:
        detail = " ".join(lines).lower()
        if "sign in to confirm" in detail or "not a bot" in detail:
            return "YouTube requested additional verification; review the compatibility guide"
        if "429" in detail or "too many requests" in detail:
            return "YouTube rate-limited this network address"
        if "max-filesize" in detail or "larger than max" in detail:
            return "The source exceeds the configured file-size limit"
        if "duration" in detail and "filter" in detail:
            return "The source exceeds the configured duration limit"
        if "private video" in detail or "video unavailable" in detail:
            return "The requested video is unavailable or private"
        return "yt-dlp could not download this video"

    def available(self) -> dict[str, bool | str]:
        import shutil

        missing = [
            name for name in ("yt-dlp", "ffmpeg", "ffprobe", "deno") if not shutil.which(name)
        ]
        if missing:
            return {"ok": False, "detail": f"Missing executables: {', '.join(missing)}"}
        return {"ok": True, "detail": "yt-dlp, ffmpeg, and Deno are available"}
