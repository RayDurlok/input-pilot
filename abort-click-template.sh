#!/usr/bin/env bash
set -euo pipefail

state_dir="${XDG_STATE_HOME:-${HOME}/.local/state}/wayland-automation"
abort_file="${state_dir}/click-template.abort"
sequence_abort_file="${state_dir}/mouse-sequence.abort"
lock_file="${state_dir}/click-template.lock"
socket="${YDOTOOL_SOCKET:-/tmp/ydotool_socket}"
app_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "${state_dir}"
touch "${abort_file}"
touch "${sequence_abort_file}"

if [[ -s "${lock_file}" ]]; then
  pid="$(cat "${lock_file}" 2>/dev/null || true)"
  if [[ "${pid}" =~ ^[0-9]+$ ]]; then
    kill "${pid}" 2>/dev/null || true
  fi
fi

pkill -f "${app_dir}/wayland-click-image.py" 2>/dev/null || true
rm -f "${lock_file}"

if command -v ydotool >/dev/null 2>&1; then
  YDOTOOL_SOCKET="${socket}" ydotool click 0x80 0x81 0x82 >/dev/null 2>&1 || true
fi

if command -v notify-send >/dev/null 2>&1; then
  notify-send "Input Pilot" "Running automation aborted."
fi
