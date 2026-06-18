import asyncio
from pathlib import Path
from typing import Any

import pytest

from mailtube.config import Settings
from mailtube.downloader.ytdlp import YtDlpDownloader


@pytest.mark.asyncio
async def test_yt_dlp_uses_argument_array_and_bounded_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    class FakeProcess:
        pid = 100
        returncode = 0

        def __init__(self) -> None:
            self.stdout = asyncio.StreamReader()
            self.stdout.feed_data(b"__MT_PROGRESS__:55.0%\n")
            self.stdout.feed_data(b"__MT_TITLE__:Fixture title\n")
            self.stdout.feed_eof()

        async def wait(self) -> int:
            return 0

    async def fake_exec(*args: str, **kwargs: Any) -> FakeProcess:
        captured["args"] = args
        captured["kwargs"] = kwargs
        template = Path(args[args.index("--output") + 1])
        template.with_name(template.name.replace("%(ext)s", "mp3")).write_bytes(b"fixture")
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    settings = Settings(
        environment="test",
        data_dir=tmp_path / "data",
        work_dir=tmp_path / "work",
    )
    progress: list[float] = []
    result = await YtDlpDownloader(settings).download(
        job_id="a" * 36,
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        output_format="mp3",
        quality="192k",
        progress=lambda value: _record(progress, value),
    )
    assert result.path.read_bytes() == b"fixture"
    assert progress == [55.0]
    assert captured["args"][0] == "yt-dlp"
    assert "--no-playlist" in captured["args"]
    assert captured["kwargs"]["start_new_session"] is True
    assert "shell" not in captured["kwargs"]


async def _record(values: list[float], value: float) -> None:
    values.append(value)


def test_downloader_errors_do_not_echo_upstream_urls_or_credentials() -> None:
    message = YtDlpDownloader._safe_failure(
        ["ERROR https://secret.example/?token=credential failed with HTTP Error 403"]
    )
    assert "secret" not in message
    assert "credential" not in message
