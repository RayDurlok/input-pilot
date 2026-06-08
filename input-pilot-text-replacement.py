#!/usr/bin/env python3
"""Low-level text replacement helper for Input Pilot on Wayland."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from evdev import InputDevice, categorize, ecodes, list_devices


CONFIG_FILE = Path.home() / ".config/wayland-automation/text-replacements.json"
MOUSE_CONFIG_FILE = Path.home() / ".config/wayland-automation/mousemove-sequence.json"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
LOG_FILE = STATE_DIR / "wayland-automation/text-replacement.log"
PID_FILE = STATE_DIR / "wayland-automation/text-replacement.pid"
DEFAULT_YDOTOOL_SOCKET = "/tmp/ydotool_socket"
SCRIPT_DIR = Path(__file__).resolve().parent
MOUSE_SEQUENCE_RUNNER = SCRIPT_DIR / "input-pilot-mouse-sequence.py"
MAX_BUFFER = 128
MOUSE_SHORTCUT_SETTLE_SECONDS = 0.08

LETTER_KEYS = {
    ecodes.KEY_A: "a",
    ecodes.KEY_B: "b",
    ecodes.KEY_C: "c",
    ecodes.KEY_D: "d",
    ecodes.KEY_E: "e",
    ecodes.KEY_F: "f",
    ecodes.KEY_G: "g",
    ecodes.KEY_H: "h",
    ecodes.KEY_I: "i",
    ecodes.KEY_J: "j",
    ecodes.KEY_K: "k",
    ecodes.KEY_L: "l",
    ecodes.KEY_M: "m",
    ecodes.KEY_N: "n",
    ecodes.KEY_O: "o",
    ecodes.KEY_P: "p",
    ecodes.KEY_Q: "q",
    ecodes.KEY_R: "r",
    ecodes.KEY_S: "s",
    ecodes.KEY_T: "t",
    ecodes.KEY_U: "u",
    ecodes.KEY_V: "v",
    ecodes.KEY_W: "w",
    ecodes.KEY_X: "x",
    ecodes.KEY_Y: "y",
    ecodes.KEY_Z: "z",
}
CHAR_KEYS = {
    **LETTER_KEYS,
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
    ecodes.KEY_DOT: ".",
    ecodes.KEY_COMMA: ",",
    ecodes.KEY_MINUS: "-",
    ecodes.KEY_SLASH: "/",
    ecodes.KEY_SPACE: " ",
    ecodes.KEY_GRAVE: "^",  # German keyboard: ^ (caret/dead circumflex)
}
SHIFT_CHAR_KEYS = {
    ecodes.KEY_MINUS: "_",
    ecodes.KEY_SLASH: "_",
    ecodes.KEY_GRAVE: "°",  # German: Shift+^ = ° (degree sign)
}
MODIFIER_KEYS = {
    ecodes.KEY_LEFTCTRL,
    ecodes.KEY_RIGHTCTRL,
    ecodes.KEY_LEFTALT,
    ecodes.KEY_RIGHTALT,
    ecodes.KEY_LEFTMETA,
    ecodes.KEY_RIGHTMETA,
}
SHIFT_KEYS = {ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT}
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
    **{code: char.upper() for code, char in LETTER_KEYS.items()},
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
    ecodes.KEY_F1: "F1",
    ecodes.KEY_F2: "F2",
    ecodes.KEY_F3: "F3",
    ecodes.KEY_F4: "F4",
    ecodes.KEY_F5: "F5",
    ecodes.KEY_F6: "F6",
    ecodes.KEY_F7: "F7",
    ecodes.KEY_F8: "F8",
    ecodes.KEY_F9: "F9",
    ecodes.KEY_F10: "F10",
    ecodes.KEY_F11: "F11",
    ecodes.KEY_F12: "F12",
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
class Replacement:
    trigger: str
    replacement: str
    date_format: str | None = None


@dataclass(frozen=True)
class MouseShortcut:
    modifiers: frozenset[str]
    key: str
    index: int
    name: str


DYNAMIC_REPLACEMENTS = [
    Replacement(trigger="dt.", replacement="", date_format="%d.%m.%Y"),
    Replacement(trigger="dt_", replacement="", date_format="%Y_%m_%d"),
    Replacement(trigger="dt-", replacement="", date_format="%Y_%m_%d"),
    Replacement(trigger="dt/", replacement="", date_format="%Y_%m_%d"),
    Replacement(trigger="rnr.", replacement="", date_format="%Y%m%d"),
]


def user_format_to_strftime(fmt: str) -> str:
    fmt = fmt.replace("yyyy", "%Y")
    fmt = fmt.replace("yy", "%y")
    fmt = fmt.replace("mm", "%m")
    fmt = fmt.replace("dd", "%d")
    return fmt


def log(message: str) -> None:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {message}\n")
    except OSError:
        return


def load_replacements() -> list[Replacement]:
    if not CONFIG_FILE.exists():
        return list(DYNAMIC_REPLACEMENTS)
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        log(f"could not load replacements: {exc}")
        return list(DYNAMIC_REPLACEMENTS)
    if not isinstance(data, list):
        return list(DYNAMIC_REPLACEMENTS)

    replacements: list[Replacement] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if item.get("enabled", True) is False:
            continue
        trigger = str(item.get("trigger", "")).strip()
        if not trigger:
            continue
        if "date_format" in item:
            fmt = user_format_to_strftime(str(item["date_format"]))
            replacements.append(Replacement(trigger=trigger, replacement="", date_format=fmt))
        else:
            replacement = str(item.get("replacement", ""))
            if replacement:
                replacements.append(Replacement(trigger=trigger, replacement=replacement))
    configured_triggers = {entry.trigger for entry in replacements}
    replacements.extend(
        dynamic
        for dynamic in DYNAMIC_REPLACEMENTS
        if dynamic.trigger not in configured_triggers
    )
    replacements.sort(key=lambda entry: len(entry.trigger), reverse=True)
    return replacements


def parse_mouse_shortcut(shortcut: str) -> tuple[frozenset[str], str] | None:
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
    return frozenset(modifiers), key


def load_mouse_shortcuts() -> list[MouseShortcut]:
    if not MOUSE_CONFIG_FILE.exists():
        return []
    try:
        with MOUSE_CONFIG_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        log(f"could not load mousemove shortcuts: {exc}")
        return []

    automations = data.get("automations", []) if isinstance(data, dict) else []
    if not isinstance(automations, list):
        return []

    shortcuts = []
    for index, automation in enumerate(automations, start=1):
        if not isinstance(automation, dict):
            continue
        parsed = parse_mouse_shortcut(str(automation.get("shortcut", "")))
        if not parsed:
            continue
        modifiers, key = parsed
        shortcuts.append(
            MouseShortcut(
                modifiers=modifiers,
                key=key,
                index=index,
                name=str(automation.get("name", "")).strip() or f"Automation {index}",
            )
        )
    return shortcuts


def resolve_replacement(replacement: Replacement) -> str:
    if replacement.date_format:
        return datetime.now().strftime(replacement.date_format)
    return replacement.replacement


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


def run_ydotool(arguments: list[str], socket_path: str | None) -> None:
    ydotool = shutil.which("ydotool")
    if not ydotool:
        raise RuntimeError("ydotool is not installed")
    env = os.environ.copy()
    if socket_path:
        env["YDOTOOL_SOCKET"] = socket_path
    subprocess.run([ydotool, *arguments], check=True, env=env)


def _clipboard_paste(text: str, socket_path: str | None) -> None:
    wl_copy = shutil.which("wl-copy")
    if not wl_copy:
        raise RuntimeError("wl-copy is not installed")

    saved: bytes | None = None
    wl_paste = shutil.which("wl-paste")
    if wl_paste:
        try:
            result = subprocess.run(
                [wl_paste, "--no-newline"], capture_output=True, timeout=0.5
            )
            if result.returncode == 0:
                saved = result.stdout
        except subprocess.TimeoutExpired:
            pass

    subprocess.run([wl_copy, "--", text], check=True)
    # Ctrl+V: KEY_LEFTCTRL=29, KEY_V=47
    run_ydotool(["key", "29:1", "47:1", "47:0", "29:0"], socket_path)

    if saved is not None:
        time.sleep(0.15)
        subprocess.run([wl_copy, "--"], input=saved, check=False)


def type_text(text: str, socket_path: str | None) -> None:
    parts = text.split("{enter}")
    for i, part in enumerate(parts):
        if part:
            _clipboard_paste(part, socket_path)
        if i < len(parts) - 1:
            run_ydotool(["key", "42:1", "28:1", "28:0", "42:0"], socket_path)  # Shift+Enter


def run_mouse_automation(shortcut: MouseShortcut, socket_path: str | None) -> None:
    command = [str(MOUSE_SEQUENCE_RUNNER), "--index", str(shortcut.index)]
    if socket_path:
        command.extend(["--ydotool-socket", socket_path])
    subprocess.Popen(command, start_new_session=True)
    log(f"triggered mousemove automation {shortcut.index}: {shortcut.name}")


def inject_replacement(
    trigger: str,
    replacement: str,
    socket_path: str | None,
) -> None:
    for _ in range(len(trigger) + 1):
        run_ydotool(["key", "14:1", "14:0"], socket_path)
    type_text(replacement, socket_path)


class ReplacementEngine:
    def __init__(self, socket_path: str | None) -> None:
        self.socket_path = socket_path
        self.buffer = ""
        self.modifiers_down: set[int] = set()
        self.shift_down: set[int] = set()
        self.replacements = load_replacements()
        self.config_mtime = CONFIG_FILE.stat().st_mtime_ns if CONFIG_FILE.exists() else 0
        self.mouse_shortcuts = load_mouse_shortcuts()
        self.mouse_config_mtime = (
            MOUSE_CONFIG_FILE.stat().st_mtime_ns if MOUSE_CONFIG_FILE.exists() else 0
        )
        self.keys_down: set[int] = set()
        self.pending_mouse_shortcut: MouseShortcut | None = None
        self.last_mouse_trigger: tuple[int, float] | None = None
        self.injecting = False

    def refresh_config(self) -> None:
        mtime = CONFIG_FILE.stat().st_mtime_ns if CONFIG_FILE.exists() else 0
        if mtime == self.config_mtime:
            return
        self.config_mtime = mtime
        self.replacements = load_replacements()
        log(f"loaded {len(self.replacements)} text replacements")

    def refresh_mouse_config(self) -> None:
        mtime = MOUSE_CONFIG_FILE.stat().st_mtime_ns if MOUSE_CONFIG_FILE.exists() else 0
        if mtime == self.mouse_config_mtime:
            return
        self.mouse_config_mtime = mtime
        self.mouse_shortcuts = load_mouse_shortcuts()
        log(f"loaded {len(self.mouse_shortcuts)} mousemove shortcuts")

    def active_modifiers(self) -> frozenset[str]:
        modifiers = {MODIFIER_NAMES[key] for key in self.modifiers_down if key in MODIFIER_NAMES}
        modifiers.update(MODIFIER_NAMES[key] for key in self.shift_down if key in MODIFIER_NAMES)
        return frozenset(modifiers)

    def maybe_trigger_mouse_shortcut(self, key_code: int) -> bool:
        key_name = SHORTCUT_KEY_NAMES.get(key_code)
        if not key_name:
            return False
        self.refresh_mouse_config()
        modifiers = self.active_modifiers()
        for shortcut in self.mouse_shortcuts:
            if shortcut.key == key_name and shortcut.modifiers == modifiers:
                self.pending_mouse_shortcut = shortcut
                log(f"queued mousemove automation {shortcut.index}: {shortcut.name}")
                self.buffer = ""
                return True
        return False

    def flush_pending_mouse_shortcut(self) -> None:
        if (
            self.pending_mouse_shortcut is None
            or self.active_modifiers()
            or self.keys_down
        ):
            return
        shortcut = self.pending_mouse_shortcut
        self.pending_mouse_shortcut = None
        time.sleep(MOUSE_SHORTCUT_SETTLE_SECONDS)

        now = time.monotonic()
        if (
            self.last_mouse_trigger
            and self.last_mouse_trigger[0] == shortcut.index
            and now - self.last_mouse_trigger[1] < 0.5
        ):
            return
        self.last_mouse_trigger = (shortcut.index, now)

        try:
            run_mouse_automation(shortcut, self.socket_path)
        except Exception as exc:  # noqa: BLE001
            log(f"could not trigger mousemove automation {shortcut.name!r}: {exc}")

    def update_buffer(self, key_code: int) -> None:
        char = None
        if self.shift_down:
            char = SHIFT_CHAR_KEYS.get(key_code)
        if char is None:
            char = CHAR_KEYS.get(key_code)
        if char is None:
            if key_code in {ecodes.KEY_BACKSPACE, ecodes.KEY_DELETE}:
                self.buffer = self.buffer[:-1]
            elif key_code in {ecodes.KEY_ENTER, ecodes.KEY_TAB}:
                self.buffer = ""
            return
        self.buffer = (self.buffer + char)[-MAX_BUFFER:]

    def matching_replacement(self) -> Replacement | None:
        if not self.buffer.endswith(" "):
            return None
        text_before_space = self.buffer[:-1]
        for replacement in self.replacements:
            if text_before_space.endswith(replacement.trigger):
                return replacement
        return None

    def handle_key(self, key_code: int, key_value: int) -> None:
        if key_code in MODIFIER_KEYS:
            if key_value:
                self.modifiers_down.add(key_code)
            else:
                self.modifiers_down.discard(key_code)
                self.flush_pending_mouse_shortcut()
            return
        if key_code in SHIFT_KEYS:
            if key_value:
                self.shift_down.add(key_code)
            else:
                self.shift_down.discard(key_code)
                self.flush_pending_mouse_shortcut()
            return

        if key_value == 1:
            self.keys_down.add(key_code)
        elif key_value == 0:
            self.keys_down.discard(key_code)
            self.flush_pending_mouse_shortcut()
            return

        if key_value == 1 and not self.injecting and self.maybe_trigger_mouse_shortcut(key_code):
            return

        if key_value != 1 or self.injecting or self.modifiers_down:
            return

        self.refresh_config()
        self.update_buffer(key_code)
        replacement = self.matching_replacement()
        if not replacement:
            return

        self.injecting = True
        try:
            replacement_text = resolve_replacement(replacement)
            inject_replacement(
                replacement.trigger,
                replacement_text,
                self.socket_path,
            )
            self.buffer = (replacement_text + " ")[-MAX_BUFFER:]
        except Exception as exc:  # noqa: BLE001
            log(f"could not inject replacement {replacement.trigger!r}: {exc}")
        finally:
            self.injecting = False


async def watch_device(device: InputDevice, engine: ReplacementEngine) -> None:
    async for event in device.async_read_loop():
        if event.type != ecodes.EV_KEY:
            continue
        key_event = categorize(event)
        engine.handle_key(key_event.scancode, key_event.keystate)


async def run_engine(socket_path: str | None) -> int:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    engine = ReplacementEngine(socket_path)
    try:
        devices = keyboard_devices()
    except PermissionError:
        log("permission denied reading /dev/input; add the user to the input group or run a privileged service")
        return 2

    if not devices:
        log("no keyboard input devices found")
        return 1

    log(
        "text replacement started devices="
        + ",".join(f"{device.name}:{device.path}" for device in devices)
    )
    tasks = [asyncio.create_task(watch_device(device, engine)) for device in devices]
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        for device in devices:
            device.close()
        PID_FILE.unlink(missing_ok=True)
    return 0


def stop_engine() -> int:
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
    parser = argparse.ArgumentParser(description="Input Pilot text replacement engine")
    parser.add_argument("--stop", action="store_true", help="Stop a running engine")
    parser.add_argument("--ydotool-socket", default=DEFAULT_YDOTOOL_SOCKET)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.stop:
        return stop_engine()
    return asyncio.run(run_engine(args.ydotool_socket))


if __name__ == "__main__":
    raise SystemExit(main())
