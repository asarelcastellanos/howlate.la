#!/usr/bin/env bash
# Sets up the collector on a fresh Debian VM. Safe to run again to redeploy.
#
#   sudo bash collector/deploy/setup.sh
#
# Assumes the VM has a service account attached with write access to the bucket,
# which is how the uploader authenticates without any key file on disk.
#
# Nothing on this machine holds state worth keeping. Collected data leaves for
# Cloud Storage within seconds of being written, so rebuilding the VM from
# scratch costs at most the few minutes still sitting in the spool directory.

set -euo pipefail

REPO="https://github.com/asarelcastellanos/howlate.la.git"
APP_DIR="/opt/howlate"
DATA_DIR="/var/lib/howlate"

# The repository also holds the analysis code and the site, and neither belongs
# on this machine. Only this one directory is installed, so the collector's three
# dependencies are the only ones that ever land here.
COMPONENT="collector"

echo "==> Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv git

echo "==> Creating the howlate user"
# A dedicated user with no login shell: if the collector is ever compromised, it
# cannot log in or touch anything outside its own directory.
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
# The package was once called plain "howlate". pip leaves the old one in place
# when installing under the new name, and a stale copy means "python -m
# howlate.record" would quietly run last year's code. Drop it if it is there.
# Safe to delete this block once every machine has deployed past the rename.
if "$APP_DIR/venv/bin/pip" show howlate >/dev/null 2>&1; then
  echo "    removing the old howlate package"
  "$APP_DIR/venv/bin/pip" uninstall --quiet --yes howlate
fi
"$APP_DIR/venv/bin/pip" install --quiet "$APP_DIR/repo/$COMPONENT"

echo "==> Installing services"
install -m 0644 "$APP_DIR"/repo/"$COMPONENT"/deploy/howlate-*.service /etc/systemd/system/
install -m 0644 "$APP_DIR"/repo/"$COMPONENT"/deploy/howlate-*.timer /etc/systemd/system/
systemctl daemon-reload
# Installed by glob above, but enabled by name: a new unit file dropped into
# deploy/ arrives on the machine and then sits there doing nothing until it is
# added to this line.
systemctl enable howlate-record.service howlate-upload.service
systemctl enable howlate-timetable.timer

# restart, not "enable --now": that only starts a service that is stopped, so on
# a redeploy the old code and old environment would keep running and the update
# would silently do nothing. Restarting sends SIGTERM, which finishes the open
# file cleanly before the new version picks up.
systemctl restart howlate-record.service howlate-upload.service
systemctl restart howlate-timetable.timer

echo
echo "==> Done. Current state:"
systemctl is-active howlate-record.service howlate-upload.service | sed 's/^/    /'
echo
echo "    Watch it:   journalctl -u howlate-record -f"
echo "    Next check: systemctl list-timers howlate-timetable"
