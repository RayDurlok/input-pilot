#!/usr/bin/env bash
set -euo pipefail

app_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
app_icon="${app_dir}/InputPilotIconRounded.png"
desktop_path="${HOME}/.config/autostart/wayland-automation-tray.desktop"
launcher_path="${HOME}/.local/share/applications/input-pilot-tray.desktop"

mkdir -p "${HOME}/.config/autostart" "${HOME}/.local/share/applications"

desktop_entry() {
  cat <<DESKTOP
[Desktop Entry]
Type=Application
Name=Input Pilot Tray
Comment=Start Input Pilot tray helper
Exec=/usr/bin/python3 ${app_dir}/wayland-automation-tray.py --ydotool-socket /tmp/ydotool_socket
Icon=${app_icon}
Terminal=false
X-GNOME-Autostart-enabled=true
StartupNotify=false
StartupWMClass=input-pilot-tray
X-KDE-DBUS-Restricted-Interfaces=org.kde.KWin.ScreenShot2
DESKTOP
}

desktop_entry > "${desktop_path}"
desktop_entry > "${launcher_path}"

chmod 0644 "${desktop_path}"
chmod 0644 "${launcher_path}"
echo "Installed ${desktop_path}"
echo "Installed ${launcher_path}"
