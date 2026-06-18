#!/bin/sh
set -eu

IMAGE="${MAILTUBE_IMAGE:-ghcr.io/OWNER/MailTube:latest}"
CONFIG_DIR="${MAILTUBE_CONFIG_DIR:-$HOME/.config/mailtube}"

fail() { printf 'MailTube: %s\n' "$1" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || fail "Docker is required: https://docs.docker.com/engine/install/"
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required"
test -t 0 && test -t 1 || fail "Run the installer in an interactive terminal"

arch=$(uname -m)
case "$arch" in
  x86_64|amd64|aarch64|arm64) ;;
  armv7l|armv6l) fail "32-bit Raspberry Pi systems are unsupported. Install Raspberry Pi OS Lite 64-bit." ;;
  *) fail "Unsupported architecture: $arch" ;;
esac

mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"
printf 'Pulling %s…\n' "$IMAGE"
docker pull "$IMAGE"
digest=$(docker image inspect "$IMAGE" --format '{{index .RepoDigests 0}}')
test -n "$digest" || fail "Could not resolve an immutable image digest"

docker run --rm -it \
  --user "$(id -u):$(id -g)" \
  -e MAILTUBE_CONFIG_DIR=/config \
  -e MAILTUBE_IMAGE="$digest" \
  -v "$CONFIG_DIR:/config" \
  "$digest" mailtube setup

docker compose --env-file "$CONFIG_DIR/.env" -f "$CONFIG_DIR/compose.yml" config >/dev/null
docker compose --env-file "$CONFIG_DIR/.env" -f "$CONFIG_DIR/compose.yml" up -d

attempt=0
until docker compose --env-file "$CONFIG_DIR/.env" -f "$CONFIG_DIR/compose.yml" exec -T mailtube \
  python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health', timeout=3)" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  test "$attempt" -lt 30 || fail "MailTube did not become healthy. Run: docker compose -f $CONFIG_DIR/compose.yml logs"
  sleep 2
done

mode=$(sed -n 's/^MAILTUBE_DEPLOYMENT_MODE=//p' "$CONFIG_DIR/.env" | tr -d '"')
host_port=$(sed -n 's/^MAILTUBE_HTTP_PORT=//p' "$CONFIG_DIR/.env" | tr -d '"')
if [ "$mode" = "tailscale" ] && command -v tailscale >/dev/null 2>&1; then
  printf 'Publish MailTube privately with Tailscale Serve now? [y/N] '
  read -r answer
  case "$answer" in
    y|Y|yes|YES) tailscale serve --bg "http://127.0.0.1:${host_port:-8080}" ;;
  esac
fi

if [ -n "${MAILTUBE_MANIFEST_URL:-}" ] && [ -n "${MAILTUBE_COSIGN_IDENTITY:-}" ]; then
  updater_container=$(docker create "$digest")
  docker cp "$updater_container:/usr/local/share/mailtube/update.sh" "$CONFIG_DIR/update.sh"
  docker cp "$updater_container:/usr/local/share/mailtube/install-updater.sh" "$CONFIG_DIR/install-updater.sh"
  docker rm "$updater_container" >/dev/null
  chmod 700 "$CONFIG_DIR/update.sh" "$CONFIG_DIR/install-updater.sh"
  MAILTUBE_CONFIG_DIR="$CONFIG_DIR" \
  MAILTUBE_MANIFEST_URL="$MAILTUBE_MANIFEST_URL" \
  MAILTUBE_COSIGN_IDENTITY="$MAILTUBE_COSIGN_IDENTITY" \
    "$CONFIG_DIR/install-updater.sh"
else
  printf 'Automatic updates were not scheduled. Set MAILTUBE_MANIFEST_URL and MAILTUBE_COSIGN_IDENTITY, then run scripts/install-updater.sh.\n'
fi

printf '\nMailTube is ready.\nDashboard: http://127.0.0.1:8080\nConfiguration: %s\n' "$CONFIG_DIR"
printf 'Logs: docker compose --env-file "%s/.env" -f "%s/compose.yml" logs -f\n' "$CONFIG_DIR" "$CONFIG_DIR"
