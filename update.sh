#!/usr/bin/env bash
#
# Update Input Pilot to the latest GitHub release, in place: download the release
# tarball, copy it over the current install, re-run install.sh, and restart the
# tray. Run it with `input-pilot-update` (installed by install.sh) or `./update.sh`.
#
# The whole script lives inside functions that bash parses into memory before
# main runs, and main ends with `exit`, so copying the new files over this very
# script mid-run cannot corrupt execution.
#
set -euo pipefail

REPO="RayDurlok/input-pilot"
TARBALL_NAME="input-pilot-linux.tar.gz"
TARBALL_URL="https://github.com/${REPO}/releases/latest/download/${TARBALL_NAME}"
YDOTOOL_SOCKET="/tmp/ydotool_socket"

app_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

log() {
  printf '\033[1m==>\033[0m %s\n' "$*"
}

is_tray_process() {
  # True only for a real python tray process, not a shell that mentions the path.
  # comm is the executable name (python3 for the tray, bash for a shell), so it
  # rejects shells whose command line happens to contain the script path.
  local pid="$1" comm cmdline
  comm="$(cat "/proc/${pid}/comm" 2>/dev/null || true)"
  [[ "${comm}" == python* ]] || return 1
  cmdline="$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || true)"
  [[ "${cmdline}" == *"wayland-automation-tray.py"* ]]
}

restart_tray() {
  local pids pid running=0
  pids="$(pgrep -f 'wayland-automation-tray\.py' 2>/dev/null || true)"
  for pid in ${pids}; do
    if is_tray_process "${pid}"; then
      running=1
      kill "${pid}" 2>/dev/null || true
    fi
  done
  if (( ! running )); then
    log "Tray was not running — start it with: input-pilot"
    return 0
  fi
  sleep 1
  if [[ -n "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ]]; then
    log "Restarting the tray..."
    setsid -f /usr/bin/python3 "${app_dir}/wayland-automation-tray.py" \
      --ydotool-socket "${YDOTOOL_SOCKET}" >/dev/null 2>&1 || true
  else
    log "No graphical session detected — start the tray manually with: input-pilot"
  fi
}

apply_update() {
  local src="$1" dest="$2"
  log "Installing update into ${dest}..."
  cp -a "${src}/." "${dest}/"
  chmod +x "${dest}"/*.sh "${dest}"/*.py 2>/dev/null || true
  log "Running installer..."
  "${dest}/install.sh"
}

main() {
  command -v curl >/dev/null 2>&1 || { echo "update needs curl." >&2; exit 1; }
  command -v tar >/dev/null 2>&1 || { echo "update needs tar." >&2; exit 1; }

  local tmp_dir src_dir
  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "${tmp_dir}"' EXIT

  log "Downloading the latest release..."
  if ! curl -fL "${TARBALL_URL}" -o "${tmp_dir}/${TARBALL_NAME}"; then
    echo "Could not download ${TARBALL_URL}" >&2
    exit 1
  fi

  log "Extracting..."
  tar xzf "${tmp_dir}/${TARBALL_NAME}" -C "${tmp_dir}"

  src_dir="${tmp_dir}/input-pilot"
  if [[ ! -d "${src_dir}" ]]; then
    src_dir="$(find "${tmp_dir}" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
  fi
  if [[ -z "${src_dir}" || ! -f "${src_dir}/install.sh" ]]; then
    echo "Downloaded release looks invalid (no install.sh found)." >&2
    exit 1
  fi

  apply_update "${src_dir}" "${app_dir}"
  restart_tray

  log "Input Pilot is up to date."
  exit 0
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
