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

FROM denoland/deno:alpine-2.8.3 AS deno
FROM golang:1.26.4-alpine3.23 AS cosign-builder
RUN CGO_ENABLED=0 GOBIN=/out \
    go install github.com/sigstore/cosign/v3/cmd/cosign@v3.0.6

FROM python:3.12-alpine AS runtime
ARG VERSION=1.0.6
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

RUN apk add --no-cache ca-certificates ffmpeg tini
COPY --from=deno /bin/deno /usr/local/bin/deno
COPY --from=cosign-builder /out/cosign /usr/local/bin/cosign
COPY --from=deno /usr/local/lib/glibc/ /usr/local/lib/glibc/
COPY --from=deno /lib/ld-linux-* /lib/
RUN mkdir -p /lib64 \
    && ln -sf /usr/local/lib/glibc/ld-linux-* /lib64/ \
    && deno --version

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

RUN addgroup -g 10001 -S mailtube \
    && adduser -u 10001 -S -D -H -G mailtube mailtube \
    && install -d -o 10001 -g 10001 /data /work /tmp/deno
USER 10001:10001
EXPOSE 8080
VOLUME ["/data", "/work"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health', timeout=3)"]
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["mailtube", "serve"]
