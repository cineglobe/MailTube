#!/bin/sh
set -eu

IMAGE="${MAILTUBE_IMAGE:-ghcr.io/cineglobe/mailtube:latest}"
CONFIG_DIR="${MAILTUBE_CONFIG_DIR:-$HOME/.config/mailtube}"
SETUP_FILE="${MAILTUBE_SETUP_FILE:-}"

fail() { printf 'MailTube: %s\n' "$1" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || fail "Docker is required: https://docs.docker.com/engine/install/"
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required"
if [ -z "$SETUP_FILE" ]; then
  test -t 1 || fail "Interactive setup requires a terminal; use MAILTUBE_SETUP_FILE for unattended setup"
  test -r /dev/tty || fail "Could not open the controlling terminal"
fi

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

if [ -n "$SETUP_FILE" ]; then
  test -f "$SETUP_FILE" || fail "MAILTUBE_SETUP_FILE does not exist: $SETUP_FILE"
  setup_mode=$(stat -c '%a' "$SETUP_FILE" 2>/dev/null || stat -f '%Lp' "$SETUP_FILE" 2>/dev/null || true)
  case "$setup_mode" in
    400|600) ;;
    *) fail "MAILTUBE_SETUP_FILE must be owner-only (chmod 600): $SETUP_FILE" ;;
  esac
  docker run --rm -i \
    --user "$(id -u):$(id -g)" \
    -e MAILTUBE_CONFIG_DIR=/config \
    -e MAILTUBE_IMAGE="$digest" \
    -v "$CONFIG_DIR:/config" \
    "$digest" mailtube setup --non-interactive - < "$SETUP_FILE"
else
  docker run --rm -it \
    --user "$(id -u):$(id -g)" \
    -e MAILTUBE_CONFIG_DIR=/config \
    -e MAILTUBE_IMAGE="$digest" \
    -v "$CONFIG_DIR:/config" \
    "$digest" mailtube setup < /dev/tty
fi

docker compose --env-file "$CONFIG_DIR/.env" -f "$CONFIG_DIR/compose.yml" config >/dev/null
docker compose --env-file "$CONFIG_DIR/.env" -f "$CONFIG_DIR/compose.yml" run --rm --no-deps secrets-init
docker compose --env-file "$CONFIG_DIR/.env" -f "$CONFIG_DIR/compose.yml" run --rm --no-deps \
  --entrypoint /bin/sh mailtube -ec \
  'for path in /run/secrets/admin_password_hash /run/secrets/session_secret; do test -r "$path" || exit 1; done' \
  || fail "Generated secrets are not readable by the non-root MailTube container"
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
if [ "$mode" = "tailscale" ]; then
  printf '\nTailscale mode keeps MailTube on localhost. Existing Serve routes were not changed.\n'
  printf 'Choose an unused HTTPS port and publish it manually, for example:\n'
  printf '  tailscale serve --https=<HTTPS_PORT> --bg http://127.0.0.1:%s\n' "${host_port:-8080}"
  command -v tailscale >/dev/null 2>&1 || printf 'Install Tailscale before running that command.\n'
fi

public_url=$(sed -n 's/^MAILTUBE_PUBLIC_URL=//p' "$CONFIG_DIR/.env" | tr -d '"')
case "$public_url" in
  https://*)
    printf '\nSecure cookies are enabled. Use %s for login and diagnostics; local HTTP sessions will not retain authentication.\n' "$public_url"
    ;;
esac

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

dashboard_url=${public_url:-"http://127.0.0.1:${host_port:-8080}"}
printf '\nMailTube is ready.\nDashboard: %s\nConfiguration: %s\n' "$dashboard_url" "$CONFIG_DIR"
printf 'Logs: docker compose --env-file "%s/.env" -f "%s/compose.yml" logs -f\n' "$CONFIG_DIR" "$CONFIG_DIR"
