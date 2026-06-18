# Development

Install Python 3.12+, Node 22+, pnpm, ffmpeg, ffprobe, and Deno.

```bash
python3.12 -m venv .venv
.venv/bin/pip install --constraint constraints.txt -e '.[dev]'
pnpm --dir apps/web install --frozen-lockfile
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/pytest
pnpm --dir apps/web lint
pnpm --dir apps/web typecheck
pnpm --dir apps/web test
pnpm --dir apps/web build
```

Use fake yt-dlp/IMAP/SMTP fixtures in routine tests. Live YouTube checks must be opt-in and use an operator-owned video. Build images with Buildx for `linux/amd64,linux/arm64` before release.
