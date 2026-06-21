#!/bin/sh
set -eu

IMAGE="${MAILTUBE_IMAGE:-ghcr.io/cineglobe/mailtube:latest}"
CONFIG_DIR="${MAILTUBE_CONFIG_DIR:-$HOME/.config/mailtube}"
SETUP_FILE="${MAILTUBE_SETUP_FILE:-}"
EXISTING_CONFIG="${MAILTUBE_EXISTING_CONFIG:-}"
RUN_SETUP=1
TAILSCALE_DNS=""
TAILSCALE_HTTPS_PORT="${MAILTUBE_TAILSCALE_HTTPS_PORT:-}"

fail() { printf 'MailTube: %s\n' "$1" >&2; exit 1; }
show_fireworks() {
  test -t 1 || return 0
  printf '\n\033[38;5;39m       .  *  .       \033[38;5;208m.  +  .\n'
  printf '\033[38;5;39m    *  \\ | /  *     \033[38;5;208m* \\ | / *\n'
  printf '\033[38;5;226m  .  -- MAILTUBE --  . \033[38;5;205m-- READY --\n'
  printf '\033[38;5;39m    *  / | \\  *     \033[38;5;208m* / | \\ *\n'
  printf '\033[38;5;39m       .  *  .       \033[38;5;208m.  +  .\033[0m\n'
}
start_tailscale_serve() {
  if [ "$TAILSCALE_HTTPS_PORT" = "443" ]; then
    tailscale serve --bg --yes "$serve_target"
  else
    tailscale serve --https="$TAILSCALE_HTTPS_PORT" --bg --yes "$serve_target"
  fi
}
start_tailscale_serve_as_root() {
  if [ "$TAILSCALE_HTTPS_PORT" = "443" ]; then
    sudo tailscale serve --bg --yes "$serve_target"
  else
    sudo tailscale serve --https="$TAILSCALE_HTTPS_PORT" --bg --yes "$serve_target"
  fi
}
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

if [ -f "$CONFIG_DIR/.env" ] && [ -f "$CONFIG_DIR/secrets/admin_password_hash" ] && \
   [ -f "$CONFIG_DIR/secrets/session_secret" ]; then
  if [ -n "$SETUP_FILE" ]; then
    EXISTING_CONFIG=${EXISTING_CONFIG:-replace}
  elif [ -z "$EXISTING_CONFIG" ]; then
    printf '\nDetected a previous MailTube setup at:\n  %s\n' "$CONFIG_DIR"
    printf '  1) Resume with these preferences and repair generated files (recommended)\n'
    printf '  2) Start fresh (the previous setup will be moved to a timestamped backup)\n'
    while :; do
      printf 'Choose [1-2]: '
      IFS= read -r choice < /dev/tty || fail "Could not read setup recovery choice"
      case "$choice" in
        1|'') EXISTING_CONFIG=resume; break ;;
        2) EXISTING_CONFIG=replace; break ;;
        *) printf 'Enter 1 or 2.\n' ;;
      esac
    done
  fi
  case "$EXISTING_CONFIG" in
    resume) RUN_SETUP=0 ;;
    replace)
      backup_dir="${CONFIG_DIR}.backup.$(date +%Y%m%d-%H%M%S)"
      mv "$CONFIG_DIR" "$backup_dir"
      printf 'Previous setup moved to %s\n' "$backup_dir"
      ;;
    *) fail "MAILTUBE_EXISTING_CONFIG must be resume or replace" ;;
  esac
fi

mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"
printf 'Pulling %s…\n' "$IMAGE"
docker pull "$IMAGE"
digest=$(docker image inspect "$IMAGE" --format '{{index .RepoDigests 0}}')
test -n "$digest" || fail "Could not resolve an immutable image digest"

if [ "$RUN_SETUP" -eq 0 ]; then
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    -e MAILTUBE_CONFIG_DIR=/config \
    -e MAILTUBE_IMAGE="$digest" \
    -v "$CONFIG_DIR:/config" \
    "$digest" mailtube refresh-compose
elif [ -n "$SETUP_FILE" ]; then
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

