#!/usr/bin/env bash
set -euo pipefail

app_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
desktop_id="wayland-automation-open-nextcloud-files.desktop"
desktop_path="${HOME}/.local/share/applications/${desktop_id}"
shortcut_file="${HOME}/.config/kglobalshortcutsrc"
backup="${shortcut_file}.backup-$(date +%Y%m%d-%H%M%S)"

mkdir -p "${HOME}/.local/share/applications" "${HOME}/.config"

cat > "${desktop_path}" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Open Nextcloud Files
Comment=Open Nextcloud files in the browser
Exec=${app_dir}/open-nextcloud-files.sh
Icon=folder-cloud
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
  "Alt+F7,Alt+F7,Open Nextcloud Files"

kbuildsycoca6 >/dev/null 2>&1 || true

if command -v busctl >/dev/null 2>&1; then
  busctl --user call \
    org.kde.kglobalaccel \
    /kglobalaccel \
    org.kde.KGlobalAccel \
    doRegister \
    as 4 "${desktop_id}" _launch "Open Nextcloud Files" "Open Nextcloud Files" \
    >/dev/null 2>&1 || true

  busctl --user call \
    org.kde.kglobalaccel \
    /kglobalaccel \
    org.kde.KGlobalAccel \
    setShortcut \
    asaiu 4 "${desktop_id}" _launch "Open Nextcloud Files" "Open Nextcloud Files" 1 150994998 6 \
    >/dev/null 2>&1 || true
fi

cat <<EOF
Installed ${desktop_path}
Mapped Alt+F7 in ${shortcut_file}

Backup:
${backup}
EOF
