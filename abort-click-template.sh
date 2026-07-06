#!/usr/bin/env bash
set -euo pipefail

state_dir="${XDG_STATE_HOME:-${HOME}/.local/state}/wayland-automation"
abort_file="${state_dir}/click-template.abort"
sequence_abort_file="${state_dir}/mouse-sequence.abort"
lock_file="${state_dir}/click-template.lock"
pause_file="${state_dir}/paused"
socket="${YDOTOOL_SOCKET:-/tmp/ydotool_socket}"
app_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
settings_file="${HOME}/.config/wayland-automation/settings.json"
text_replacement_engine="${app_dir}/input-pilot-text-replacement.py"

mkdir -p "${state_dir}"

notifications_enabled() {
  if [[ -f "${settings_file}" ]] \
    && command -v python3 >/dev/null 2>&1 \
    && python3 - "${settings_file}" <<'PY'
import json
import sys
try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        data = json.load(handle)
except Exception:
    data = {}
raise SystemExit(0 if data.get("notifications_disabled") else 1)
PY
  then
    return 1
  fi
  command -v notify-send >/dev/null 2>&1
}

notify_input_pilot() {
  if notifications_enabled; then
    notify-send "Input Pilot" "$1"
  fi
}

stop_running() {
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
}

stop_app_helpers() {
  if [[ -x "${text_replacement_engine}" ]]; then
    "${text_replacement_engine}" --stop >/dev/null 2>&1 || true
  fi
}

start_app_helpers() {
  if [[ -x "${text_replacement_engine}" ]]; then
    YDOTOOL_SOCKET="${socket}" setsid -f "${text_replacement_engine}" --ydotool-socket "${socket}" >/dev/null 2>&1 || true
  fi
}

# F12 / the tray menu toggle global suspend. Pausing also stops anything that is
# currently running and releases held mouse buttons; resuming clears the abort
# flags so the next trigger starts cleanly.
if [[ -e "${pause_file}" ]]; then
  rm -f "${pause_file}" "${abort_file}" "${sequence_abort_file}"
  start_app_helpers
  notify_input_pilot "Resumed."
else
  stop_running
  stop_app_helpers
  touch "${pause_file}"
  notify_input_pilot "Suspended — press F12 or use the tray menu to resume."
fi
