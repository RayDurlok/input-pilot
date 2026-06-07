#!/usr/bin/env bash
set -euo pipefail

rm -f "${HOME}/.local/bin/input-pilot"
rm -f "${HOME}/.config/autostart/wayland-automation-tray.desktop"
rm -f "${HOME}/.local/share/applications/input-pilot-tray.desktop"

if command -v kbuildsycoca6 >/dev/null 2>&1; then
  kbuildsycoca6 >/dev/null 2>&1 || true
fi

cat <<'EOF'
Removed Input Pilot launcher and desktop entries.

User configuration is kept in:
  ~/.config/wayland-automation/

User logs are kept in:
  ~/.local/state/wayland-automation/

The ydotool system service override is not removed automatically.
EOF
