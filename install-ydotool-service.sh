#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  exec pkexec "$0" "$@"
fi

override_dir="/etc/systemd/system/ydotool.service.d"
override_file="${override_dir}/override.conf"

install -d -m 0755 "${override_dir}"
cat > "${override_file}" <<'SERVICE'
[Service]
ExecStart=
ExecStart=/usr/bin/ydotoold -p /tmp/ydotool_socket -P 0666
SERVICE

systemctl daemon-reload
systemctl enable --now ydotool.service
systemctl restart ydotool.service

echo "Installed persistent ydotool.service override for /tmp/ydotool_socket"
