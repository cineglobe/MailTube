#!/bin/sh
set -eu

CONFIG_DIR="${MAILTUBE_CONFIG_DIR:-$HOME/.config/mailtube}"
MANIFEST_URL="${MAILTUBE_MANIFEST_URL:-https://github.com/cineglobe/MailTube/releases/latest/download/stable-manifest.json}"
COSIGN_IDENTITY="${MAILTUBE_COSIGN_IDENTITY:-https://github.com/cineglobe/MailTube/.github/workflows/release.yml@refs/heads/main}"

compose() {
  docker compose --env-file "$CONFIG_DIR/.env" -f "$CONFIG_DIR/compose.yml" "$@"
}

channel=$(compose exec -T mailtube python -c \
  'from mailtube.config import Settings; from mailtube.db import Database; s=Settings(); print(Database(s.db_path).get_runtime_settings().get("update_channel", s.update_channel))')
if [ "$channel" != "stable" ]; then
  echo "MailTube stable updates are disabled"
  exit 0
fi

lock="$CONFIG_DIR/.update.lock"
if ! mkdir "$lock" 2>/dev/null; then
  echo "A MailTube update check is already running"
  exit 0
fi
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"; rmdir "$lock" 2>/dev/null || true' EXIT INT TERM

old=$(sed -n 's/^MAILTUBE_IMAGE=//p' "$CONFIG_DIR/.env" | tr -d '"')
test -n "$old" || { echo "MAILTUBE_IMAGE is missing" >&2; exit 1; }
curl -fsSL "$MANIFEST_URL" -o "$tmp/manifest.json"
json_field() {
  compose exec -T mailtube python -c \
    'import json,sys; value=json.load(sys.stdin).get(sys.argv[1]); isinstance(value,str) and value or sys.exit(1); print(value)' \
    "$1" < "$tmp/manifest.json"
}
image=$(json_field image)
digest=$(json_field digest)
version=$(json_field version)
if ! compose exec -T mailtube python -c \
  'import re,sys; ok=sys.argv[1]=="ghcr.io/cineglobe/mailtube" and re.fullmatch(r"sha256:[0-9a-f]{64}",sys.argv[2]) and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+",sys.argv[3]); sys.exit(0 if ok else 1)' \
  "$image" "$digest" "$version"; then
  echo "Stable manifest contains an invalid image, digest, or version" >&2
  exit 1
fi
reference="$image@$digest"
current=$(compose exec -T mailtube python -c \
  "import json,urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health'))['version'])")
relation=$(compose exec -T mailtube python -c \
  'import sys; a=tuple(map(int,sys.argv[1].split("."))); b=tuple(map(int,sys.argv[2].split("."))); print("newer" if b>a else "same" if b==a else "older")' \
  "$current" "$version")
if [ "$relation" = "same" ]; then
  echo "MailTube $current is already current"
  exit 0
fi
if [ "$relation" = "older" ]; then
  echo "Refusing to downgrade MailTube $current to $version" >&2
  exit 1
fi
if [ "${current%%.*}" != "${version%%.*}" ]; then
  echo "Major update $current -> $version requires explicit operator approval" >&2
  exit 2
fi

run_cosign() {
  if command -v cosign >/dev/null 2>&1; then
    cosign "$@"
  else
    docker run --rm -e HOME=/tmp --entrypoint /usr/local/bin/cosign "$old" "$@"
  fi
}
run_cosign verify "$reference" \
  --certificate-identity "$COSIGN_IDENTITY" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com >/dev/null
run_cosign verify-attestation "$reference" \
  --type slsaprovenance \
  --certificate-identity "$COSIGN_IDENTITY" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com >/dev/null

backup_path="/data/backups/pre-update-$version.db"
compose exec -T mailtube mailtube backup "$backup_path"
cp "$CONFIG_DIR/compose.yml" "$tmp/compose.yml"
docker pull "$reference"
sed "s|^MAILTUBE_IMAGE=.*|MAILTUBE_IMAGE=$reference|" "$CONFIG_DIR/.env" > "$tmp/env"
chmod 600 "$tmp/env"
mv "$tmp/env" "$CONFIG_DIR/.env"
docker run --rm --user "$(id -u):$(id -g)" \
  -e MAILTUBE_CONFIG_DIR=/config -e MAILTUBE_IMAGE="$reference" \
  -v "$CONFIG_DIR:/config" "$reference" mailtube refresh-compose
compose up -d

healthy=0
attempt=0
while [ "$attempt" -lt 30 ]; do
  if compose exec -T mailtube python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health', timeout=3)" >/dev/null 2>&1; then
    healthy=1
    break
  fi
  attempt=$((attempt + 1))
  sleep 2
done
if [ "$healthy" -ne 1 ]; then
  sed "s|^MAILTUBE_IMAGE=.*|MAILTUBE_IMAGE=$old|" "$CONFIG_DIR/.env" > "$tmp/rollback.env"
  chmod 600 "$tmp/rollback.env"
  mv "$tmp/rollback.env" "$CONFIG_DIR/.env"
  cp "$tmp/compose.yml" "$CONFIG_DIR/compose.yml"
  compose stop mailtube
  compose run --rm --no-deps -e BACKUP_PATH="$backup_path" --entrypoint /bin/sh mailtube -ec \
    'cp "$BACKUP_PATH" /data/mailtube.db; rm -f /data/mailtube.db-wal /data/mailtube.db-shm'
  compose up -d
  echo "Update failed health checks; restored MailTube $current and its database" >&2
  exit 1
fi

updater_container=$(docker create "$reference")
docker cp "$updater_container:/usr/local/share/mailtube/update.sh" "$tmp/update.sh"
docker rm "$updater_container" >/dev/null
chmod 700 "$tmp/update.sh"
mv "$tmp/update.sh" "$CONFIG_DIR/update.sh"
echo "Updated MailTube $current -> $version"
