#!/usr/bin/env bash
set -euo pipefail

app_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
bin_dir="${HOME}/.local/bin"
launcher="${bin_dir}/input-pilot"

missing=()
optional_missing=()

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    missing+=("$1")
  fi
}

optional() {
  if ! command -v "$1" >/dev/null 2>&1; then
    optional_missing+=("$1")
  fi
}

need python3
need ydotool
need wl-copy
need wl-paste
need busctl
need gdbus
need kreadconfig6
need kbuildsycoca6
need kscreen-doctor
need xdg-open
optional notify-send

if (( ${#missing[@]} )); then
  cat >&2 <<EOF
Input Pilot is missing required commands:

  ${missing[*]}

On Fedora KDE, install the matching packages first. Typical package names are:

  sudo dnf install python3-gobject gtk3 libappindicator-gtk3 ydotool wl-clipboard python3-opencv python3-numpy python3-evdev kscreen kf6-kconfig

Then run ./install.sh again.
EOF
  exit 1
fi

if ! /usr/bin/python3 - <<'PY'
import cv2
import evdev
import gi
import numpy

gi.require_version("Gtk", "3.0")
gi.require_version("AppIndicator3", "0.1")
PY
then
  cat >&2 <<'EOF'
Input Pilot is missing required Python modules.

On Fedora KDE, install the matching packages first. Typical package names are:

  sudo dnf install python3-gobject gtk3 libappindicator-gtk3 python3-opencv python3-numpy python3-evdev

Then run ./install.sh again.
EOF
  exit 1
fi

mkdir -p "${bin_dir}"
cat > "${launcher}" <<EOF
#!/usr/bin/env bash
exec /usr/bin/python3 "${app_dir}/wayland-automation-tray.py" --ydotool-socket /tmp/ydotool_socket "\$@"
EOF
chmod 0755 "${launcher}"

"${app_dir}/install-tray-autostart.sh"

if [[ ! -S /tmp/ydotool_socket ]]; then
  cat <<EOF

Input Pilot installed, but /tmp/ydotool_socket is not active yet.
Run this once to configure the persistent ydotool service:

  ${app_dir}/install-ydotool-service.sh

EOF
fi

if (( ${#optional_missing[@]} )); then
  echo "Optional commands missing: ${optional_missing[*]}"
fi

echo "Installed Input Pilot launcher: ${launcher}"
echo "Start it with: input-pilot"
