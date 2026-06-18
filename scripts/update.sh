#!/bin/sh
set -eu

CONFIG_DIR="${MAILTUBE_CONFIG_DIR:-$HOME/.config/mailtube}"
MANIFEST_URL="${MAILTUBE_MANIFEST_URL:?Set MAILTUBE_MANIFEST_URL to the signed stable manifest}"
COSIGN_IDENTITY="${MAILTUBE_COSIGN_IDENTITY:?Set MAILTUBE_COSIGN_IDENTITY to the release workflow identity}"
command -v cosign >/dev/null 2>&1 || { echo "cosign is required" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "jq is required" >&2; exit 1; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT INT TERM
curl -fsSL "$MANIFEST_URL" -o "$tmp/manifest.json"
image=$(jq -er '.image' "$tmp/manifest.json")
digest=$(jq -er '.digest' "$tmp/manifest.json")
version=$(jq -er '.version' "$tmp/manifest.json")
case "$version" in *.*.*) ;; *) echo "Invalid version" >&2; exit 1;; esac
reference="$image@$digest"
current=$(docker compose --env-file "$CONFIG_DIR/.env" -f "$CONFIG_DIR/compose.yml" exec -T mailtube \
  python -c "import json,urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health'))['version'])")
if [ "${current%%.*}" != "${version%%.*}" ]; then
  echo "Major update $current -> $version requires explicit operator approval" >&2
  exit 2
fi
cosign verify "$reference" \
  --certificate-identity "$COSIGN_IDENTITY" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com >/dev/null
cosign verify-attestation "$reference" \
  --type slsaprovenance \
  --certificate-identity "$COSIGN_IDENTITY" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com >/dev/null

old=$(sed -n 's/^MAILTUBE_IMAGE=//p' "$CONFIG_DIR/.env" | tr -d '"')
docker compose --env-file "$CONFIG_DIR/.env" -f "$CONFIG_DIR/compose.yml" exec -T mailtube \
  mailtube backup "/data/backups/pre-update-$version.db"
docker pull "$reference"
sed "s|^MAILTUBE_IMAGE=.*|MAILTUBE_IMAGE=$reference|" "$CONFIG_DIR/.env" > "$tmp/env"
chmod 600 "$tmp/env"
mv "$tmp/env" "$CONFIG_DIR/.env"
docker compose --env-file "$CONFIG_DIR/.env" -f "$CONFIG_DIR/compose.yml" up -d
sleep 15
if ! docker compose --env-file "$CONFIG_DIR/.env" -f "$CONFIG_DIR/compose.yml" exec -T mailtube \
  python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health', timeout=3)"; then
  sed "s|^MAILTUBE_IMAGE=.*|MAILTUBE_IMAGE=$old|" "$CONFIG_DIR/.env" > "$tmp/env"
  chmod 600 "$tmp/env"
  mv "$tmp/env" "$CONFIG_DIR/.env"
  docker compose --env-file "$CONFIG_DIR/.env" -f "$CONFIG_DIR/compose.yml" up -d
  echo "Update failed health checks; rolled back to $old" >&2
  exit 1
fi
echo "Updated MailTube to $version"
