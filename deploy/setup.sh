#!/usr/bin/env bash
# Sets up the collector on a fresh Debian VM. Safe to run again to redeploy.
#
#   sudo bash setup.sh
#
# Assumes the VM has a service account attached with write access to the
# bucket, which is how the uploader authenticates without any key file.

set -euo pipefail

REPO="https://github.com/asarelcastellanos/howlate.la.git"
APP_DIR="/opt/howlate"
DATA_DIR="/var/lib/howlate"

echo "==> Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv git

echo "==> Creating the howlate user"
# A dedicated user with no login shell: if the collector is ever compromised,
# it cannot log in or touch anything outside its own directory.
id -u howlate &>/dev/null || useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin howlate
install -d -o howlate -g howlate -m 0755 "$DATA_DIR" "$DATA_DIR/data"

echo "==> Fetching the code"
if [ -d "$APP_DIR/repo/.git" ]; then
  git -C "$APP_DIR/repo" fetch --quiet origin
  git -C "$APP_DIR/repo" reset --hard --quiet origin/main
else
  install -d -m 0755 "$APP_DIR"
  git clone --quiet "$REPO" "$APP_DIR/repo"
fi

echo "==> Installing into a virtualenv"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet "$APP_DIR/repo"

echo "==> Installing services"
install -m 0644 "$APP_DIR"/repo/deploy/howlate-*.service /etc/systemd/system/
install -m 0644 "$APP_DIR"/repo/deploy/howlate-*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now howlate-record.service howlate-upload.service
systemctl enable --now howlate-timetable.timer

echo
echo "==> Done. Current state:"
systemctl is-active howlate-record.service howlate-upload.service | sed 's/^/    /'
echo
echo "    Watch it:   journalctl -u howlate-record -f"
echo "    Next check: systemctl list-timers howlate-timetable"
