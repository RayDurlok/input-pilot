#!/usr/bin/env bash
set -euo pipefail

app_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
bin_dir="${HOME}/.local/bin"
launcher="${bin_dir}/input-pilot"
fedora_packages=(
  python3-gobject
  gtk3
  libappindicator-gtk3
  ydotool
  wl-clipboard
  python3-opencv
  python3-numpy
  python3-evdev
  glib2
  xdg-utils
  libkscreen
  kf6-kconfig
  kf6-kservice
)

missing=()
optional_missing=()
python_modules_ok=0

os_id() {
  if [[ -r /etc/os-release ]]; then
    . /etc/os-release
    printf '%s' "${ID:-unknown}"
  else
    printf 'unknown'
  fi
}

is_fedora() {
  [[ "$(os_id)" == "fedora" ]]
}

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

check_commands() {
  missing=()
  optional_missing=()
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
}

check_python_modules() {
  /usr/bin/python3 - <<'PY'
import cv2
import evdev
import gi
import numpy

gi.require_version("Gtk", "3.0")
gi.require_version("AppIndicator3", "0.1")
PY
}

install_fedora_packages() {
  if ! command -v dnf >/dev/null 2>&1; then
    return 1
  fi
  echo "Installing Fedora packages:"
  printf '  %s\n' "${fedora_packages[@]}"
  sudo dnf install -y "${fedora_packages[@]}"
}

print_missing_help() {
  local python_status="no"
  if (( python_modules_ok )); then
    python_status="yes"
  fi
  cat >&2 <<EOF
Input Pilot is missing required dependencies.

Missing commands:
  ${missing[*]:-(none)}
Python modules ok:
  ${python_status}
EOF

  if is_fedora; then
    cat >&2 <<EOF

Install them on Fedora KDE with:

  sudo dnf install ${fedora_packages[*]}

Then run ./install.sh again.
EOF
  else
    cat >&2 <<EOF

Automatic package installation is currently only supported on Fedora.
Install equivalent packages for your distribution, then run ./install.sh again.
Required capabilities are:

  GTK 3 Python bindings, AppIndicator GTK 3, ydotool, wl-clipboard,
  OpenCV for Python, NumPy, python-evdev, KScreen tools, KDE kreadconfig6,
  KDE kbuildsycoca6, GLib tools, xdg-open.
EOF
  fi
}

check_commands
if check_python_modules; then
  python_modules_ok=1
else
  python_modules_ok=0
fi
if (( ${#missing[@]} )) || (( python_modules_ok == 0 )); then
  print_missing_help
  if is_fedora && [[ -t 0 ]] && command -v sudo >/dev/null 2>&1 && command -v dnf >/dev/null 2>&1; then
    read -r -p "Install missing Fedora packages now? [y/N] " reply
    case "${reply}" in
      [yY]|[yY][eE][sS]|[jJ]|[jJ][aA])
        install_fedora_packages
        ;;
      *)
        exit 1
        ;;
    esac
  else
    exit 1
  fi
fi

check_commands
if (( ${#missing[@]} )); then
  print_missing_help
  exit 1
fi

if ! check_python_modules; then
  cat >&2 <<EOF
Input Pilot is missing required Python modules.

EOF
  if is_fedora; then
    cat >&2 <<EOF

Install the required Fedora packages and run ./install.sh again:

  sudo dnf install python3-gobject gtk3 libappindicator-gtk3 python3-opencv python3-numpy python3-evdev
EOF
  else
    cat >&2 <<EOF

Install equivalent packages for your distribution, then run ./install.sh again.
Required Python modules are: gi with Gtk 3 and AppIndicator3, cv2, numpy, evdev.
EOF
  fi
  exit 1
fi

if ! id -nG "${USER}" | grep -qw input; then
  cat <<EOF

Text Replacement needs read access to /dev/input.
Add your user to the input group once, then log out and back in:

  sudo usermod -aG input "${USER}"

EOF
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
