#!/bin/sh
set -eu

CONFIG_DIR="${MAILTUBE_CONFIG_DIR:-$HOME/.config/mailtube}"
MANIFEST_URL="${MAILTUBE_MANIFEST_URL:-https://github.com/cineglobe/MailTube/releases/latest/download/stable-manifest.json}"
COSIGN_IDENTITY="${MAILTUBE_COSIGN_IDENTITY:-https://github.com/cineglobe/MailTube/.github/workflows/release.yml@refs/heads/main}"
UPDATE_CHANNEL="${MAILTUBE_UPDATE_CHANNEL:-stable}"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
install -m 700 "$SCRIPT_DIR/update.sh" "$CONFIG_DIR/update.sh"

case "$(uname -s)" in
  Linux)
    unit_dir="$HOME/.config/systemd/user"
    if [ "$UPDATE_CHANNEL" = "off" ]; then
      systemctl --user disable --now mailtube-update.timer 2>/dev/null || true
      rm -f "$unit_dir/mailtube-update.timer" "$unit_dir/mailtube-update.service"
      systemctl --user daemon-reload
      echo "MailTube automatic updates are disabled."
      exit 0
    fi
    mkdir -p "$unit_dir"
    cat > "$unit_dir/mailtube-update.service" <<EOF
[Unit]
Description=Install a verified stable MailTube update
[Service]
Type=oneshot
TimeoutStartSec=30min
Environment=MAILTUBE_CONFIG_DIR=$CONFIG_DIR
Environment=MAILTUBE_MANIFEST_URL=$MANIFEST_URL
Environment=MAILTUBE_COSIGN_IDENTITY=$COSIGN_IDENTITY
ExecStart=$CONFIG_DIR/update.sh
EOF
    cat > "$unit_dir/mailtube-update.timer" <<EOF
[Unit]
Description=MailTube stable update check every six hours
[Timer]
OnBootSec=10min
OnUnitActiveSec=6h
RandomizedDelaySec=15min
Persistent=true
[Install]
WantedBy=timers.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable --now mailtube-update.timer
    ;;
  Darwin)
    label="org.mailtube.update"
    plist="$HOME/Library/LaunchAgents/$label.plist"
    if [ "$UPDATE_CHANNEL" = "off" ]; then
      launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
      rm -f "$plist"
      echo "MailTube automatic updates are disabled."
      exit 0
    fi
    mkdir -p "$HOME/Library/LaunchAgents"
    cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>$label</string>
<key>ProgramArguments</key><array><string>$CONFIG_DIR/update.sh</string></array>
<key>EnvironmentVariables</key><dict>
<key>MAILTUBE_CONFIG_DIR</key><string>$CONFIG_DIR</string>
<key>MAILTUBE_MANIFEST_URL</key><string>$MANIFEST_URL</string>
<key>MAILTUBE_COSIGN_IDENTITY</key><string>$COSIGN_IDENTITY</string>
</dict>
<key>StartInterval</key><integer>21600</integer>
<key>ProcessType</key><string>Background</string>
</dict></plist>
EOF
    launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$plist"
    ;;
  *) echo "Use Task Scheduler with scripts/update.ps1 on Windows." >&2; exit 1 ;;
esac

echo "MailTube signed stable updates are scheduled every six hours."
