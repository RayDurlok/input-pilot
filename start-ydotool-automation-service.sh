#!/usr/bin/env bash
set -euo pipefail

socket_path="${1:-/tmp/ydotool_socket}"

systemctl stop ydotool >/dev/null 2>&1 || true
systemctl stop ydotool-automation >/dev/null 2>&1 || true

systemd-run \
  --unit=ydotool-automation \
  --property=Restart=always \
  /usr/bin/ydotoold \
  -p "${socket_path}" \
  -P 0666

echo "Started ydotool-automation with socket ${socket_path}"
echo "Use: YDOTOOL_SOCKET=${socket_path} ydotool debug"
