#!/usr/bin/env bash
set -euo pipefail

log_dir="${XDG_STATE_HOME:-$HOME/.local/state}/wayland-automation"
log_file="${log_dir}/open-downloads.log"
mkdir -p "${log_dir}"
printf '%s open-downloads invoked pid=%s display=%s desktop=%s\n' \
  "$(date --iso-8601=seconds)" "$$" "${DISPLAY:-}" "${XDG_CURRENT_DESKTOP:-}" \
  >> "${log_file}"

xdg-open "${HOME}/Downloads/"