mode=$(sed -n 's/^MAILTUBE_DEPLOYMENT_MODE=//p' "$CONFIG_DIR/.env" | tr -d '"')
host_port=$(sed -n 's/^MAILTUBE_HTTP_PORT=//p' "$CONFIG_DIR/.env" | tr -d '"')
TAILSCALE_HTTPS_PORT=${TAILSCALE_HTTPS_PORT:-${host_port:-8080}}
if [ "$mode" = "tailscale" ] && command -v tailscale >/dev/null 2>&1; then
  TAILSCALE_DNS=$(
    tailscale status --json 2>/dev/null | docker run --rm -i --entrypoint python "$digest" \
      -c 'import json,sys; print(json.load(sys.stdin).get("Self", {}).get("DNSName", "").rstrip("."))' \
      2>/dev/null
  ) || TAILSCALE_DNS=""
  if [ -n "$TAILSCALE_DNS" ]; then
    docker run --rm \
      --user "$(id -u):$(id -g)" \
      -e MAILTUBE_CONFIG_DIR=/config \
      -v "$CONFIG_DIR:/config" \
      "$digest" mailtube configure-tailscale "$TAILSCALE_DNS" --https-port "$TAILSCALE_HTTPS_PORT"
  else
    printf 'Tailscale is installed but its MagicDNS name could not be detected.\n'
  fi
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

docker compose --env-file "$CONFIG_DIR/.env" -f "$CONFIG_DIR/compose.yml" exec -T mailtube \
  mailtube doctor >/dev/null || fail "Post-start diagnostics failed. Run: docker compose -f $CONFIG_DIR/compose.yml logs"

if [ "$mode" = "tailscale" ]; then
  serve_target="http://127.0.0.1:${host_port:-8080}"
  if [ -n "$TAILSCALE_DNS" ]; then
    if [ "$TAILSCALE_HTTPS_PORT" = "443" ]; then
      dashboard_url="https://$TAILSCALE_DNS"
      retry_command="sudo tailscale serve --bg --yes $serve_target"
    else
      dashboard_url="https://$TAILSCALE_DNS:$TAILSCALE_HTTPS_PORT"
      retry_command="sudo tailscale serve --https=$TAILSCALE_HTTPS_PORT --bg --yes $serve_target"
    fi
    if start_tailscale_serve; then
      serve_ok=1
    elif command -v sudo >/dev/null 2>&1 && test -r /dev/tty; then
      printf '\nTailscale requires administrator permission. sudo may prompt for your password.\n'
      if start_tailscale_serve_as_root < /dev/tty; then
        serve_ok=1
      else
        serve_ok=0
      fi
    else
      serve_ok=0
    fi
    if [ "$serve_ok" -eq 1 ]; then
      printf '\nTailscale Serve is active at %s\n' "$dashboard_url"
    else
      printf '\nMailTube is healthy locally, but Tailscale Serve could not be activated. Try:\n  %s\n' "$retry_command"
      printf 'To avoid future sudo prompts, run once: sudo tailscale set --operator="$USER"\n'
    fi
  else
    printf '\nMailTube is healthy locally, but Tailscale Serve is unavailable. Install or connect Tailscale, then rerun this installer.\n'
  fi
fi

public_url=$(sed -n 's/^MAILTUBE_PUBLIC_URL=//p' "$CONFIG_DIR/.env" | tr -d '"')
case "$public_url" in
  https://*)
    printf '\nSecure cookies are enabled. Use %s for login and diagnostics; local HTTP sessions will not retain authentication.\n' "$public_url"
    ;;
esac

update_channel=$(sed -n 's/^MAILTUBE_UPDATE_CHANNEL=//p' "$CONFIG_DIR/.env" | tr -d '"')
update_channel=${update_channel:-stable}
updater_container=$(docker create "$digest")
docker cp "$updater_container:/usr/local/share/mailtube/update.sh" "$CONFIG_DIR/update.sh"
docker cp "$updater_container:/usr/local/share/mailtube/install-updater.sh" "$CONFIG_DIR/install-updater.sh"
docker rm "$updater_container" >/dev/null
chmod 700 "$CONFIG_DIR/update.sh" "$CONFIG_DIR/install-updater.sh"
MAILTUBE_CONFIG_DIR="$CONFIG_DIR" \
MAILTUBE_UPDATE_CHANNEL="$update_channel" \
MAILTUBE_MANIFEST_URL="${MAILTUBE_MANIFEST_URL:-}" \
MAILTUBE_COSIGN_IDENTITY="${MAILTUBE_COSIGN_IDENTITY:-}" \
  "$CONFIG_DIR/install-updater.sh"

# dashboard-url:start
# Exercised under dash by tests/test_installer.py.
if [ -z "${dashboard_url:-}" ]; then
  if [ -n "${public_url:-}" ]; then
    dashboard_url=$public_url
  else
    dashboard_url="http://127.0.0.1:${host_port:-8080}"
  fi
fi
# dashboard-url:end
show_fireworks
printf '\nMailTube is ready.\nDashboard: %s\nConfiguration: %s\n' "$dashboard_url" "$CONFIG_DIR"
printf 'Logs: docker compose --env-file "%s/.env" -f "%s/compose.yml" logs -f\n' "$CONFIG_DIR" "$CONFIG_DIR"
