#!/usr/bin/env bash
set -euo pipefail

app_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
desktop_path="${HOME}/.config/autostart/wayland-automation-tray.desktop"

mkdir -p "${HOME}/.config/autostart"

cat > "${desktop_path}" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Wayland Automation Tray
Comment=Start Wayland Automation tray helper
Exec=/usr/bin/python3 ${app_dir}/wayland-automation-tray.py --ydotool-socket /tmp/ydotool_socket
Icon=input-keyboard
Terminal=false
X-GNOME-Autostart-enabled=true
StartupNotify=false
DESKTOP

chmod 0644 "${desktop_path}"
echo "Installed ${desktop_path}"
