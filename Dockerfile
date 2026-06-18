# syntax=docker/dockerfile:1.7
FROM node:22-bookworm-slim AS web-builder
ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH
WORKDIR /build/apps/web
RUN corepack enable
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/pnpm-workspace.yaml ./
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile
COPY apps/web/ ./
RUN pnpm build

FROM denoland/deno:bin-2.8.1 AS deno

FROM python:3.12-slim-bookworm AS runtime
ARG VERSION=1.0.1
ARG SOURCE_URL="https://github.com/cineglobe/MailTube"
LABEL org.opencontainers.image.title="MailTube" \
      org.opencontainers.image.description="Private web and email media conversion appliance" \
      org.opencontainers.image.source=$SOURCE_URL \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.version=$VERSION

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MAILTUBE_STATIC_DIR=/app/static \
    MAILTUBE_DATA_DIR=/data \
    MAILTUBE_WORK_DIR=/work \
    DENO_DIR=/tmp/deno

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates ffmpeg tini \
    && rm -rf /var/lib/apt/lists/*
COPY --from=deno /deno /usr/local/bin/deno

WORKDIR /app
COPY pyproject.toml constraints.txt README.md ./
COPY src/ ./src/
COPY scripts/update.sh /usr/local/share/mailtube/update.sh
COPY scripts/install-updater.sh /usr/local/share/mailtube/install-updater.sh
COPY scripts/update.ps1 /usr/local/share/mailtube/update.ps1
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --no-compile --constraint constraints.txt . \
    && python -m pip check
COPY --from=web-builder /build/apps/web/out ./static

RUN groupadd --gid 10001 mailtube \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin mailtube \
    && install -d -o 10001 -g 10001 /data /work /tmp/deno
USER 10001:10001
EXPOSE 8080
VOLUME ["/data", "/work"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health', timeout=3)"]
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["mailtube", "serve"]
