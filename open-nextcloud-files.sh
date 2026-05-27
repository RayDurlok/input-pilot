#!/usr/bin/env bash
set -euo pipefail

url="https://nextcloud.jackandjake.at/apps/files/files"
log_dir="${XDG_STATE_HOME:-$HOME/.local/state}/wayland-automation"
log_file="${log_dir}/open-nextcloud-files.log"
mkdir -p "${log_dir}"
printf '%s open-nextcloud-files invoked pid=%s url=%s display=%s desktop=%s\n' \
  "$(date --iso-8601=seconds)" "$$" "${url}" "${DISPLAY:-}" "${XDG_CURRENT_DESKTOP:-}" \
  >> "${log_file}"

xdg-open "${url}"
