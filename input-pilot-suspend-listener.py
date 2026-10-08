#!/usr/bin/env python3
"""Tiny low-level suspend-key listener for Input Pilot.

This intentionally avoids KGlobalAccel for the emergency/suspend key because
that path can crash KWin on affected Plasma builds.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from evdev import InputDevice, categorize, ecodes, list_devices
from input_pilot_dolphin_preview import eligible_window


SETTINGS_FILE = Path.home() / ".config/wayland-automation/settings.json"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
LOG_FILE = STATE_DIR / "wayland-automation/suspend-listener.log"
PID_FILE = STATE_DIR / "wayland-automation/suspend-listener.pid"
DEFAULT_YDOTOOL_SOCKET = "/tmp/ydotool_socket"
SCRIPT_DIR = Path(__file__).resolve().parent
ABORT_CLICK = SCRIPT_DIR / "abort-click-template.sh"
DEFAULT_SUSPEND_SHORTCUT = "F12"

MODIFIER_KEYS = {
    ecodes.KEY_LEFTCTRL,
    ecodes.KEY_RIGHTCTRL,
    ecodes.KEY_LEFTALT,
    ecodes.KEY_RIGHTALT,
    ecodes.KEY_LEFTMETA,
    ecodes.KEY_RIGHTMETA,
    ecodes.KEY_LEFTSHIFT,
    ecodes.KEY_RIGHTSHIFT,
}
MODIFIER_NAMES = {
    ecodes.KEY_LEFTCTRL: "Ctrl",
    ecodes.KEY_RIGHTCTRL: "Ctrl",
    ecodes.KEY_LEFTALT: "Alt",
    ecodes.KEY_RIGHTALT: "Alt",
    ecodes.KEY_LEFTMETA: "Meta",
    ecodes.KEY_RIGHTMETA: "Meta",
    ecodes.KEY_LEFTSHIFT: "Shift",
    ecodes.KEY_RIGHTSHIFT: "Shift",
}
SHORTCUT_KEY_NAMES = {
    **{getattr(ecodes, f"KEY_F{number}"): f"F{number}" for number in range(1, 13)},
    **{getattr(ecodes, f"KEY_{chr(code)}"): chr(code) for code in range(ord("A"), ord("Z") + 1)},
    ecodes.KEY_1: "1",
    ecodes.KEY_2: "2",
    ecodes.KEY_3: "3",
    ecodes.KEY_4: "4",
    ecodes.KEY_5: "5",
    ecodes.KEY_6: "6",
    ecodes.KEY_7: "7",
    ecodes.KEY_8: "8",
    ecodes.KEY_9: "9",
    ecodes.KEY_0: "0",
    ecodes.KEY_SPACE: "Space",
    ecodes.KEY_TAB: "Tab",
    ecodes.KEY_ENTER: "Enter",
    ecodes.KEY_ESC: "Esc",
    ecodes.KEY_LEFT: "Left",
    ecodes.KEY_RIGHT: "Right",
    ecodes.KEY_UP: "Up",
    ecodes.KEY_DOWN: "Down",
    ecodes.KEY_HOME: "Home",
    ecodes.KEY_END: "End",
    ecodes.KEY_PAGEUP: "PageUp",
    ecodes.KEY_PAGEDOWN: "PageDown",
    ecodes.KEY_INSERT: "Insert",
    ecodes.KEY_DELETE: "Delete",
}
SHORTCUT_KEY_ALIASES = {
    "SPACE": "Space",
    "TAB": "Tab",
    "ENTER": "Enter",
    "RETURN": "Enter",
    "ESC": "Esc",
    "ESCAPE": "Esc",
    "LEFT": "Left",
    "RIGHT": "Right",
    "UP": "Up",
    "DOWN": "Down",
    "HOME": "Home",
    "END": "End",
    "PAGEUP": "PageUp",
    "PAGEDOWN": "PageDown",
    "PGUP": "PageUp",
    "PGDN": "PageDown",
    "INSERT": "Insert",
    "INS": "Insert",
    "DELETE": "Delete",
    "DEL": "Delete",
}
MODIFIER_ALIASES = {
    "CTRL": "Ctrl",
    "CONTROL": "Ctrl",
    "ALT": "Alt",
    "SHIFT": "Shift",
    "META": "Meta",
    "SUPER": "Meta",
}


@dataclass(frozen=True)
class Shortcut:
    modifiers: frozenset[str]
    key: str


def log(message: str) -> None:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {message}\n")
    except OSError:
        return


def parse_shortcut(shortcut: str) -> Shortcut | None:
    parts = [part.strip() for part in shortcut.split("+") if part.strip()]
    if not parts:
        return None
    key = parts[-1].upper()
    key = SHORTCUT_KEY_ALIASES.get(key, key)
    modifiers = []
    for part in parts[:-1]:
        modifier = MODIFIER_ALIASES.get(part.upper())
        if not modifier:
            return None
        modifiers.append(modifier)
    if len(key) == 1 and key.isalpha():
        key = key.upper()
    return Shortcut(frozenset(modifiers), key)


def load_suspend_shortcut() -> Shortcut:
    raw = DEFAULT_SUSPEND_SHORTCUT
    if SETTINGS_FILE.exists():
        try:
            with SETTINGS_FILE.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                raw = str(data.get("suspend_shortcut", raw)).strip() or raw
        except (OSError, json.JSONDecodeError) as exc:
            log(f"could not load suspend shortcut: {exc}")
    return parse_shortcut(raw) or Shortcut(frozenset(), DEFAULT_SUSPEND_SHORTCUT)


def keyboard_devices() -> list[InputDevice]:
    devices: list[InputDevice] = []
    for path in list_devices():
        try:
            device = InputDevice(path)
            capabilities = device.capabilities()
        except PermissionError:
            raise
        except OSError:
            continue
        keys = set(capabilities.get(ecodes.EV_KEY, []))
        if "ydotoold virtual device" in device.name.lower():
            device.close()
            continue
        if ecodes.KEY_A in keys and ecodes.KEY_SPACE in keys:
            devices.append(device)
        else:
            device.close()
    return devices


def run_abort_toggle(socket_path: str | None) -> None:
    env = os.environ.copy()
    if socket_path:
        env["YDOTOOL_SOCKET"] = socket_path
    subprocess.Popen([str(ABORT_CLICK)], start_new_session=True, env=env)


class SuspendListener:
    def __init__(self, socket_path: str | None) -> None:
        self.socket_path = socket_path
        self.modifiers_down: set[int] = set()
        self.shortcut = load_suspend_shortcut()
        self.settings_mtime = SETTINGS_FILE.stat().st_mtime_ns if SETTINGS_FILE.exists() else 0
        self.last_trigger = 0.0
        self.preview_window: dict = {}
        self.preview_process = None

    def handle_preview_key(self, key_code: int, key_value: int) -> None:
        if key_code != ecodes.KEY_SPACE:
            if key_value:
                self.preview_window = {}
            return
        if key_value == 1:
            busy = self.preview_process is not None and self.preview_process.poll() is None
            self.preview_window = eligible_window() if not self.modifiers_down and not busy else {}
        elif key_value == 0:
            expected, self.preview_window = self.preview_window, {}
            if expected and not self.modifiers_down and eligible_window() == expected:
                self.preview_process = subprocess.Popen(
                    [sys.executable, str(SCRIPT_DIR / "input_pilot_dolphin_preview.py"),
                     "--window", json.dumps(expected)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    env=dict(os.environ, YDOTOOL_SOCKET=self.socket_path or DEFAULT_YDOTOOL_SOCKET),
                )

    def stop_preview(self) -> None:
        if self.preview_process is not None and self.preview_process.poll() is None:
            self.preview_process.terminate()

    def refresh_settings(self) -> None:
        mtime = SETTINGS_FILE.stat().st_mtime_ns if SETTINGS_FILE.exists() else 0
        if mtime == self.settings_mtime:
            return
        self.settings_mtime = mtime
        self.shortcut = load_suspend_shortcut()
        label = "+".join([*sorted(self.shortcut.modifiers), self.shortcut.key])
        log(f"loaded suspend shortcut {label}")

    def active_modifiers(self) -> frozenset[str]:
        return frozenset(
            MODIFIER_NAMES[key] for key in self.modifiers_down if key in MODIFIER_NAMES
        )

    def handle_key(self, key_code: int, key_value: int) -> None:
        # A configured Space master key takes precedence over Quick Look.
        if key_code == ecodes.KEY_SPACE or key_value == 1:
            self.refresh_settings()
        if self.shortcut.key != "Space" or self.shortcut.modifiers:
            try:
                self.handle_preview_key(key_code, key_value)
            except OSError as exc:
                log(f"could not start Dolphin preview: {exc}")
        if key_code in MODIFIER_KEYS:
            if key_value:
                self.modifiers_down.add(key_code)
            else:
                self.modifiers_down.discard(key_code)
            return
        if key_value != 1:
            return
        key_name = SHORTCUT_KEY_NAMES.get(key_code)
        if not key_name:
            return
        if key_name != self.shortcut.key or self.active_modifiers() != self.shortcut.modifiers:
            return
        now = time.monotonic()
        if now - self.last_trigger < 0.4:
            return
        self.last_trigger = now
        try:
            run_abort_toggle(self.socket_path)
            log(f"triggered suspend toggle via {key_name}")
        except Exception as exc:  # noqa: BLE001
            log(f"could not trigger suspend toggle: {exc}")


async def watch_device(device: InputDevice, listener: SuspendListener) -> None:
    async for event in device.async_read_loop():
        if event.type != ecodes.EV_KEY:
            continue
        key_event = categorize(event)
        listener.handle_key(key_event.scancode, key_event.keystate)


async def run_listener(socket_path: str | None) -> int:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    listener = SuspendListener(socket_path)
    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, task.cancel)
    try:
        devices = keyboard_devices()
    except PermissionError:
        log("permission denied reading /dev/input; add the user to the input group")
        return 2

    if not devices:
        log("no keyboard input devices found")
        return 1

    log(
        "suspend listener started devices="
        + ",".join(f"{device.name}:{device.path}" for device in devices)
    )
    tasks = [asyncio.create_task(watch_device(device, listener)) for device in devices]
    try:
        await asyncio.gather(*tasks)
    finally:
        listener.stop_preview()
        for task in tasks:
            task.cancel()
        for device in devices:
            device.close()
        PID_FILE.unlink(missing_ok=True)
    return 0


def stop_listener() -> int:
    if not PID_FILE.exists():
        return 0
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        PID_FILE.unlink(missing_ok=True)
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    PID_FILE.unlink(missing_ok=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Input Pilot suspend-key listener")
    parser.add_argument("--stop", action="store_true", help="Stop a running listener")
    parser.add_argument("--ydotool-socket", default=DEFAULT_YDOTOOL_SOCKET)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.stop:
        return stop_listener()
    try:
        return asyncio.run(run_listener(args.ydotool_socket))
    except asyncio.CancelledError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
