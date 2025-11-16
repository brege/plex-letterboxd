#!/bin/bash
set -e

if [ "$EUID" -eq 0 ]; then
   echo "Do not run this script as root. It will prompt for sudo when needed."
   exit 1
fi

SCHEDULE="${1:-monthly}"

case "$SCHEDULE" in
  daily|weekly|monthly|hourly)
    ;;
  *)
    echo "Usage: $0 [daily|weekly|monthly|hourly]"
    echo "Default: monthly"
    exit 1
    ;;
esac

echo "Installing plex-letterboxd systemd service and timer ($SCHEDULE)..."

# Download service and timer templates
curl -o plex-letterboxd@.service https://raw.githubusercontent.com/brege/plex-letterboxd/refs/heads/main/systemd/plex-letterboxd%40.service
curl -o plex-letterboxd@.timer https://raw.githubusercontent.com/brege/plex-letterboxd/refs/heads/main/systemd/plex-letterboxd%40.timer

# Replace user/group placeholders
sed -i "s|/home/__user__|$HOME|g; s/__user__/$USER/g; s/__group__/$(id -gn)/g" plex-letterboxd@.service

echo "Moving service and timer files to /etc/systemd/system/..."
sudo mv plex-letterboxd@.service /etc/systemd/system/
sudo mv plex-letterboxd@.timer /etc/systemd/system/
sudo chown root:root /etc/systemd/system/plex-letterboxd@.{service,timer}
sudo chmod 644 /etc/systemd/system/plex-letterboxd@.{service,timer}

# Fix SELinux context on Fedora/RHEL
sudo restorecon -v /etc/systemd/system/plex-letterboxd@.{service,timer} 2>/dev/null || true

echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "Enabling and starting plex-letterboxd@${SCHEDULE}.timer..."
sudo systemctl enable --now "plex-letterboxd@${SCHEDULE}.timer"

echo ""
echo "Timer installed successfully!"
echo "Status:"
sudo systemctl status "plex-letterboxd@${SCHEDULE}.timer" --no-pager
echo ""
echo "View logs with:"
echo "  sudo journalctl -u plex-letterboxd@${SCHEDULE}.service"
echo ""
echo "List timers with:"
echo "  systemctl list-timers"
