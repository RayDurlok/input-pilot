#!/usr/bin/env bash
set -euo pipefail

app_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
desktop_id="wayland-automation-open-downloads.desktop"
old_desktop_id="codex-open-downloads.desktop"
desktop_path="${HOME}/.local/share/applications/${desktop_id}"
shortcut_file="${HOME}/.config/kglobalshortcutsrc"
backup="${shortcut_file}.backup-$(date +%Y%m%d-%H%M%S)"

mkdir -p "${HOME}/.local/share/applications" "${HOME}/.config"

cat > "${desktop_path}" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Open Downloads
Comment=Open /home/jakob/Downloads/
Exec=${app_dir}/open-downloads.sh
Icon=folder-download
Terminal=false
NoDisplay=true
StartupNotify=false
Categories=Utility;
X-KDE-GlobalAccel-CommandShortcut=true
DESKTOP

chmod 0644 "${desktop_path}"

if [[ -f "${shortcut_file}" ]]; then
  cp "${shortcut_file}" "${backup}"
fi

kwriteconfig6 \
  --file "${shortcut_file}" \
  --group "services" \
  --group "${desktop_id}" \
  --key "_launch" \
  "F1\tHelp,F1\tHelp,Open Downloads"

kwriteconfig6 \
  --file "${shortcut_file}" \
  --group "services" \
  --group "${old_desktop_id}" \
  --key "_launch" \
  --delete \
  "" || true

rm -f "${HOME}/.local/share/applications/${old_desktop_id}"

kbuildsycoca6 >/dev/null 2>&1 || true

if command -v busctl >/dev/null 2>&1; then
  busctl --user call \
    org.kde.kglobalaccel \
    /kglobalaccel \
    org.kde.KGlobalAccel \
    doRegister \
    as 4 "${desktop_id}" _launch "Open Downloads" "Open Downloads" \
    >/dev/null 2>&1 || true

  busctl --user call \
    org.kde.kglobalaccel \
    /kglobalaccel \
    org.kde.KGlobalAccel \
    unregister \
    ss "${old_desktop_id}" _launch \
    >/dev/null 2>&1 || true

  busctl --user call \
    org.kde.kglobalaccel \
    /kglobalaccel \
    org.kde.KGlobalAccel \
    setShortcut \
    asaiu 4 "${desktop_id}" _launch "Open Downloads" "Open Downloads" 2 16777264 16777304 6 \
    >/dev/null 2>&1 || true
fi

cat <<EOF
Installed ${desktop_path}
Mapped F1/Help in ${shortcut_file}

Backup:
${backup}

If F1 does not react immediately, log out and back in, or open KDE System
Settings -> Keyboard -> Shortcuts and confirm the Open Downloads shortcut once.
EOF
