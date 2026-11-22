#!/usr/bin/env bash
# One-command installer for the tee time bot on an Ubuntu server (22.04 / 24.04).
# Installs an always-on service that stays logged in and checks every 60 seconds.
# Re-run any time to update the code (your logins and booking log are kept):
#
#   sudo bash /opt/teebot/server/setup.sh
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/hinklee17/teebot}"
APP=/opt/teebot
ENV_FILE=/etc/teebot.env
INTERVAL="${INTERVAL:-60}"   # seconds between checks

[ "$(id -u)" -eq 0 ] || { echo "Please run with sudo."; exit 1; }
say() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }

say "Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git python3-venv python3-pip >/dev/null

# Chromium needs memory; add 1 GB swap on small servers.
if ! swapon --show | grep -q .; then
  say "Adding 1 GB swap"
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

id teebot >/dev/null 2>&1 || useradd --system --home "$APP" --shell /usr/sbin/nologin teebot

say "Getting the latest code"
# The folder belongs to the bot's user; tell git (run as root) that's fine.
git config --global --get-all safe.directory 2>/dev/null | grep -qx "$APP" \
  || git config --global --add safe.directory "$APP"
if [ -d "$APP/.git" ]; then
  [ -f "$APP/state.json" ] && cp "$APP/state.json" /tmp/teebot-state.json
  git -C "$APP" fetch -q origin main
  git -C "$APP" reset -q --hard origin/main
  [ -f /tmp/teebot-state.json ] && mv /tmp/teebot-state.json "$APP/state.json"
else
  git clone -q "$REPO_URL" "$APP"
fi

say "Installing Python packages and the browser (takes a couple of minutes)"
python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install -q --upgrade pip
"$APP/venv/bin/pip" install -q -r "$APP/requirements.txt"
# Prefer IPv4: droplets often have no IPv6, which breaks the browser download.
NODE_OPTIONS=--dns-result-order=ipv4first PLAYWRIGHT_BROWSERS_PATH="$APP/browsers" \
  "$APP/venv/bin/python" -m playwright install --with-deps chromium >/dev/null
compgen -G "$APP/browsers/chromium*" >/dev/null || { echo "Browser download failed; re-run this installer."; exit 1; }
chown -R teebot:teebot "$APP"

if [ ! -f "$ENV_FILE" ]; then
  say "Enter your logins (passwords are hidden as you type; nothing is shown or logged)"
  read -r  -p "Club login email: " CLUB_USERNAME </dev/tty
  read -rs -p "Club password: " CLUB_PASSWORD </dev/tty; echo
  echo "Email: paste the Google Apps Script web app URL and the secret phrase you set in it."
  read -r  -p "Email web app URL (https://script.google.com/macros/s/.../exec): " MAIL_WEBHOOK_URL </dev/tty
  read -rs -p "Email secret phrase (same as SECRET in the script): " MAIL_SECRET </dev/tty; echo
  read -r  -p "healthchecks.io ping URL (optional, press Enter to skip): " HEALTHCHECK_URL </dev/tty
  # systemd env-file quoting: wrap in "..." and escape backslashes and quotes
  q() { local v=${1//\\/\\\\}; v=${v//\"/\\\"}; printf '"%s"' "$v"; }
  umask 077
  {
    echo "CLUB_USERNAME=$(q "$CLUB_USERNAME")"
    echo "CLUB_PASSWORD=$(q "$CLUB_PASSWORD")"
    echo "MAIL_WEBHOOK_URL=$(q "$MAIL_WEBHOOK_URL")"
    echo "MAIL_SECRET=$(q "$MAIL_SECRET")"
    echo "HEALTHCHECK_URL=$(q "$HEALTHCHECK_URL")"
  } > "$ENV_FILE"
  chmod 600 "$ENV_FILE"; chown root:root "$ENV_FILE"
else
  say "Keeping existing logins in $ENV_FILE"
fi

say "Installing the always-on service"
# Remove the older once-a-minute timer version if it's there.
systemctl disable --now teebot.timer >/dev/null 2>&1 || true
rm -f /etc/systemd/system/teebot.timer

cat > /etc/systemd/system/teebot.service <<EOF
[Unit]
Description=Tee time bot (always on)
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=teebot
WorkingDirectory=$APP
EnvironmentFile=$ENV_FILE
Environment=PLAYWRIGHT_BROWSERS_PATH=$APP/browsers
Environment=DRY_RUN=false
Environment=INTERVAL=$INTERVAL
Environment=PYTHONUNBUFFERED=1
ExecStart=$APP/venv/bin/python -m teebot.runner
Restart=always
RestartSec=30
Nice=10
MemoryMax=900M

[Install]
WantedBy=multi-user.target
EOF

# Small helper commands.
cat > /usr/local/bin/teebot-rearm <<EOF
#!/usr/bin/env bash
# Let the bot book a date again, e.g.:  sudo teebot-rearm 2026-11-21
set -euo pipefail
[ \$# -eq 1 ] || { echo "usage: sudo teebot-rearm YYYY-MM-DD"; exit 1; }
sudo -u teebot $APP/venv/bin/python - "\$1" <<'PY'
import json, sys
p = "$APP/state.json"
s = json.load(open(p))
print("removed:", s.get("booked", {}).pop(sys.argv[1], "(not found)"))
json.dump(s, open(p, "w"), indent=2)
PY
EOF
cat > /usr/local/bin/teebot-update <<EOF
#!/usr/bin/env bash
# Pull the latest code from GitHub and restart:  sudo teebot-update
exec bash $APP/server/setup.sh
EOF
chmod 755 /usr/local/bin/teebot-rearm /usr/local/bin/teebot-update

systemctl daemon-reload

run_as_bot() {
  systemd-run --quiet --wait --pipe --collect \
    -p User=teebot -p WorkingDirectory="$APP" -p EnvironmentFile="$ENV_FILE" \
    -E PLAYWRIGHT_BROWSERS_PATH="$APP/browsers" "$@"
}

say "Sending a test email"
if run_as_bot "$APP/venv/bin/python" -m teebot.notify; then
  echo "  Test email sent. Check your inbox (and spam folder)."
else
  echo "  WARNING: the test email failed (see above). The bot can still book, but it"
  echo "  can't tell you. Fix: sudo rm $ENV_FILE && sudo teebot-update  (re-enter the email details)"
fi

say "Test run (dry run: looks, never books)"
if run_as_bot -E DRY_RUN=1 "$APP/venv/bin/python" -m teebot.bot; then
  systemctl enable teebot.service >/dev/null
  systemctl restart teebot.service
  say "Done! The bot is LIVE and checks every ${INTERVAL} seconds."
  echo "  Watch it:     journalctl -u teebot -f        (Ctrl+C to stop watching)"
  echo "  Pause:        sudo systemctl stop teebot"
  echo "  Resume:       sudo systemctl start teebot"
  echo "  Re-arm a day: sudo teebot-rearm 2026-11-21"
  echo "  Update code:  sudo teebot-update"
else
  echo
  echo "The test run failed (see messages above). The bot was NOT turned on."
  echo "Fix the problem, then re-run:  sudo bash $APP/server/setup.sh"
  echo "To re-enter logins:            sudo rm $ENV_FILE  and re-run."
  exit 1
fi
