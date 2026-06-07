#!/usr/bin/env python3
"""Small KDE tray helper for local Wayland automation actions."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shlex
import signal
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("AppIndicator3", "0.1")
from gi.repository import AppIndicator3, Gdk, Gio, GLib, Gtk  # noqa: E402


APP_ID = "input-pilot"
APP_NAME = "Input Pilot"
DESKTOP_APP_ID = "input-pilot-tray"
SCRIPT_DIR = Path(__file__).resolve().parent
CLICK_IMAGE = SCRIPT_DIR / "wayland-click-image.py"
TEMPLATE_SERVER = SCRIPT_DIR / "input-pilot-template-server.py"
TEXT_REPLACEMENT_ENGINE = SCRIPT_DIR / "input-pilot-text-replacement.py"
MOUSE_SEQUENCE_RUNNER = SCRIPT_DIR / "input-pilot-mouse-sequence.py"
FOLDER_TEMPLATE_RUNNER = SCRIPT_DIR / "input-pilot-folder-template.py"
ABORT_CLICK = SCRIPT_DIR / "abort-click-template.sh"
DEFAULT_TEMPLATE = Path.home() / "Desktop/buttonscreen.png"
DEFAULT_YDOTOOL_SOCKET = "/tmp/ydotool_socket"
CONFIG_FILE = Path.home() / ".config/wayland-automation/shortcuts.json"
TEXT_REPLACEMENTS_FILE = Path.home() / ".config/wayland-automation/text-replacements.json"
MOUSE_SEQUENCE_FILE = Path.home() / ".config/wayland-automation/mousemove-sequence.json"
FOLDER_TEMPLATE_FILE = Path.home() / ".config/wayland-automation/folder-templates.json"
DEFAULT_FOLDER_TEMPLATE = Path.home() / "Templates/Input Pilot Folder Template"
APP_ICON = SCRIPT_DIR / "InputPilotIconRounded.png"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
ACTIVE_WINDOW_FILE = STATE_DIR / "wayland-automation/active-window.json"
CURSOR_POSITION_FILE = STATE_DIR / "wayland-automation/cursor-position.json"
TEXT_REPLACEMENT_PID_FILE = STATE_DIR / "wayland-automation/text-replacement.pid"
TEXT_REPLACEMENT_LOG_FILE = STATE_DIR / "wayland-automation/text-replacement.log"
DEFAULT_DATE_ENTRIES: list[dict[str, object]] = [
    {"trigger": "dt.", "date_format": "dd.mm.yyyy", "enabled": True},
    {"trigger": "dt_", "date_format": "yyyy_mm_dd", "enabled": True},
    {"trigger": "rnr.", "date_format": "yyyymmdd", "enabled": True},
]
AUTOMATION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{5,63}$")
_DATE_FMT_CHARS_RE = re.compile(r'^(?:yyyy|yy|mm|dd|[.\-_/ ])+$')
_DATE_FMT_TOKEN_RE = re.compile(r'yyyy|yy|mm|dd')
PATH_DISPLAY_PARTS = 4
OPEN_CONFIGURED_TARGET = SCRIPT_DIR / "open-configured-target.py"
KWIN_ACTIVE_WINDOW_SCRIPT = SCRIPT_DIR / "kwin-active-window-state.js"
KWIN_ACTIVE_WINDOW_SCRIPT_NAME = "wayland-automation-active-window-state"
DBUS_NAME = "io.inputpilot.Automation"
DBUS_OBJECT = "/io/inputpilot/Automation"
DBUS_INTERFACE = "io.inputpilot.Automation"
FUNCTION_KEYS = [f"F{number}" for number in range(1, 12)]
HOTKEY_KEYS = (
    [f"F{number}" for number in range(1, 13)]
    + [chr(code) for code in range(ord("A"), ord("Z") + 1)]
    + [str(number) for number in range(0, 10)]
    + [
        "Space",
        "Tab",
        "Enter",
        "Esc",
        "Left",
        "Right",
        "Up",
        "Down",
        "Home",
        "End",
        "PageUp",
        "PageDown",
        "Insert",
        "Delete",
    ]
)
EMERGENCY_KEY = "F12"
MODIFIER_OPTIONS = [
    "",
    "Alt",
    "Ctrl",
    "Meta",
    "Shift",
    "Ctrl+Alt",
    "Ctrl+Shift",
    "Alt+Shift",
    "Meta+Alt",
    "Ctrl+Alt+Shift",
]
MODIFIER_CODES = {
    "Alt": 0x08000000,
    "Ctrl": 0x04000000,
    "Meta": 0x10000000,
    "Shift": 0x02000000,
}
DIALOG_MODIFIER = "Shift"
QT_KEY_F1 = 16777264
QT_KEY_HELP = 16777304
QT_KEY_CODES = {
    **{f"F{number}": QT_KEY_F1 + number - 1 for number in range(1, 36)},
    **{chr(code): code for code in range(ord("A"), ord("Z") + 1)},
    **{str(number): ord(str(number)) for number in range(0, 10)},
    "Space": 0x20,
    "Tab": 0x01000001,
    "Enter": 0x01000005,
    "Esc": 0x01000000,
    "Left": 0x01000012,
    "Right": 0x01000014,
    "Up": 0x01000013,
    "Down": 0x01000015,
    "Home": 0x01000010,
    "End": 0x01000011,
    "PageUp": 0x01000016,
    "PageDown": 0x01000017,
    "Insert": 0x01000006,
    "Delete": 0x01000007,
    "Backspace": 0x01000003,
}
PURE_MODIFIER_KEYVALS = {
    "Shift_L",
    "Shift_R",
    "Control_L",
    "Control_R",
    "Alt_L",
    "Alt_R",
    "Meta_L",
    "Meta_R",
    "Super_L",
    "Super_R",
    "Hyper_L",
    "Hyper_R",
    "ISO_Level3_Shift",
}
RECORDER_KEY_NAMES = {
    "space": "Space",
    "Tab": "Tab",
    "Return": "Enter",
    "KP_Enter": "Enter",
    "Escape": "Esc",
    "Left": "Left",
    "Right": "Right",
    "Up": "Up",
    "Down": "Down",
    "Home": "Home",
    "End": "End",
    "Page_Up": "PageUp",
    "Page_Down": "PageDown",
    "Insert": "Insert",
    "Delete": "Delete",
    "BackSpace": "Backspace",
    "KP_0": "0",
    "KP_1": "1",
    "KP_2": "2",
    "KP_3": "3",
    "KP_4": "4",
    "KP_5": "5",
    "KP_6": "6",
    "KP_7": "7",
    "KP_8": "8",
    "KP_9": "9",
    "exclam": "1",
    "onesuperior": "1",
    "quotedbl": "2",
    "at": "2",
    "twosuperior": "2",
    "section": "3",
    "numbersign": "3",
    "threesuperior": "3",
    "dollar": "4",
    "percent": "5",
    "ampersand": "6",
    "slash": "7",
    "braceleft": "7",
    "parenleft": "8",
    "bracketleft": "8",
    "parenright": "9",
    "bracketright": "9",
    "equal": "0",
    "braceright": "0",
}
RECORDER_SUPPORTED_KEYS = (
    set(HOTKEY_KEYS)
    | {f"F{number}" for number in range(1, 13)}
    | {chr(code) for code in range(ord("A"), ord("Z") + 1)}
    | {str(number) for number in range(0, 10)}
    | {"Backspace"}
)


def canonical_shortcut(shortcut: str) -> str:
    parts = [part.strip() for part in shortcut.split("+") if part.strip()]
    if not parts:
        return ""
    key = parts[-1].upper()
    key_names = {
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
        "BACKSPACE": "Backspace",
        "BKSP": "Backspace",
    }
    key = key_names.get(key, key)
    modifier_names = {
        "ALT": "Alt",
        "CTRL": "Ctrl",
        "CONTROL": "Ctrl",
        "META": "Meta",
        "SUPER": "Meta",
        "SHIFT": "Shift",
    }
    modifier_order = {
        "Ctrl": 0,
        "Alt": 1,
        "Shift": 2,
        "Meta": 3,
    }
    modifiers = []
    seen_modifiers = set()
    for part in parts[:-1]:
        modifier = modifier_names.get(part.upper(), part.title())
        if modifier not in MODIFIER_CODES or modifier in seen_modifiers:
            continue
        modifiers.append(modifier)
        seen_modifiers.add(modifier)
    modifiers.sort(key=lambda item: modifier_order.get(item, 99))
    return shortcut_label("+".join(modifiers), key)


def parse_shortcut(shortcut: str) -> tuple[str, str]:
    parts = canonical_shortcut(shortcut).split("+")
    key = parts[-1]
    modifier = "+".join(parts[:-1])
    return modifier, key


def shortcut_label(modifier: str, function_key: str) -> str:
    return f"{modifier}+{function_key}" if modifier else function_key


def modifier_value(modifier: str) -> int:
    value = 0
    for part in modifier.split("+"):
        if part:
            value |= MODIFIER_CODES[part]
    return value


def key_codes_for(modifier: str, function_key: str) -> list[int]:
    if function_key not in QT_KEY_CODES:
        raise ValueError(f"Unsupported hotkey key: {function_key}")
    modifier_code = modifier_value(modifier)
    codes = [modifier_code | QT_KEY_CODES[function_key]]
    if function_key == "F1" and not modifier:
        codes.append(QT_KEY_HELP)
    return codes


def run_detached(command: list[str]) -> None:
    subprocess.Popen(command, start_new_session=True)


def notify(title: str, message: str) -> None:
    if shutil.which("notify-send"):
        run_detached(["notify-send", title, message])


def write_active_window_state(
    is_file_dialog: bool,
    caption: str,
    resource_class: str,
    resource_name: str,
    window_role: str,
    window_type: str,
    window_pid: int = 0,
) -> None:
    ACTIVE_WINDOW_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "is_file_dialog": is_file_dialog,
        "caption": caption,
        "resource_class": resource_class,
        "resource_name": resource_name,
        "window_role": window_role,
        "window_type": window_type,
        "window_pid": window_pid,
        "pid": os.getpid(),
    }
    with ACTIVE_WINDOW_FILE.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def clear_active_window_state() -> None:
    write_active_window_state(False, "", "", "", "", "")


def write_cursor_position(x: int, y: int) -> None:
    CURSOR_POSITION_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "x": x,
        "y": y,
        "pid": os.getpid(),
    }
    with CURSOR_POSITION_FILE.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


class AutomationDBusService:
    introspection = Gio.DBusNodeInfo.new_for_xml(
        f"""
        <node>
          <interface name="{DBUS_INTERFACE}">
            <method name="SetActiveWindow">
              <arg type="b" name="is_file_dialog" direction="in"/>
              <arg type="s" name="caption" direction="in"/>
              <arg type="s" name="resource_class" direction="in"/>
              <arg type="s" name="resource_name" direction="in"/>
              <arg type="s" name="window_role" direction="in"/>
              <arg type="s" name="window_type" direction="in"/>
              <arg type="i" name="window_pid" direction="in"/>
            </method>
            <method name="SetCursorPosition">
              <arg type="i" name="x" direction="in"/>
              <arg type="i" name="y" direction="in"/>
            </method>
          </interface>
        </node>
        """
    )

    def __init__(self) -> None:
        self.connection: Gio.DBusConnection | None = None
        self.registration_id = 0
        self.owner_id = Gio.bus_own_name(
            Gio.BusType.SESSION,
            DBUS_NAME,
            Gio.BusNameOwnerFlags.REPLACE,
            self.on_bus_acquired,
            None,
            None,
        )

    def on_bus_acquired(self, connection: Gio.DBusConnection, _name: str) -> None:
        self.connection = connection
        self.registration_id = connection.register_object(
            DBUS_OBJECT,
            self.introspection.interfaces[0],
            self.handle_method_call,
            None,
            None,
        )

    def handle_method_call(
        self,
        _connection: Gio.DBusConnection,
        _sender: str,
        _object_path: str,
        _interface_name: str,
        method_name: str,
        parameters: GLib.Variant,
        invocation: Gio.DBusMethodInvocation,
    ) -> None:
        if method_name == "SetActiveWindow":
            write_active_window_state(*parameters.unpack())
            invocation.return_value(None)
            return
        if method_name == "SetCursorPosition":
            x, y = parameters.unpack()
            write_cursor_position(x, y)
            invocation.return_value(None)
            return
        invocation.return_dbus_error(
            f"{DBUS_INTERFACE}.Error.UnknownMethod",
            f"Unknown method: {method_name}",
        )

    def shutdown(self) -> None:
        if self.connection and self.registration_id:
            self.connection.unregister_object(self.registration_id)
            self.registration_id = 0
        if self.owner_id:
            Gio.bus_unown_name(self.owner_id)
            self.owner_id = 0


def load_shortcuts() -> dict[str, str]:
    if not CONFIG_FILE.exists():
        return {"F1": str(Path.home() / "Downloads")}
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    shortcuts = {}
    for key, value in data.items():
        shortcut = canonical_shortcut(str(key))
        target = str(value).strip()
        if shortcut and target:
            shortcuts[shortcut] = target
    return shortcuts


def save_shortcuts(shortcuts: dict[str, str]) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    clean = {
        canonical_shortcut(key): value.strip()
        for key, value in shortcuts.items()
        if canonical_shortcut(key) and value.strip()
    }
    with CONFIG_FILE.open("w", encoding="utf-8") as handle:
        json.dump(clean, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _is_date_format(text: str) -> bool:
    return bool(_DATE_FMT_CHARS_RE.fullmatch(text) and _DATE_FMT_TOKEN_RE.search(text))


def load_text_replacements() -> list[dict[str, object]]:
    raw: list[dict[str, object]] = []
    if TEXT_REPLACEMENTS_FILE.exists():
        try:
            with TEXT_REPLACEMENTS_FILE.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            data = []
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                trigger = str(item.get("trigger", "")).strip()
                if not trigger:
                    continue
                if "date_format" in item:
                    raw.append({
                        "trigger": trigger,
                        "date_format": str(item["date_format"]),
                        "enabled": bool(item.get("enabled", True)),
                    })
                else:
                    replacement = str(item.get("replacement", ""))
                    if replacement:
                        raw.append({
                            "trigger": trigger,
                            "replacement": replacement,
                            "enabled": bool(item.get("enabled", True)),
                        })

    loaded_triggers = {str(r["trigger"]) for r in raw}
    result = [dict(e) for e in DEFAULT_DATE_ENTRIES if e["trigger"] not in loaded_triggers]
    result.extend(raw)
    return result


def save_text_replacements(replacements: list[dict[str, object]]) -> None:
    TEXT_REPLACEMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    clean = []
    seen: set[str] = set()
    for item in replacements:
        trigger = str(item.get("trigger", "")).strip()
        if not trigger or trigger in seen:
            continue
        seen.add(trigger)
        if "date_format" in item:
            fmt = str(item["date_format"])
            clean.append({"trigger": trigger, "date_format": fmt, "enabled": bool(item.get("enabled", True))})
        else:
            replacement = str(item.get("replacement", ""))
            if not replacement:
                continue
            if _is_date_format(replacement):
                clean.append({"trigger": trigger, "date_format": replacement, "enabled": bool(item.get("enabled", True))})
            else:
                clean.append({"trigger": trigger, "replacement": replacement, "enabled": bool(item.get("enabled", True))})
    with TEXT_REPLACEMENTS_FILE.open("w", encoding="utf-8") as handle:
        json.dump(clean, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def clean_mouse_steps(data: object) -> list[dict[str, object]]:
    if not isinstance(data, list):
        return []
    steps = []
    for item in data:
        if not isinstance(item, dict):
            continue
        template = str(item.get("template", "")).strip()
        click = str(item.get("click", "left")).strip()
        action = str(item.get("action", "")).strip().lower()
        button = str(item.get("button", "")).strip().lower()
        source_type = str(item.get("source_type", "")).strip().lower()
        target_type = str(item.get("target_type", "")).strip().lower()
        input_type = str(item.get("input_type", "")).strip().lower()
        condition = str(item.get("condition", "")).strip().lower()
        condition_template = str(item.get("condition_template", "")).strip()
        animate_mouse = bool(item.get("animate_mouse", False))
        match_choice = str(item.get("match_choice", "best")).strip().lower()
        keys = str(item.get("keys", "")).strip()
        text = str(item.get("text", ""))
        try:
            indent = int(float(item.get("indent", 0) or 0))
        except (TypeError, ValueError):
            indent = 0
        try:
            x = int(float(item.get("x", 0) or 0))
            y = int(float(item.get("y", 0) or 0))
        except (TypeError, ValueError):
            x = 0
            y = 0
        try:
            source_x = int(float(item.get("source_x", 0) or 0))
            source_y = int(float(item.get("source_y", 0) or 0))
        except (TypeError, ValueError):
            source_x = 0
            source_y = 0
        try:
            wait = float(item.get("wait", 0.0) or 0.0)
        except (TypeError, ValueError):
            wait = 0.0
        try:
            drag_steps = int(float(item.get("drag_steps", 2) or 2))
        except (TypeError, ValueError):
            drag_steps = 2
        if_jump_enabled = bool(item.get("if_jump_enabled", False))
        try:
            if_jump_step = int(float(item.get("if_jump_step", 1) or 1))
        except (TypeError, ValueError):
            if_jump_step = 1
        if not action:
            if click == "hover":
                action = "move"
                target_type = "template"
            elif click in {"left", "right", "double-left"}:
                action = "click"
                button = click
                target_type = "template"
            elif click == "drag":
                action = "drag"
                source_type = "template"
                target_type = "template"
            elif click == "drag-position":
                action = "drag"
                source_type = "template"
                target_type = "position"
            elif click == "position":
                action = "move"
                target_type = "position"
            elif click == "previous-position":
                action = "move"
                target_type = "previous-position"
            elif click == "keys":
                action = "input"
                input_type = "keys"
            elif click == "text":
                action = "input"
                input_type = "text"
        if action not in {"click", "drag", "move", "input", "if"}:
            action = "click"
        if condition == "screenshot-missing":
            condition = "previous-node-failed"
        elif condition == "screenshot-found":
            condition = "previous-node-succeeded"
        if condition not in {"previous-node-failed", "previous-node-succeeded", "always"}:
            condition = "previous-node-failed"
        if button not in {"left", "right", "double-left"}:
            button = "left"
        if source_type not in {"template", "position", "previous-position"}:
            source_type = "template"
        if target_type not in {"template", "position", "previous-position"}:
            target_type = "template" if action in {"click", "drag"} else "position"
        if input_type not in {"keys", "text"}:
            input_type = "keys"
        if match_choice not in {"best", "rightmost", "leftmost", "topmost", "bottommost", "middle"}:
            match_choice = "best"
        if action == "click":
            click = button
        elif action == "drag":
            click = "drag-position" if target_type == "position" else "drag"
        elif action == "move":
            click = "previous-position" if target_type == "previous-position" else "position"
        elif action == "input":
            click = input_type
        elif action == "if":
            click = "if"
        valid_clicks = {
            "left",
            "right",
            "double-left",
            "hover",
            "drag",
            "drag-position",
            "keys",
            "position",
            "previous-position",
            "text",
            "if",
        }
        has_step = False
        if action == "if":
            has_step = True
        elif action == "input":
            has_step = bool(keys) if input_type == "keys" else bool(text)
        elif action == "move":
            has_step = (
                (target_type == "template" and (str(item.get("target", "")).strip() or template))
                or target_type in {"position", "previous-position"}
            )
        elif action == "drag":
            has_source = (
                (source_type == "template" and template)
                or source_type in {"position", "previous-position"}
            )
            has_target = (
                (target_type == "template" and str(item.get("target", "")).strip())
                or target_type in {"position", "previous-position"}
            )
            has_step = has_source and has_target
        elif action == "click":
            has_step = (
                (target_type == "template" and template)
                or target_type in {"position", "previous-position"}
            )
        if (
            has_step
        ):
            steps.append(
                {
                    "template": template,
                    "click": click if click in valid_clicks else "left",
                    "target": str(item.get("target", "")).strip(),
                    "action": action,
                    "button": button,
                    "source_type": source_type,
                    "target_type": target_type,
                    "input_type": input_type,
                    "condition": condition,
                    "condition_template": "",
                    "animate_mouse": animate_mouse and action == "click",
                    "match_choice": match_choice,
                    "keys": keys,
                    "text": text,
                    "indent": max(0, min(indent, 8)),
                    "source_x": max(source_x, 0),
                    "source_y": max(source_y, 0),
                    "x": max(x, 0),
                    "y": max(y, 0),
                    "drag_steps": max(1, min(drag_steps, 200)),
                    "if_jump_enabled": if_jump_enabled and action == "if",
                    "if_jump_step": max(1, min(if_jump_step, 999)),
                    "wait": max(wait, 0.0),
                    "note": str(item.get("note", "")),
                }
            )
    return steps


def compact_path_for_display(path_text: str, max_parts: int = PATH_DISPLAY_PARTS) -> str:
    path_text = str(path_text).strip()
    if not path_text:
        return ""
    path = Path(path_text).expanduser()
    parts = path.parts
    if len(parts) <= max_parts:
        return path_text
    return ".../" + "/".join(parts[-max_parts:])


def set_path_entry_value(entry: Gtk.Entry, path_text: str, compact: bool = True) -> None:
    value = str(path_text).strip()
    setattr(entry, "_input_pilot_full_path", value)
    entry.set_tooltip_text(value or None)
    entry.set_text(compact_path_for_display(value) if compact else value)
    entry.set_position(-1)


def path_entry_value(entry: Gtk.Entry) -> str:
    text = entry.get_text().strip()
    full_path = str(getattr(entry, "_input_pilot_full_path", "") or "").strip()
    if full_path and text in {full_path, compact_path_for_display(full_path)}:
        return full_path
    return text


def clean_automation_id(raw_id: object) -> str:
    candidate = str(raw_id or "").strip().lower()
    return candidate if AUTOMATION_ID_RE.fullmatch(candidate) else ""


def unique_automation_id(raw_id: object, used_ids: set[str]) -> str:
    candidate = clean_automation_id(raw_id)
    if candidate and candidate not in used_ids:
        used_ids.add(candidate)
        return candidate
    while True:
        candidate = f"auto-{uuid.uuid4().hex[:12]}"
        if candidate not in used_ids:
            used_ids.add(candidate)
            return candidate


def load_mouse_config() -> dict[str, object]:
    if not MOUSE_SEQUENCE_FILE.exists():
        return {"automations": []}
    try:
        with MOUSE_SEQUENCE_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"automations": []}
    if isinstance(data, list):
        return {
            "automations": [
                {
                    "name": "Automation 1",
                    "shortcut": "",
                    "steps": clean_mouse_steps(data),
                }
            ]
        }
    if not isinstance(data, dict):
        return {"automations": []}

    if isinstance(data.get("automations"), list):
        automations = data.get("automations", [])
    else:
        automations = [data]

    clean_automations = []
    used_ids: set[str] = set()
    for index, item in enumerate(automations, start=1):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip() or f"Automation {index}"
        shortcut = canonical_shortcut(str(item.get("shortcut", "")))
        clean_automations.append(
            {
                "id": unique_automation_id(item.get("id", ""), used_ids),
                "name": name,
                "shortcut": shortcut,
                "debug": bool(item.get("debug", False)),
                "steps": clean_mouse_steps(item.get("steps", [])),
            }
        )
    return {"automations": clean_automations}


def load_mouse_sequence() -> list[dict[str, object]]:
    automations = load_mouse_config().get("automations", [])
    if isinstance(automations, list) and automations:
        first = automations[0]
        if isinstance(first, dict):
            steps = first.get("steps", [])
            return list(steps) if isinstance(steps, list) else []
    return []


def save_mouse_config(automations: list[dict[str, object]]) -> list[dict[str, object]]:
    MOUSE_SEQUENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    clean_automations = []
    used_names: set[str] = set()
    used_ids: set[str] = set()
    for index, item in enumerate(automations, start=1):
        name = unique_automation_name(
            str(item.get("name", "")),
            used_names,
            f"Automation {index}",
        )
        shortcut = canonical_shortcut(str(item.get("shortcut", "")))
        clean_automations.append(
            {
                "id": unique_automation_id(item.get("id", ""), used_ids),
                "name": name,
                "shortcut": shortcut,
                "debug": bool(item.get("debug", False)),
                "steps": clean_mouse_steps(item.get("steps", [])),
            }
        )
    data = {"automations": clean_automations}
    with MOUSE_SEQUENCE_FILE.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return clean_automations


def unique_automation_name(
    raw_name: str,
    used_names: set[str],
    fallback: str,
) -> str:
    base = raw_name.strip() or fallback
    candidate = base
    counter = 2
    while candidate.casefold() in used_names:
        candidate = f"{base} ({counter})"
        counter += 1
    used_names.add(candidate.casefold())
    return candidate


def default_folder_templates() -> list[dict[str, object]]:
    return [
        {
            "name": "Project Template",
            "shortcut": "Ctrl+N",
            "template": str(DEFAULT_FOLDER_TEMPLATE),
            "default_name": "New Project",
        }
    ]


def clean_folder_templates(data: object) -> list[dict[str, object]]:
    if not isinstance(data, list):
        return default_folder_templates()
    templates = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            continue
        template = str(item.get("template", "")).strip()
        if not template:
            continue
        templates.append(
            {
                "name": str(item.get("name", "")).strip() or f"Template {index}",
                "shortcut": canonical_shortcut(str(item.get("shortcut", ""))),
                "template": template,
                "default_name": str(item.get("default_name", "")).strip()
                or "New Project",
            }
        )
    return templates or default_folder_templates()


def load_folder_templates() -> list[dict[str, object]]:
    if not FOLDER_TEMPLATE_FILE.exists():
        return default_folder_templates()
    try:
        with FOLDER_TEMPLATE_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default_folder_templates()
    return clean_folder_templates(data)


def save_folder_templates(templates: list[dict[str, object]]) -> None:
    FOLDER_TEMPLATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    clean = clean_folder_templates(templates)
    with FOLDER_TEMPLATE_FILE.open("w", encoding="utf-8") as handle:
        json.dump(clean, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def desktop_id_for(shortcut: str) -> str:
    safe = shortcut.lower().replace("+", "-")
    return f"wayland-automation-configured-{safe}.desktop"


def dialog_desktop_id_for(function_key: str) -> str:
    return f"wayland-automation-dialog-{function_key.lower()}.desktop"


def emergency_desktop_id() -> str:
    return "wayland-automation-emergency-f12.desktop"


def mouse_sequence_desktop_id(automation_id: str) -> str:
    safe = clean_automation_id(automation_id) or f"auto-{uuid.uuid4().hex[:12]}"
    return f"input-pilot-automation-{safe}.desktop"


def folder_template_desktop_id(index: int) -> str:
    return f"input-pilot-folder-template-{index}.desktop"


def component_path_for(desktop_id: str) -> str:
    safe = desktop_id.replace(".", "_").replace("-", "_")
    return f"/component/{safe}"


def write_desktop_file(shortcut: str, target: str) -> str:
    desktop_id = desktop_id_for(shortcut)
    desktop_path = Path.home() / ".local/share/applications" / desktop_id
    desktop_path.parent.mkdir(parents=True, exist_ok=True)
    desktop_path.write_text(
        "\n".join(
            [
                "[Desktop Entry]",
                "Type=Application",
                f"Name=Open configured target {shortcut}",
                f"Comment=Open configured Input Pilot target for {shortcut}",
                f"Exec={OPEN_CONFIGURED_TARGET} --auto {shortcut}",
                "Icon=system-run",
                "Terminal=false",
                "NoDisplay=true",
                "StartupNotify=false",
                "Categories=Utility;",
                "X-KDE-GlobalAccel-CommandShortcut=true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    desktop_path.chmod(0o644)
    return desktop_id


def write_dialog_desktop_file(function_key: str, target: str) -> str:
    desktop_id = dialog_desktop_id_for(function_key)
    desktop_path = Path.home() / ".local/share/applications" / desktop_id
    desktop_path.parent.mkdir(parents=True, exist_ok=True)
    desktop_path.write_text(
        "\n".join(
            [
                "[Desktop Entry]",
                "Type=Application",
                f"Name=Use configured folder {function_key} in dialog",
                f"Comment=Use configured Input Pilot folder for {function_key} in a file dialog",
                f"Exec={OPEN_CONFIGURED_TARGET} --dialog {function_key}",
                "Icon=folder-open",
                "Terminal=false",
                "NoDisplay=true",
                "StartupNotify=false",
                "Categories=Utility;",
                "X-KDE-GlobalAccel-CommandShortcut=true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    desktop_path.chmod(0o644)
    return desktop_id


def write_mouse_sequence_desktop_file(automation_id: str, name: str) -> str:
    desktop_id = mouse_sequence_desktop_id(automation_id)
    desktop_path = Path.home() / ".local/share/applications" / desktop_id
    desktop_path.parent.mkdir(parents=True, exist_ok=True)
    command = f"{MOUSE_SEQUENCE_RUNNER} --id {shlex.quote(automation_id)}"
    desktop_path.write_text(
        "\n".join(
            [
                "[Desktop Entry]",
                "Type=Application",
                f"Name=Run Input Pilot automation {name}",
                f"Comment=Run Input Pilot automation {name}",
                f"Exec={command}",
                "Icon=input-mouse",
                "Terminal=false",
                "NoDisplay=true",
                "StartupNotify=false",
                "Categories=Utility;",
                "X-KDE-GlobalAccel-CommandShortcut=true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    desktop_path.chmod(0o644)
    return desktop_id


def write_folder_template_desktop_file(index: int, name: str) -> str:
    desktop_id = folder_template_desktop_id(index)
    desktop_path = Path.home() / ".local/share/applications" / desktop_id
    desktop_path.parent.mkdir(parents=True, exist_ok=True)
    command = f"{FOLDER_TEMPLATE_RUNNER} --index {index}"
    desktop_path.write_text(
        "\n".join(
            [
                "[Desktop Entry]",
                "Type=Application",
                f"Name=Create Input Pilot folder template {name}",
                f"Comment=Create folder from Input Pilot template {name}",
                f"Exec={command}",
                "Icon=folder-new",
                "Terminal=false",
                "NoDisplay=true",
                "StartupNotify=false",
                "Categories=Utility;",
                "X-KDE-GlobalAccel-CommandShortcut=true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    desktop_path.chmod(0o644)
    return desktop_id


def write_emergency_desktop_file() -> str:
    desktop_id = emergency_desktop_id()
    desktop_path = Path.home() / ".local/share/applications" / desktop_id
    desktop_path.parent.mkdir(parents=True, exist_ok=True)
    desktop_path.write_text(
        "\n".join(
            [
                "[Desktop Entry]",
                "Type=Application",
                "Name=Abort Input Pilot automation",
                "Comment=Emergency stop for running Input Pilot actions",
                f"Exec={ABORT_CLICK}",
                "Icon=process-stop",
                "Terminal=false",
                "NoDisplay=true",
                "StartupNotify=false",
                "Categories=Utility;",
                "X-KDE-GlobalAccel-CommandShortcut=true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    desktop_path.chmod(0o644)
    return desktop_id


def run_checked(command: list[str]) -> None:
    subprocess.run(command, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def kwin_scripting_call(*args: str) -> None:
    if not shutil.which("busctl"):
        return
    run_checked(
        [
            "busctl",
            "--user",
            "call",
            "org.kde.KWin",
            "/Scripting",
            "org.kde.kwin.Scripting",
            *args,
        ]
    )


def busctl_text(command: list[str]) -> str:
    if not shutil.which("busctl"):
        return ""
    result = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def configure_ydotool_input_device() -> bool:
    tree = busctl_text(["busctl", "--user", "tree", "org.kde.KWin"])
    paths = sorted(set(re.findall(r"/org/kde/KWin/InputDevice/\S+", tree)))
    configured = False
    for path in paths:
        name_output = busctl_text(
            [
                "busctl",
                "--user",
                "get-property",
                "org.kde.KWin",
                path,
                "org.kde.KWin.InputDevice",
                "name",
            ]
        )
        if "ydotoold virtual device" not in name_output:
            continue
        run_checked(
            [
                "busctl",
                "--user",
                "set-property",
                "org.kde.KWin",
                path,
                "org.kde.KWin.InputDevice",
                "pointerAccelerationProfileFlat",
                "b",
                "true",
            ]
        )
        run_checked(
            [
                "busctl",
                "--user",
                "set-property",
                "org.kde.KWin",
                path,
                "org.kde.KWin.InputDevice",
                "pointerAccelerationProfileAdaptive",
                "b",
                "false",
            ]
        )
        run_checked(
            [
                "busctl",
                "--user",
                "set-property",
                "org.kde.KWin",
                path,
                "org.kde.KWin.InputDevice",
                "pointerAcceleration",
                "d",
                "0",
            ]
        )
        configured = True
    return configured


def load_kwin_active_window_script() -> None:
    if not KWIN_ACTIVE_WINDOW_SCRIPT.exists():
        return
    unload_kwin_active_window_script()
    kwin_scripting_call(
        "loadScript",
        "s",
        str(KWIN_ACTIVE_WINDOW_SCRIPT),
    )
    kwin_scripting_call("start")


def unload_kwin_active_window_script() -> None:
    kwin_scripting_call("unloadScript", "s", str(KWIN_ACTIVE_WINDOW_SCRIPT))
    kwin_scripting_call("unloadScript", "s", KWIN_ACTIVE_WINDOW_SCRIPT_NAME)
    clear_active_window_state()


def register_shortcut(shortcut: str, target: str) -> None:
    modifier, function_key = parse_shortcut(shortcut)
    desktop_id = write_desktop_file(shortcut, target)
    name = f"Open configured target {shortcut}"
    codes = key_codes_for(modifier, function_key)

    if shutil.which("kbuildsycoca6"):
        run_checked(["kbuildsycoca6"])

    if shutil.which("kwriteconfig6"):
        run_checked(
            [
                "kwriteconfig6",
                "--file",
                str(Path.home() / ".config/kglobalshortcutsrc"),
                "--group",
                "services",
                "--group",
                desktop_id,
                "--key",
                "_launch",
                f"{shortcut},{shortcut},{name}",
            ]
        )

    if shutil.which("busctl"):
        run_checked(
            [
                "busctl",
                "--user",
                "call",
                "org.kde.kglobalaccel",
                "/kglobalaccel",
                "org.kde.KGlobalAccel",
                "doRegister",
                "as",
                "4",
                desktop_id,
                "_launch",
                name,
                name,
            ]
        )
        run_checked(
            [
                "busctl",
                "--user",
                "call",
                "org.kde.kglobalaccel",
                "/kglobalaccel",
                "org.kde.KGlobalAccel",
                "setShortcut",
                "asaiu",
                "4",
                desktop_id,
                "_launch",
                name,
                name,
                str(len(codes)),
                *[str(code) for code in codes],
                "6",
            ]
        )


def register_dialog_shortcut(function_key: str, target: str) -> None:
    desktop_id = write_dialog_desktop_file(function_key, target)
    shortcut = shortcut_label(DIALOG_MODIFIER, function_key)
    name = f"Use configured folder {function_key} in dialog"
    codes = key_codes_for(DIALOG_MODIFIER, function_key)

    if shutil.which("kbuildsycoca6"):
        run_checked(["kbuildsycoca6"])

    if shutil.which("kwriteconfig6"):
        run_checked(
            [
                "kwriteconfig6",
                "--file",
                str(Path.home() / ".config/kglobalshortcutsrc"),
                "--group",
                "services",
                "--group",
                desktop_id,
                "--key",
                "_launch",
                f"{shortcut},{shortcut},{name}",
            ]
        )

    if shutil.which("busctl"):
        run_checked(
            [
                "busctl",
                "--user",
                "call",
                "org.kde.kglobalaccel",
                "/kglobalaccel",
                "org.kde.KGlobalAccel",
                "doRegister",
                "as",
                "4",
                desktop_id,
                "_launch",
                name,
                name,
            ]
        )
        run_checked(
            [
                "busctl",
                "--user",
                "call",
                "org.kde.kglobalaccel",
                "/kglobalaccel",
                "org.kde.KGlobalAccel",
                "setShortcut",
                "asaiu",
                "4",
                desktop_id,
                "_launch",
                name,
                name,
                str(len(codes)),
                *[str(code) for code in codes],
                "6",
            ]
        )


def register_emergency_shortcut() -> None:
    desktop_id = write_emergency_desktop_file()
    name = "Abort Input Pilot template click"
    codes = key_codes_for("", EMERGENCY_KEY)

    if shutil.which("kbuildsycoca6"):
        run_checked(["kbuildsycoca6"])

    if shutil.which("kwriteconfig6"):
        run_checked(
            [
                "kwriteconfig6",
                "--file",
                str(Path.home() / ".config/kglobalshortcutsrc"),
                "--group",
                "services",
                "--group",
                desktop_id,
                "--key",
                "_launch",
                f"{EMERGENCY_KEY},{EMERGENCY_KEY},{name}",
            ]
        )

    if shutil.which("busctl"):
        run_checked(
            [
                "busctl",
                "--user",
                "call",
                "org.kde.kglobalaccel",
                "/kglobalaccel",
                "org.kde.KGlobalAccel",
                "doRegister",
                "as",
                "4",
                desktop_id,
                "_launch",
                name,
                name,
            ]
        )
        run_checked(
            [
                "busctl",
                "--user",
                "call",
                "org.kde.kglobalaccel",
                "/kglobalaccel",
                "org.kde.KGlobalAccel",
                "setShortcut",
                "asaiu",
                "4",
                desktop_id,
                "_launch",
                name,
                name,
                str(len(codes)),
                *[str(code) for code in codes],
                "6",
            ]
        )


def register_mouse_sequence_shortcut(index: int, automation: dict[str, object]) -> None:
    shortcut = str(automation.get("shortcut", ""))
    name = str(automation.get("name", "")).strip() or f"Automation {index}"
    automation_id = clean_automation_id(automation.get("id", ""))
    if not automation_id:
        automation_id = f"auto-{index}"
    shortcut = canonical_shortcut(shortcut)
    if not shortcut:
        return
    modifier, function_key = parse_shortcut(shortcut)
    desktop_id = write_mouse_sequence_desktop_file(automation_id, name)
    shortcut_name = f"Run Input Pilot automation {name}"
    codes = key_codes_for(modifier, function_key)

    if shutil.which("kbuildsycoca6"):
        run_checked(["kbuildsycoca6"])

    if shutil.which("kwriteconfig6"):
        run_checked(
            [
                "kwriteconfig6",
                "--file",
                str(Path.home() / ".config/kglobalshortcutsrc"),
                "--group",
                "services",
                "--group",
                desktop_id,
                "--key",
                "_launch",
                f"{shortcut},{shortcut},{shortcut_name}",
            ]
        )

    if shutil.which("busctl"):
        run_checked(
            [
                "busctl",
                "--user",
                "call",
                "org.kde.kglobalaccel",
                "/kglobalaccel",
                "org.kde.KGlobalAccel",
                "doRegister",
                "as",
                "4",
                desktop_id,
                "_launch",
                shortcut_name,
                shortcut_name,
            ]
        )
        run_checked(
            [
                "busctl",
                "--user",
                "call",
                "org.kde.kglobalaccel",
                "/kglobalaccel",
                "org.kde.KGlobalAccel",
                "setShortcut",
                "asaiu",
                "4",
                desktop_id,
                "_launch",
                shortcut_name,
                shortcut_name,
                str(len(codes)),
                *[str(code) for code in codes],
                "6",
            ]
        )


def register_mouse_sequence_shortcuts(automations: list[dict[str, object]]) -> None:
    unregister_mouse_sequence_shortcuts()
    for index, automation in enumerate(automations, start=1):
        if isinstance(automation, dict):
            register_mouse_sequence_shortcut(index, automation)


def register_folder_template_shortcut(index: int, template: dict[str, object]) -> None:
    shortcut = canonical_shortcut(str(template.get("shortcut", "")))
    if not shortcut:
        return
    name = str(template.get("name", "")).strip() or f"Template {index}"
    modifier, key = parse_shortcut(shortcut)
    desktop_id = write_folder_template_desktop_file(index, name)
    shortcut_name = f"Create Input Pilot folder template {name}"
    codes = key_codes_for(modifier, key)

    if shutil.which("kbuildsycoca6"):
        run_checked(["kbuildsycoca6"])

    if shutil.which("kwriteconfig6"):
        run_checked(
            [
                "kwriteconfig6",
                "--file",
                str(Path.home() / ".config/kglobalshortcutsrc"),
                "--group",
                "services",
                "--group",
                desktop_id,
                "--key",
                "_launch",
                f"{shortcut},{shortcut},{shortcut_name}",
            ]
        )

    if shutil.which("busctl"):
        run_checked(
            [
                "busctl",
                "--user",
                "call",
                "org.kde.kglobalaccel",
                "/kglobalaccel",
                "org.kde.KGlobalAccel",
                "doRegister",
                "as",
                "4",
                desktop_id,
                "_launch",
                shortcut_name,
                shortcut_name,
            ]
        )
        run_checked(
            [
                "busctl",
                "--user",
                "call",
                "org.kde.kglobalaccel",
                "/kglobalaccel",
                "org.kde.KGlobalAccel",
                "setShortcut",
                "asaiu",
                "4",
                desktop_id,
                "_launch",
                shortcut_name,
                shortcut_name,
                str(len(codes)),
                *[str(code) for code in codes],
                "6",
            ]
        )


def register_folder_template_shortcuts(templates: list[dict[str, object]]) -> None:
    unregister_folder_template_shortcuts()
    for index, template in enumerate(templates, start=1):
        if isinstance(template, dict):
            register_folder_template_shortcut(index, template)


def unregister_shortcut(shortcut: str) -> None:
    desktop_id = desktop_id_for(shortcut)
    desktop_path = Path.home() / ".local/share/applications" / desktop_id
    if shutil.which("busctl"):
        run_checked(
            [
                "busctl",
                "--user",
                "call",
                "org.kde.kglobalaccel",
                "/kglobalaccel",
                "org.kde.KGlobalAccel",
                "unregister",
                "ss",
                desktop_id,
                "_launch",
            ]
        )
    if shutil.which("kwriteconfig6"):
        run_checked(
            [
                "kwriteconfig6",
                "--file",
                str(Path.home() / ".config/kglobalshortcutsrc"),
                "--group",
                "services",
                "--group",
                desktop_id,
                "--key",
                "_launch",
                "--delete",
                "",
            ]
        )
    desktop_path.unlink(missing_ok=True)


def unregister_mouse_sequence_desktop_id(desktop_id: str) -> None:
    desktop_path = Path.home() / ".local/share/applications" / desktop_id
    if shutil.which("busctl"):
        run_checked(
            [
                "busctl",
                "--user",
                "call",
                "org.kde.kglobalaccel",
                "/kglobalaccel",
                "org.kde.KGlobalAccel",
                "unregister",
                "ss",
                desktop_id,
                "_launch",
            ]
        )
    if shutil.which("kwriteconfig6"):
        run_checked(
            [
                "kwriteconfig6",
                "--file",
                str(Path.home() / ".config/kglobalshortcutsrc"),
                "--group",
                "services",
                "--group",
                desktop_id,
                "--key",
                "_launch",
                "--delete",
                "",
            ]
        )
    desktop_path.unlink(missing_ok=True)


def unregister_folder_template_desktop_id(desktop_id: str) -> None:
    desktop_path = Path.home() / ".local/share/applications" / desktop_id
    if shutil.which("busctl"):
        run_checked(
            [
                "busctl",
                "--user",
                "call",
                "org.kde.kglobalaccel",
                "/kglobalaccel",
                "org.kde.KGlobalAccel",
                "unregister",
                "ss",
                desktop_id,
                "_launch",
            ]
        )
    if shutil.which("kwriteconfig6"):
        run_checked(
            [
                "kwriteconfig6",
                "--file",
                str(Path.home() / ".config/kglobalshortcutsrc"),
                "--group",
                "services",
                "--group",
                desktop_id,
                "--key",
                "_launch",
                "--delete",
                "",
            ]
        )
    desktop_path.unlink(missing_ok=True)


def unregister_mouse_sequence_shortcuts() -> None:
    applications_dir = Path.home() / ".local/share/applications"
    desktop_ids = {"wayland-automation-mouse-sequence.desktop"}
    desktop_ids.update(
        path.name
        for path in applications_dir.glob("wayland-automation-mouse-sequence-*.desktop")
    )
    desktop_ids.update(
        path.name
        for path in applications_dir.glob("input-pilot-automation-*.desktop")
    )
    for desktop_id in desktop_ids:
        unregister_mouse_sequence_desktop_id(desktop_id)


def unregister_folder_template_shortcuts() -> None:
    applications_dir = Path.home() / ".local/share/applications"
    desktop_ids = {
        path.name for path in applications_dir.glob("input-pilot-folder-template-*.desktop")
    }
    for desktop_id in desktop_ids:
        unregister_folder_template_desktop_id(desktop_id)


def unregister_dialog_shortcut(function_key: str) -> None:
    desktop_id = dialog_desktop_id_for(function_key)
    desktop_path = Path.home() / ".local/share/applications" / desktop_id
    if shutil.which("busctl"):
        run_checked(
            [
                "busctl",
                "--user",
                "call",
                "org.kde.kglobalaccel",
                "/kglobalaccel",
                "org.kde.KGlobalAccel",
                "unregister",
                "ss",
                desktop_id,
                "_launch",
            ]
        )
    if shutil.which("kwriteconfig6"):
        run_checked(
            [
                "kwriteconfig6",
                "--file",
                str(Path.home() / ".config/kglobalshortcutsrc"),
                "--group",
                "services",
                "--group",
                desktop_id,
                "--key",
                "_launch",
                "--delete",
                "",
            ]
        )
    desktop_path.unlink(missing_ok=True)


def unregister_emergency_shortcut() -> None:
    desktop_id = emergency_desktop_id()
    desktop_path = Path.home() / ".local/share/applications" / desktop_id
    if shutil.which("busctl"):
        run_checked(
            [
                "busctl",
                "--user",
                "call",
                "org.kde.kglobalaccel",
                "/kglobalaccel",
                "org.kde.KGlobalAccel",
                "unregister",
                "ss",
                desktop_id,
                "_launch",
            ]
        )
    if shutil.which("kwriteconfig6"):
        run_checked(
            [
                "kwriteconfig6",
                "--file",
                str(Path.home() / ".config/kglobalshortcutsrc"),
                "--group",
                "services",
                "--group",
                desktop_id,
                "--key",
                "_launch",
                "--delete",
                "",
            ]
        )
    desktop_path.unlink(missing_ok=True)


def disable_legacy_shortcuts() -> None:
    legacy_desktop_ids = [
        "wayland-automation-open-downloads.desktop",
    ]
    for desktop_id in legacy_desktop_ids:
        if shutil.which("busctl"):
            run_checked(
                [
                    "busctl",
                    "--user",
                    "call",
                    "org.kde.kglobalaccel",
                    "/kglobalaccel",
                    "org.kde.KGlobalAccel",
                    "unregister",
                    "ss",
                    desktop_id,
                    "_launch",
                ]
            )


def apply_shortcuts(shortcuts: dict[str, str]) -> None:
    disable_legacy_shortcuts()
    register_emergency_shortcut()
    unregister_mouse_sequence_shortcuts()
    mouse_automations = load_mouse_config().get("automations", [])
    register_mouse_sequence_shortcuts(mouse_automations if isinstance(mouse_automations, list) else [])
    register_folder_template_shortcuts(load_folder_templates())

    for shortcut, target in shortcuts.items():
        target = target.strip()
        if target:
            register_shortcut(shortcut, target)

    for modifier in MODIFIER_OPTIONS:
        for function_key in FUNCTION_KEYS:
            shortcut = shortcut_label(modifier, function_key)
            if shortcut not in shortcuts:
                unregister_shortcut(shortcut)

    for function_key in FUNCTION_KEYS:
        target = shortcuts.get(function_key, "").strip()
        dialog_shortcut = shortcut_label(DIALOG_MODIFIER, function_key)
        if target and Path(target).expanduser().is_dir() and dialog_shortcut not in shortcuts:
            register_dialog_shortcut(function_key, str(Path(target).expanduser()))
        else:
            unregister_dialog_shortcut(function_key)


def unregister_configured_shortcuts(shortcuts: dict[str, str]) -> None:
    for shortcut in shortcuts:
        unregister_shortcut(shortcut)


def deactivate_shortcuts() -> None:
    disable_legacy_shortcuts()
    unregister_emergency_shortcut()
    unregister_mouse_sequence_shortcuts()
    unregister_folder_template_shortcuts()
    unregister_configured_shortcuts(load_shortcuts())
    for modifier in MODIFIER_OPTIONS:
        for function_key in FUNCTION_KEYS:
            unregister_shortcut(shortcut_label(modifier, function_key))
    for function_key in FUNCTION_KEYS:
        unregister_dialog_shortcut(function_key)


def check_ydotool(socket: str | None = None) -> str:
    ydotool = shutil.which("ydotool")
    if not ydotool:
        return "ydotool ist nicht installiert."

    socket = socket or os.environ.get("YDOTOOL_SOCKET")
    command = [ydotool, "debug"]
    env = os.environ.copy()
    if socket:
        env["YDOTOOL_SOCKET"] = socket

    try:
        result = subprocess.run(
            command,
            env=env,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=2,
        )
    except subprocess.TimeoutExpired:
        return "ydotool antwortet nicht innerhalb von 2 Sekunden."

    if result.returncode == 0:
        return "ydotool ist erreichbar."
    return result.stdout.strip() or "ydotool ist aktuell nicht erreichbar."


def text_replacement_running() -> bool:
    if not TEXT_REPLACEMENT_PID_FILE.exists():
        return False
    try:
        pid = int(TEXT_REPLACEMENT_PID_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def start_text_replacement_engine(socket: str | None = None) -> None:
    if (
        not TEXT_REPLACEMENT_ENGINE.exists()
        or text_replacement_running()
    ):
        return
    command = [str(TEXT_REPLACEMENT_ENGINE)]
    if socket:
        command.extend(["--ydotool-socket", socket])
    run_detached(command)


def stop_text_replacement_engine() -> None:
    if TEXT_REPLACEMENT_ENGINE.exists():
        run_checked([str(TEXT_REPLACEMENT_ENGINE), "--stop"])


def text_replacement_status() -> str:
    if text_replacement_running():
        return "Textreplacement läuft."
    if TEXT_REPLACEMENT_LOG_FILE.exists():
        try:
            lines = TEXT_REPLACEMENT_LOG_FILE.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        if lines:
            return lines[-1]
    return "Textreplacement läuft nicht."


def make_item(label: str, callback) -> Gtk.MenuItem:
    item = Gtk.MenuItem(label=label)
    item.connect("activate", callback)
    item.show()
    return item


def apply_window_icon() -> None:
    GLib.set_prgname(DESKTOP_APP_ID)
    try:
        Gdk.set_program_class(DESKTOP_APP_ID)
    except AttributeError:
        pass
    if not APP_ICON.is_file():
        return
    try:
        Gtk.Window.set_default_icon_from_file(str(APP_ICON))
    except GLib.Error:
        pass


def apply_indicator_icon(indicator) -> None:
    indicator.set_icon_full("preferences-desktop-keyboard", APP_NAME)


class AutomationTray:
    def __init__(self, template: Path, ydotool_socket: str | None) -> None:
        self.template = template
        self.ydotool_socket = ydotool_socket
        clear_active_window_state()
        self.dbus_service = AutomationDBusService()
        self.indicator = AppIndicator3.Indicator.new(
            APP_ID,
            "preferences-desktop-keyboard",
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_title(APP_NAME)
        apply_indicator_icon(self.indicator)
        self.indicator.set_label("IP", "IP")
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_menu(self.build_menu())
        GLib.timeout_add_seconds(1, self.activate_shortcuts)
        GLib.timeout_add_seconds(1, self.activate_window_detection)
        GLib.timeout_add_seconds(1, self.activate_ydotool_device_tuning)
        GLib.timeout_add_seconds(1, self.warm_template_server)
        GLib.timeout_add_seconds(1, self.activate_text_replacement)

    def activate_shortcuts(self) -> bool:
        apply_shortcuts(load_shortcuts())
        return False

    def activate_window_detection(self) -> bool:
        load_kwin_active_window_script()
        return False

    def activate_ydotool_device_tuning(self) -> bool:
        configure_ydotool_input_device()
        return False

    def warm_template_server(self) -> bool:
        if TEMPLATE_SERVER.exists():
            run_detached([str(TEMPLATE_SERVER), "--warmup"])
        return False

    def activate_text_replacement(self) -> bool:
        start_text_replacement_engine(self.ydotool_socket)
        return False

    def build_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()

        menu.append(make_item("Hotkeys...", self.show_configuration))
        menu.append(make_item("Textreplacement...", self.show_text_replacement))
        menu.append(make_item("Input Automations...", self.show_mousemove_config))
        menu.append(make_item("Folder Templates...", self.show_folder_templates))

        separator = Gtk.SeparatorMenuItem()
        separator.show()
        menu.append(separator)

        menu.append(make_item("Beenden", self.quit))
        menu.show()
        return menu

    def click_template(self, _item: Gtk.MenuItem) -> None:
        if not self.template.exists():
            notify(
                APP_NAME,
                f"Template fehlt: {self.template}",
            )
            return
        command = [str(TEMPLATE_SERVER), str(self.template), "--double-click"]
        if self.ydotool_socket:
            command.extend(["--ydotool-socket", self.ydotool_socket])
        run_detached(command)

    def show_ydotool_status(self, _item: Gtk.MenuItem) -> None:
        notify(APP_NAME, check_ydotool(self.ydotool_socket))

    def show_mousemove_config(self, _item: Gtk.MenuItem) -> None:
        config = load_mouse_config()
        automations = config.get("automations", [])
        dialog = MousemoveConfigDialog(automations if isinstance(automations, list) else [])
        while True:
            response = dialog.run()
            if response not in {Gtk.ResponseType.OK, Gtk.ResponseType.APPLY}:
                break
            automations = dialog.automations()
            automations = save_mouse_config(automations)
            dialog.set_automations(automations)
            register_mouse_sequence_shortcuts(automations)
            notify(
                APP_NAME,
                f"{len(automations)} Input-Automationen gespeichert. Trigger laufen über Input Pilot.",
            )
            if response == Gtk.ResponseType.APPLY:
                command = [str(MOUSE_SEQUENCE_RUNNER), "--id", dialog.selected_id()]
                if self.ydotool_socket:
                    command.extend(["--ydotool-socket", self.ydotool_socket])
                run_detached(command)
        dialog.destroy()

    def show_folder_templates(self, _item: Gtk.MenuItem) -> None:
        dialog = FolderTemplateDialog(load_folder_templates())
        while True:
            response = dialog.run()
            if response not in {Gtk.ResponseType.OK, Gtk.ResponseType.APPLY}:
                break
            templates = dialog.templates()
            save_folder_templates(templates)
            register_folder_template_shortcuts(templates)
            notify(APP_NAME, f"{len(templates)} Folder Templates gespeichert.")
            if response == Gtk.ResponseType.APPLY:
                command = [str(FOLDER_TEMPLATE_RUNNER), "--index", str(dialog.selected_index())]
                run_detached(command)
        dialog.destroy()

    def show_text_replacement(self, _item: Gtk.MenuItem) -> None:
        dialog = TextReplacementDialog(load_text_replacements())
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            replacements = dialog.replacements()
            save_text_replacements(replacements)
            stop_text_replacement_engine()
            start_text_replacement_engine(self.ydotool_socket)
            notify(
                APP_NAME,
                f"{len(replacements)} Textreplacement-Einträge gespeichert. "
                f"{text_replacement_status()}",
            )
        dialog.destroy()

    def show_configuration(self, _item: Gtk.MenuItem) -> None:
        previous_shortcuts = load_shortcuts()
        dialog = ShortcutConfigDialog(previous_shortcuts)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            shortcuts = dialog.shortcuts()
            unregister_configured_shortcuts(previous_shortcuts)
            save_shortcuts(shortcuts)
            apply_shortcuts(shortcuts)
            notify(APP_NAME, "Shortcuts gespeichert.")
        dialog.destroy()

    def quit(self, _item: Gtk.MenuItem) -> None:
        deactivate_shortcuts()
        unload_kwin_active_window_script()
        if TEMPLATE_SERVER.exists():
            run_detached([str(TEMPLATE_SERVER), "--stop"])
        stop_text_replacement_engine()
        self.dbus_service.shutdown()
        Gtk.main_quit()


class MousemoveConfigDialog(Gtk.Dialog):
    MAX_BLOCK_INDENT = 8
    ROW_DND_TARGETS = [
        Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0)
    ]
    PATH_DND_TARGETS = [
        Gtk.TargetEntry.new("text/uri-list", 0, 0),
        Gtk.TargetEntry.new("text/plain", 0, 1),
    ]
    SIDEBAR_DND_TARGETS = [
        Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 1)
    ]
    CLICK_OPTIONS = [
        ("left", "Left click"),
        ("right", "Right click"),
        ("double-left", "Double left click"),
        ("drag", "Drag to template"),
        ("drag-position", "Drag to mouse position"),
        ("keys", "Key combo"),
        ("text", "Input string"),
        ("position", "Mouse position"),
        ("previous-position", "Previous mouse position"),
    ]
    ACTION_OPTIONS = [
        ("click", "Click"),
        ("drag", "Drag"),
        ("move", "Move mouse"),
        ("input", "Input"),
        ("if", "If"),
    ]
    BUTTON_OPTIONS = [
        ("left", "Left click"),
        ("right", "Right click"),
        ("double-left", "Double left click"),
    ]
    SOURCE_OPTIONS = [
        ("template", "Screenshot"),
        ("position", "X/Y position"),
        ("previous-position", "Previous mouse position"),
    ]
    TARGET_OPTIONS = [
        ("template", "Screenshot"),
        ("position", "X/Y position"),
        ("previous-position", "Previous mouse position"),
    ]
    INPUT_OPTIONS = [
        ("keys", "Key combo"),
        ("text", "Input string"),
    ]
    CONDITION_OPTIONS = [
        ("previous-node-failed", "Previous node failed"),
        ("previous-node-succeeded", "Previous node succeeded"),
        ("always", "Always"),
    ]
    MATCH_OPTIONS = [
        ("best", "Best"),
        ("rightmost", "Rightmost"),
        ("middle", "Middle"),
        ("leftmost", "Leftmost"),
        ("topmost", "Topmost"),
        ("bottommost", "Bottommost"),
    ]

    def __init__(self, automations: list[dict[str, object]]) -> None:
        super().__init__(title="Input Automations")
        self.set_default_size(1400, 680)
        self.set_border_width(0)
        self.install_css()
        self.automation_state = self.normalize_automations(automations)
        self.current_index = 0
        self.loading = False
        self.rows: list[dict[str, Gtk.Widget]] = []
        self.widget_rows: dict[int, dict[str, Gtk.Widget]] = {}
        self.selected_row: dict[str, Gtk.Widget] | None = None
        self.drag_source_index: int | None = None
        self.drop_index: int | None = None
        self.sidebar_drag_source_index: int | None = None
        action_area = self.get_action_area()
        action_area.set_no_show_all(True)
        action_area.hide()

        content = self.get_content_area()
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content.add(root)

        # ── Main split: sidebar + detail ──────────────────────────
        main_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        root.pack_start(main_hbox, True, True, 0)

        # ── Sidebar ───────────────────────────────────────────────
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sidebar_box.set_name("input-pilot-sidebar")
        sidebar_box.set_size_request(210, -1)

        sidebar_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        sidebar_header.set_border_width(8)
        sidebar_title = Gtk.Label(label="Automations")
        sidebar_title.set_xalign(0)
        sidebar_header.pack_start(sidebar_title, True, True, 0)
        collapse_btn = Gtk.Button()
        collapse_btn.add(Gtk.Image.new_from_icon_name("pan-start-symbolic", Gtk.IconSize.BUTTON))
        collapse_btn.set_relief(Gtk.ReliefStyle.NONE)
        collapse_btn.set_tooltip_text("Collapse sidebar")
        collapse_btn.connect("clicked", self.collapse_sidebar)
        sidebar_header.pack_start(collapse_btn, False, False, 0)
        sidebar_box.pack_start(sidebar_header, False, False, 0)
        sidebar_box.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0
        )

        sidebar_scroller = Gtk.ScrolledWindow()
        sidebar_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroller.set_vexpand(True)
        self.sidebar_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.sidebar_drop_indicator = Gtk.Box()
        self.sidebar_drop_indicator.set_size_request(-1, 3)
        self.sidebar_drop_indicator.set_name("input-pilot-drop-indicator")
        self.sidebar_drop_indicator.set_no_show_all(True)
        self.sidebar_list_box.pack_start(self.sidebar_drop_indicator, False, False, 0)
        self.sidebar_drop_indicator.hide()
        self.sidebar_row_events: list[Gtk.EventBox] = []
        self.sidebar_drop_index: int | None = None
        sidebar_scroller.add(self.sidebar_list_box)
        sidebar_box.pack_start(sidebar_scroller, True, True, 0)

        sidebar_box.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0
        )
        sidebar_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        sidebar_actions.set_border_width(8)
        add_automation_button = Gtk.Button()
        add_automation_button.add(Gtk.Image.new_from_icon_name("list-add-symbolic", Gtk.IconSize.BUTTON))
        add_automation_button.set_tooltip_text("Add automation")
        add_automation_button.connect("clicked", self.add_automation)
        sidebar_actions.pack_start(add_automation_button, True, True, 0)
        remove_automation_button = Gtk.Button()
        remove_automation_button.add(Gtk.Image.new_from_icon_name("list-remove-symbolic", Gtk.IconSize.BUTTON))
        remove_automation_button.set_tooltip_text("Remove automation")
        remove_automation_button.connect("clicked", self.remove_automation)
        sidebar_actions.pack_start(remove_automation_button, True, True, 0)
        duplicate_automation_button = Gtk.Button()
        duplicate_automation_button.add(Gtk.Image.new_from_icon_name("edit-copy-symbolic", Gtk.IconSize.BUTTON))
        duplicate_automation_button.set_tooltip_text("Duplicate automation")
        duplicate_automation_button.connect("clicked", self.duplicate_automation)
        sidebar_actions.pack_start(duplicate_automation_button, True, True, 0)
        sidebar_box.pack_start(sidebar_actions, False, False, 0)

        self.sidebar_revealer = Gtk.Revealer()
        self.sidebar_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_RIGHT)
        self.sidebar_revealer.set_transition_duration(150)
        self.sidebar_revealer.set_reveal_child(True)
        self.sidebar_revealer.add(sidebar_box)
        main_hbox.pack_start(self.sidebar_revealer, False, False, 0)

        self.sidebar_sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        main_hbox.pack_start(self.sidebar_sep, False, False, 0)

        # ── Detail panel ──────────────────────────────────────────
        detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        detail_box.set_border_width(10)
        main_hbox.pack_start(detail_box, True, True, 0)

        name_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        detail_box.pack_start(name_row, False, False, 0)

        self.expand_btn = Gtk.Button()
        self.expand_btn.add(Gtk.Image.new_from_icon_name("pan-end-symbolic", Gtk.IconSize.BUTTON))
        self.expand_btn.set_relief(Gtk.ReliefStyle.NONE)
        self.expand_btn.set_tooltip_text("Expand sidebar")
        self.expand_btn.connect("clicked", self.expand_sidebar)
        self.expand_btn.set_no_show_all(True)
        self.expand_btn.hide()
        name_row.pack_start(self.expand_btn, False, False, 0)

        self.name_entry = Gtk.Entry()
        self.name_entry.set_placeholder_text("Name")
        self.name_entry.connect("changed", self.on_name_changed)
        name_row.pack_start(self.name_entry, True, True, 0)

        trigger_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        detail_box.pack_start(trigger_row, False, False, 0)

        trigger_label = Gtk.Label(label="Trigger")
        trigger_label.set_xalign(0)
        trigger_row.pack_start(trigger_label, False, False, 0)

        self.modifier_combo = Gtk.ComboBoxText()
        for modifier_option in MODIFIER_OPTIONS:
            self.modifier_combo.append_text(modifier_option or "—")
        trigger_row.pack_start(self.modifier_combo, False, False, 0)

        self.key_combo = Gtk.ComboBoxText()
        self.key_combo.append_text("—")
        for key in HOTKEY_KEYS:
            self.key_combo.append_text(key)
        trigger_row.pack_start(self.key_combo, False, False, 0)

        copy_command_btn = Gtk.Button(label="Copy trigger command")
        copy_command_btn.connect("clicked", self.on_copy_command)
        trigger_row.pack_start(copy_command_btn, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        detail_box.pack_start(scroller, True, True, 0)

        self.rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.rows_box.set_border_width(2)
        self.rows_box.drag_dest_set(
            Gtk.DestDefaults.ALL,
            self.ROW_DND_TARGETS,
            Gdk.DragAction.MOVE,
        )
        self.rows_box.connect("drag-motion", self.on_rows_box_drag_motion)
        self.rows_box.connect("drag-leave", self.on_row_drag_leave)
        self.rows_box.connect("drag-data-received", self.on_rows_box_drag_data_received)
        scroller.add(self.rows_box)

        self.drop_indicator = Gtk.Box()
        self.drop_indicator.set_size_request(-1, 3)
        self.drop_indicator.set_name("input-pilot-drop-indicator")
        self.drop_indicator.set_no_show_all(True)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        for label, width in (
            ("", 63),
            ("Action", 170),
            ("Details", 720),
            ("Wait/Sleep", 120),
            ("", 36),
        ):
            header_label = Gtk.Label(label=label)
            header_label.set_xalign(0)
            header_label.set_size_request(width, -1)
            header.pack_start(header_label, label == "Details", label == "Details", 0)
        self.rows_box.pack_start(header, False, False, 0)
        self.rows_box.pack_start(self.drop_indicator, False, False, 0)
        self.drop_indicator.hide()

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        detail_box.pack_start(footer, False, False, 0)

        self.debug_check = Gtk.CheckButton(label="Debug")
        self.debug_check.set_tooltip_text("Show helpful notifications while running this automation")
        footer.pack_start(self.debug_check, False, False, 0)

        footer.pack_start(Gtk.Box(), True, True, 0)

        cancel_button = Gtk.Button(label="Cancel")
        cancel_button.connect("clicked", lambda _button: self.response(Gtk.ResponseType.CANCEL))
        footer.pack_start(cancel_button, False, False, 0)

        run_button = Gtk.Button(label="Run")
        run_button.connect("clicked", lambda _button: self.response(Gtk.ResponseType.APPLY))
        footer.pack_start(run_button, False, False, 0)

        save_button = Gtk.Button(label="Save")
        save_button.connect("clicked", lambda _button: self.response(Gtk.ResponseType.OK))
        footer.pack_start(save_button, False, False, 0)

        add_button = Gtk.Button(label="Add node")
        add_button.connect("clicked", self.add_row)
        footer.pack_start(add_button, False, False, 0)

        self.refresh_sidebar(0)
        self.load_automation(0)
        self.show_all()

    def install_css(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(
            b"""
            #input-pilot-drop-indicator {
                background: #5aa9ff;
                border-radius: 2px;
            }
            .input-pilot-grip {
                border: none;
                padding: 0;
                opacity: 0.72;
            }
            .input-pilot-grip:hover {
                opacity: 1.0;
            }
            .input-pilot-row-number {
                opacity: 0.72;
            }
            #input-pilot-sidebar {
                background-color: @theme_base_color;
            }
            .input-pilot-sidebar-row {
                padding: 0;
            }
            .input-pilot-sidebar-row-selected {
                background-color: @theme_selected_bg_color;
                color: @theme_selected_fg_color;
            }
            .input-pilot-node-card {
                background-color: @theme_base_color;
                border-radius: 6px;
                border: 1px solid alpha(@borders, 0.6);
                padding: 4px 6px;
                margin: 1px 4px;
            }
            .input-pilot-row-number {
                padding: 0 2px;
                min-width: 0;
            }
            .input-pilot-note-active {
                color: @theme_selected_bg_color;
            }
            .input-pilot-if-block-bar {
                background-color: @theme_selected_bg_color;
                border-radius: 2px;
                margin: 2px 0;
            }
            .input-pilot-animate-toggle {
                padding: 0;
                min-width: 0;
                background: transparent;
                border: none;
                box-shadow: none;
            }
            .input-pilot-animate-toggle image {
                color: alpha(@theme_fg_color, 0.25);
            }
            .input-pilot-animate-toggle:checked image {
                color: @theme_selected_bg_color;
            }
            """
        )
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def normalize_automations(
        self,
        automations: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        normalized = []
        used_names: set[str] = set()
        used_ids: set[str] = set()
        for index, automation in enumerate(automations, start=1):
            if not isinstance(automation, dict):
                continue
            name = unique_automation_name(
                str(automation.get("name", "")),
                used_names,
                f"Automation {index}",
            )
            normalized.append(
                {
                    "id": unique_automation_id(automation.get("id", ""), used_ids),
                    "name": name,
                    "shortcut": canonical_shortcut(str(automation.get("shortcut", ""))),
                    "debug": bool(automation.get("debug", False)),
                    "steps": clean_mouse_steps(automation.get("steps", [])),
                }
            )
        if not normalized:
            normalized.append(
                {
                    "id": unique_automation_id("", used_ids),
                    "name": "Automation 1",
                    "shortcut": "",
                    "debug": False,
                    "steps": [],
                }
            )
        return normalized

    def refresh_sidebar(self, active_index: int) -> None:
        self.loading = True
        for child in list(self.sidebar_row_events):
            self.sidebar_list_box.remove(child)
        self.sidebar_row_events = []
        for automation in self.automation_state:
            row_event = Gtk.EventBox()
            row_event.set_visible_window(True)
            row_event.get_style_context().add_class("input-pilot-sidebar-row")
            row_event.drag_dest_set(
                Gtk.DestDefaults.ALL, self.SIDEBAR_DND_TARGETS, Gdk.DragAction.MOVE
            )

            row_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            row_hbox.set_border_width(5)
            row_event.add(row_hbox)

            grip_event = Gtk.EventBox()
            grip_event.set_visible_window(True)
            grip_event.set_above_child(True)
            grip_event.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
            grip_label = Gtk.Label(label="⠿")
            grip_label.get_style_context().add_class("input-pilot-grip")
            grip_label.set_tooltip_text("Drag to reorder")
            grip_event.add(grip_label)
            grip_event.drag_source_set(
                Gdk.ModifierType.BUTTON1_MASK, self.SIDEBAR_DND_TARGETS, Gdk.DragAction.MOVE
            )
            grip_event.connect("enter-notify-event", self.on_handle_enter)
            grip_event.connect("leave-notify-event", self.on_handle_leave)
            grip_event.connect("button-press-event", lambda _w, _e: True)
            row_hbox.pack_start(grip_event, False, False, 0)

            name_label = Gtk.Label(label=str(automation.get("name", "Automation")))
            name_label.set_xalign(0)
            row_hbox.pack_start(name_label, True, True, 0)

            self.sidebar_list_box.pack_start(row_event, False, False, 0)
            self.sidebar_row_events.append(row_event)

            grip_event.connect("drag-data-get", self.on_sidebar_drag_data_get, row_event)
            grip_event.connect("drag-begin", self.on_sidebar_drag_begin, row_event)
            grip_event.connect("drag-end", self.on_sidebar_drag_end)
            row_event.connect("drag-motion", self.on_sidebar_row_drag_motion)
            row_event.connect("drag-leave", self.on_sidebar_drag_leave)
            row_event.connect("drag-data-received", self.on_sidebar_row_drag_received)
            row_event.connect("button-press-event", self.on_sidebar_row_clicked)

        self.sidebar_list_box.show_all()
        self.sidebar_drop_indicator.hide()
        self.loading = False
        target = max(0, min(active_index, len(self.automation_state) - 1))
        self.current_index = target
        self.update_sidebar_selection()

    def update_sidebar_selection(self) -> None:
        for i, row_event in enumerate(self.sidebar_row_events):
            ctx = row_event.get_style_context()
            if i == self.current_index:
                ctx.add_class("input-pilot-sidebar-row-selected")
            else:
                ctx.remove_class("input-pilot-sidebar-row-selected")

    def on_sidebar_row_clicked(self, widget: Gtk.EventBox, event: Gdk.EventButton) -> bool:
        if event.button != 1:
            return False
        if widget not in self.sidebar_row_events:
            return False
        new_index = self.sidebar_row_events.index(widget)
        if new_index == self.current_index:
            return False
        self.save_current_automation()
        self.load_automation(new_index)
        return False

    def on_name_changed(self, entry: Gtk.Entry) -> None:
        if self.loading:
            return
        if not 0 <= self.current_index < len(self.sidebar_row_events):
            return
        row_event = self.sidebar_row_events[self.current_index]
        row_hbox = row_event.get_child()
        if not isinstance(row_hbox, Gtk.Box):
            return
        for child in row_hbox.get_children():
            if isinstance(child, Gtk.Label):
                child.set_text(entry.get_text() or f"Automation {self.current_index + 1}")
                break
    def on_copy_command(self, _button: Gtk.Button) -> None:
        self.save_current_automation()
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        command = (
            f"{shlex.quote(str(MOUSE_SEQUENCE_RUNNER))} "
            f"--id {shlex.quote(self.selected_id())}"
        )
        clipboard.set_text(command, -1)

    def collapse_sidebar(self, _button: Gtk.Button) -> None:
        self.sidebar_revealer.set_reveal_child(False)
        self.sidebar_sep.hide()
        self.expand_btn.show()

    def expand_sidebar(self, _button: Gtk.Button) -> None:
        self.sidebar_revealer.set_reveal_child(True)
        self.sidebar_sep.show()
        self.expand_btn.hide()

    def show_sidebar_drop_indicator(self, index: int) -> None:
        self.sidebar_drop_index = max(0, min(index, len(self.sidebar_row_events)))
        self.sidebar_list_box.reorder_child(self.sidebar_drop_indicator, self.sidebar_drop_index)
        self.sidebar_drop_indicator.show()

    def hide_sidebar_drop_indicator(self) -> None:
        self.sidebar_drop_indicator.hide()
        self.sidebar_drop_index = None

    def sidebar_insertion_index_for_y(self, y: int) -> int:
        for i, row_event in enumerate(self.sidebar_row_events):
            alloc = row_event.get_allocation()
            if y < alloc.y + alloc.height / 2:
                return i
        return len(self.sidebar_row_events)

    def sync_sidebar_row_order(self) -> None:
        self.sidebar_list_box.reorder_child(self.sidebar_drop_indicator, 0)
        for i, row_event in enumerate(self.sidebar_row_events):
            self.sidebar_list_box.reorder_child(row_event, i + 1)

    def on_sidebar_drag_data_get(
        self, _widget, _context, data, _info: int, _time: int, row_event: Gtk.EventBox
    ) -> None:
        if row_event in self.sidebar_row_events:
            data.set_text(str(self.sidebar_row_events.index(row_event)), -1)

    def on_sidebar_drag_begin(self, _widget, _context, row_event: Gtk.EventBox) -> None:
        if row_event not in self.sidebar_row_events:
            return
        self.sidebar_drag_source_index = self.sidebar_row_events.index(row_event)
        row_event.set_opacity(0.18)
        self.show_sidebar_drop_indicator(self.sidebar_drag_source_index)

    def on_sidebar_drag_end(self, _widget, _context) -> None:
        for row_event in self.sidebar_row_events:
            row_event.set_opacity(1.0)
        self.sidebar_drag_source_index = None
        self.hide_sidebar_drop_indicator()
        self.sync_sidebar_row_order()

    def on_sidebar_row_drag_motion(
        self, widget: Gtk.EventBox, context, _x: int, y: int, time_: int
    ) -> bool:
        target_index = self.sidebar_insertion_index_for_y(widget.get_allocation().y + y)
        self.show_sidebar_drop_indicator(target_index)
        Gdk.drag_status(context, Gdk.DragAction.MOVE, time_)
        return True

    def on_sidebar_drag_leave(self, _widget, _context, _time: int) -> None:
        return

    def on_sidebar_row_drag_received(
        self, widget: Gtk.EventBox, context, _x: int, y: int, data, _info: int, time_: int
    ) -> None:
        try:
            source_index = int(data.get_text() or "-1")
        except (TypeError, ValueError):
            Gtk.drag_finish(context, False, False, time_)
            return
        if not 0 <= source_index < len(self.automation_state):
            Gtk.drag_finish(context, False, False, time_)
            return
        target_index = self.sidebar_drop_index
        if target_index is None:
            target_index = self.sidebar_insertion_index_for_y(widget.get_allocation().y + y)
        self.move_sidebar_automation(source_index, target_index)
        Gtk.drag_finish(context, True, False, time_)

    def move_sidebar_automation(self, source_index: int, target_index: int) -> None:
        if source_index == target_index:
            return
        # Save current state directly — avoid refresh_sidebar which rebuilds sidebar_row_events
        if self.automation_state:
            used_names = {
                str(item.get("name", "")).casefold()
                for index, item in enumerate(self.automation_state)
                if index != self.current_index and isinstance(item, dict)
            }
            name = unique_automation_name(
                self.name_entry.get_text(),
                used_names,
                f"Automation {self.current_index + 1}",
            )
            if self.name_entry.get_text().strip() != name:
                self.name_entry.set_text(name)
            automation_id = unique_automation_id(
                self.automation_state[self.current_index].get("id", ""),
                {
                    str(item.get("id", ""))
                    for index, item in enumerate(self.automation_state)
                    if index != self.current_index and isinstance(item, dict)
                },
            )
            self.automation_state[self.current_index] = {
                "id": automation_id,
                "name": name,
                "shortcut": self.shortcut(),
                "debug": self.debug_check.get_active(),
                "steps": self.steps(),
            }
        item = self.automation_state.pop(source_index)
        row_event = self.sidebar_row_events.pop(source_index)
        if source_index < target_index:
            target_index -= 1
        self.automation_state.insert(target_index, item)
        self.sidebar_row_events.insert(target_index, row_event)
        self.sync_sidebar_row_order()
        self.load_automation(target_index)

    def clear_step_rows(self) -> None:
        for row in list(self.rows):
            widget = row["row"]
            self.rows_box.remove(widget)
        self.rows = []
        self.widget_rows = {}
        self.selected_row = None

    def load_automation(self, index: int) -> None:
        self.current_index = max(0, min(index, len(self.automation_state) - 1))
        automation = self.automation_state[self.current_index]
        self.name_entry.set_text(str(automation.get("name", "")))

        shortcut = str(automation.get("shortcut", ""))
        modifier, key = parse_shortcut(shortcut) if shortcut else ("", "")
        self.modifier_combo.set_active(
            MODIFIER_OPTIONS.index(modifier) if modifier in MODIFIER_OPTIONS else 0
        )
        self.key_combo.set_active(HOTKEY_KEYS.index(key) + 1 if key in HOTKEY_KEYS else 0)
        self.debug_check.set_active(bool(automation.get("debug", False)))

        self.clear_step_rows()
        steps = automation.get("steps", [])
        if isinstance(steps, list):
            for step in steps:
                if isinstance(step, dict):
                    self.add_row_values(
                        str(step.get("template", "")),
                        str(step.get("target", "")),
                        str(step.get("click", "left")),
                        str(step.get("keys", "")),
                        str(step.get("text", "")),
                        int(float(step.get("x", 0) or 0)),
                        int(float(step.get("y", 0) or 0)),
                        float(step.get("wait", 0.0) or 0.0),
                        str(step.get("action", "")),
                        str(step.get("button", "")),
                        str(step.get("source_type", "")),
                        str(step.get("target_type", "")),
                        str(step.get("input_type", "")),
                        int(float(step.get("source_x", 0) or 0)),
                        int(float(step.get("source_y", 0) or 0)),
                        int(float(step.get("drag_steps", 2) or 2)),
                        str(step.get("note", "")),
                        int(float(step.get("indent", 0) or 0)),
                        str(step.get("condition", "")),
                        str(step.get("condition_template", "")),
                        bool(step.get("animate_mouse", False)),
                        str(step.get("match_choice", "best")),
                        bool(step.get("if_jump_enabled", False)),
                        int(float(step.get("if_jump_step", 1) or 1)),
                    )
        if not self.rows:
            self.add_row_values("", "", "left", "", "", 0, 0, 0.0)
        self.update_row_numbers()
        self.update_sidebar_selection()

    def save_current_automation(self) -> None:
        if not self.automation_state:
            return
        used_names = {
            str(item.get("name", "")).casefold()
            for index, item in enumerate(self.automation_state)
            if index != self.current_index and isinstance(item, dict)
        }
        name = unique_automation_name(
            self.name_entry.get_text(),
            used_names,
            f"Automation {self.current_index + 1}",
        )
        if self.name_entry.get_text().strip() != name:
            self.name_entry.set_text(name)
        automation_id = unique_automation_id(
            self.automation_state[self.current_index].get("id", ""),
            {
                str(item.get("id", ""))
                for index, item in enumerate(self.automation_state)
                if index != self.current_index and isinstance(item, dict)
            },
        )
        self.automation_state[self.current_index] = {
            "id": automation_id,
            "name": name,
            "shortcut": self.shortcut(),
            "debug": self.debug_check.get_active(),
            "steps": self.steps(),
        }
        if 0 <= self.current_index < len(self.sidebar_row_events):
            row_event = self.sidebar_row_events[self.current_index]
            row_hbox = row_event.get_child()
            if isinstance(row_hbox, Gtk.Box):
                for child in row_hbox.get_children():
                    if isinstance(child, Gtk.Label):
                        child.set_text(name)
                        break

    def add_automation(self, _button: Gtk.Button) -> None:
        self.save_current_automation()
        used_names = {
            str(item.get("name", "")).casefold()
            for item in self.automation_state
            if isinstance(item, dict)
        }
        name = unique_automation_name(
            f"Automation {len(self.automation_state) + 1}",
            used_names,
            f"Automation {len(self.automation_state) + 1}",
        )
        self.automation_state.append(
            {
                "id": unique_automation_id(
                    "",
                    {
                        str(item.get("id", ""))
                        for item in self.automation_state
                        if isinstance(item, dict)
                    },
                ),
                "name": name,
                "shortcut": "",
                "debug": False,
                "steps": [],
            }
        )
        self.refresh_sidebar(len(self.automation_state) - 1)
        self.load_automation(len(self.automation_state) - 1)
        self.name_entry.grab_focus()

    def remove_automation(self, _button: Gtk.Button) -> None:
        name = self.automation_state[self.current_index].get("name", "this automation")
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text=f"Remove \"{name}\"?",
        )
        dialog.format_secondary_text("This automation will be permanently deleted.")
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Remove", Gtk.ResponseType.OK)
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        if len(self.automation_state) <= 1:
            self.automation_state = [
                {
                    "id": unique_automation_id("", set()),
                    "name": "Automation 1",
                    "shortcut": "",
                    "debug": False,
                    "steps": [],
                }
            ]
            self.refresh_sidebar(0)
            self.load_automation(0)
            return
        self.automation_state.pop(self.current_index)
        next_index = min(self.current_index, len(self.automation_state) - 1)
        self.refresh_sidebar(next_index)
        self.load_automation(next_index)

    def duplicate_automation(self, _button: Gtk.Button) -> None:
        self.save_current_automation()
        source = self.automation_state[self.current_index]
        duplicate = copy.deepcopy(source)
        used_names = {
            str(item.get("name", "")).casefold()
            for item in self.automation_state
            if isinstance(item, dict)
        }
        duplicate["name"] = unique_automation_name(
            f"{source.get('name', 'Automation')} (Copy)",
            used_names,
            "Automation Copy",
        )
        duplicate["id"] = unique_automation_id(
            "",
            {
                str(item.get("id", ""))
                for item in self.automation_state
                if isinstance(item, dict)
            },
        )
        duplicate["shortcut"] = ""
        self.automation_state.append(duplicate)
        self.refresh_sidebar(len(self.automation_state) - 1)
        self.load_automation(len(self.automation_state) - 1)
        self.name_entry.grab_focus()

    def selected_index(self) -> int:
        return self.current_index + 1

    def selected_id(self) -> str:
        if 0 <= self.current_index < len(self.automation_state):
            automation_id = clean_automation_id(
                self.automation_state[self.current_index].get("id", "")
            )
            if automation_id:
                return automation_id
        return f"auto-{self.current_index + 1}"

    def set_automations(self, automations: list[dict[str, object]]) -> None:
        active_id = self.selected_id()
        self.automation_state = self.normalize_automations(automations)
        fallback_index = min(self.current_index, len(self.automation_state) - 1)
        active_index = next(
            (
                index
                for index, item in enumerate(self.automation_state)
                if clean_automation_id(item.get("id", "")) == active_id
            ),
            fallback_index,
        )
        self.refresh_sidebar(active_index)
        self.load_automation(active_index)

    def shortcut(self) -> str:
        key_index = self.key_combo.get_active()
        if key_index <= 0:
            return ""
        modifier_index = self.modifier_combo.get_active()
        modifier = MODIFIER_OPTIONS[modifier_index] if modifier_index >= 0 else ""
        key = HOTKEY_KEYS[key_index - 1]
        return shortcut_label(modifier, key)

    def add_row_values(
        self,
        template: str,
        target: str,
        click: str,
        keys: str,
        text: str,
        x: int,
        y: int,
        wait: float,
        action: str = "",
        button: str = "",
        source_type: str = "",
        target_type: str = "",
        input_type: str = "",
        source_x: int = 0,
        source_y: int = 0,
        drag_steps: int = 2,
        note: str = "",
        indent: int = 0,
        condition: str = "",
        condition_template: str = "",
        animate_mouse: bool = False,
        match_choice: str = "best",
        if_jump_enabled: bool = False,
        if_jump_step: int = 1,
    ) -> None:
        action = action.strip().lower()
        button = button.strip().lower()
        source_type = source_type.strip().lower()
        target_type = target_type.strip().lower()
        input_type = input_type.strip().lower()
        condition = condition.strip().lower()
        condition_template = condition_template.strip()
        match_choice = match_choice.strip().lower()
        if condition == "screenshot-missing":
            condition = "previous-node-failed"
        elif condition == "screenshot-found":
            condition = "previous-node-succeeded"
        if not action:
            if click == "hover":
                action = "move"
                target_type = "template"
            elif click in {"left", "right", "double-left"}:
                action = "click"
                button = click
                target_type = "template"
            elif click == "drag":
                action = "drag"
                source_type = "template"
                target_type = "template"
            elif click == "drag-position":
                action = "drag"
                source_type = "template"
                target_type = "position"
            elif click == "position":
                action = "move"
                target_type = "position"
            elif click == "previous-position":
                action = "move"
                target_type = "previous-position"
            elif click == "text":
                action = "input"
                input_type = "text"
            elif click == "keys":
                action = "input"
                input_type = "keys"
        if action not in {value for value, _label in self.ACTION_OPTIONS}:
            action = "click"
        if button not in {value for value, _label in self.BUTTON_OPTIONS}:
            button = "left"
        if source_type not in {value for value, _label in self.SOURCE_OPTIONS}:
            source_type = "template"
        if target_type not in {value for value, _label in self.TARGET_OPTIONS}:
            target_type = "template" if action in {"click", "drag"} else "position"
        if input_type not in {value for value, _label in self.INPUT_OPTIONS}:
            input_type = "keys"
        if condition not in {value for value, _label in self.CONDITION_OPTIONS}:
            condition = "previous-node-failed"
        if match_choice not in {value for value, _label in self.MATCH_OPTIONS}:
            match_choice = "best"
        indent = max(0, min(int(indent or 0), self.MAX_BLOCK_INDENT))
        drag_steps = max(1, min(int(drag_steps or 2), 200))
        if_jump_step = max(1, min(int(if_jump_step or 1), 999))
        target_template = target
        if action in {"click", "move"} and target_type == "template" and not target_template:
            target_template = template

        row_event = Gtk.EventBox()
        row_event.set_visible_window(False)
        row_event.drag_dest_set(
            Gtk.DestDefaults.ALL,
            self.ROW_DND_TARGETS,
            Gdk.DragAction.MOVE,
        )

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.get_style_context().add_class("input-pilot-node-card")
        if indent:
            row.set_margin_left(28 * indent)
        row_event.add(row)

        reorder_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        reorder_box.set_size_request(63, -1)
        handle_event = Gtk.EventBox()
        handle_event.set_visible_window(True)
        handle_event.set_above_child(True)
        handle_event.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        handle_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        handle_box.set_size_request(17, -1)
        handle_box.get_style_context().add_class("input-pilot-grip")
        handle_icon = Gtk.Label(label="⠿")
        handle_icon.set_xalign(0.5)
        handle_icon.set_yalign(0.5)
        handle_box.pack_start(handle_icon, True, True, 0)
        handle_box.set_tooltip_text("Drag to reorder node")
        handle_event.add(handle_box)
        handle_event.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK,
            self.ROW_DND_TARGETS,
            Gdk.DragAction.MOVE,
        )
        handle_event.connect("enter-notify-event", self.on_handle_enter)
        handle_event.connect("leave-notify-event", self.on_handle_leave)
        reorder_box.pack_start(handle_event, False, False, 0)

        note_buffer = Gtk.TextBuffer()
        note_buffer.set_text(note)
        number_button = Gtk.Button(label="")
        number_button.set_relief(Gtk.ReliefStyle.NONE)
        number_button.set_size_request(28, -1)
        number_button.get_style_context().add_class("input-pilot-row-number")
        reorder_box.pack_start(number_button, False, False, 0)
        row.pack_start(reorder_box, False, False, 0)

        block_bar = Gtk.Box()
        block_bar.set_size_request(4, -1)
        block_bar.set_no_show_all(True)
        block_bar.get_style_context().add_class("input-pilot-if-block-bar")
        row.pack_start(block_bar, False, False, 0)
        if indent:
            block_bar.show()

        animate_mouse_check = Gtk.ToggleButton()
        animate_mouse_check.set_image(
            Gtk.Image.new_from_icon_name("pointer-symbolic", Gtk.IconSize.BUTTON)
        )
        animate_mouse_check.set_always_show_image(True)
        animate_mouse_check.set_active(bool(animate_mouse))
        animate_mouse_check.set_tooltip_text("Move the pointer smoothly")
        animate_mouse_check.set_relief(Gtk.ReliefStyle.NONE)
        animate_mouse_check.set_size_request(28, -1)
        animate_mouse_check.set_no_show_all(True)
        animate_mouse_check.get_style_context().add_class("input-pilot-animate-toggle")
        row.pack_start(animate_mouse_check, False, False, 0)

        action_combo = Gtk.ComboBoxText()
        for value, label in self.ACTION_OPTIONS:
            action_combo.append(value, label)
        action_combo.set_active_id(action)
        action_combo.set_size_request(170, -1)
        row.pack_start(action_combo, False, False, 0)

        details_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        details_box.set_hexpand(True)
        row.pack_start(details_box, True, True, 0)

        condition_slot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        condition_slot.set_hexpand(True)
        condition_slot.set_no_show_all(True)
        details_box.pack_start(condition_slot, True, True, 0)

        condition_combo = Gtk.ComboBoxText()
        for value, label in self.CONDITION_OPTIONS:
            condition_combo.append(value, label)
        condition_combo.set_active_id(condition)
        condition_combo.set_size_request(220, -1)
        condition_combo.set_no_show_all(True)
        condition_slot.pack_start(condition_combo, False, False, 0)

        if_jump_combo = Gtk.ComboBoxText()
        if_jump_combo.append("next", "Next node")
        if_jump_combo.append("step", "Run block, then jump to step")
        if_jump_combo.set_active_id("step" if if_jump_enabled else "next")
        if_jump_combo.set_size_request(210, -1)
        if_jump_combo.set_tooltip_text("What to do after this If block finishes")
        if_jump_combo.set_no_show_all(True)
        condition_slot.pack_start(if_jump_combo, False, False, 0)

        if_jump_spin = Gtk.SpinButton.new_with_range(1, 999, 1)
        if_jump_spin.set_value(if_jump_step)
        if_jump_spin.set_size_request(72, -1)
        if_jump_spin.set_tooltip_text("Step number to continue with after the If block")
        if_jump_spin.set_no_show_all(True)
        if_jump_spin.connect("focus-in-event", self.select_row_by_widget)
        condition_slot.pack_start(if_jump_spin, False, False, 0)

        condition_entry = Gtk.Entry()
        condition_entry.set_text(condition_template)
        condition_entry.set_placeholder_text("")
        condition_entry.set_hexpand(True)
        condition_entry.set_no_show_all(True)
        condition_entry.connect("focus-in-event", self.select_row_by_widget)

        condition_button = Gtk.Button(label="...")
        condition_button.set_no_show_all(True)
        condition_button.connect("clicked", self.choose_template, condition_entry)

        source_slot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        source_slot.set_hexpand(True)
        source_slot.set_no_show_all(True)
        details_box.pack_start(source_slot, True, True, 0)

        button_combo = Gtk.ComboBoxText()
        for value, label in self.BUTTON_OPTIONS:
            button_combo.append(value, label)
        button_combo.set_active_id(button)
        button_combo.set_size_request(150, -1)
        button_combo.set_no_show_all(True)
        source_slot.pack_start(button_combo, False, False, 0)


        source_type_combo = Gtk.ComboBoxText()
        for value, label in self.SOURCE_OPTIONS:
            source_type_combo.append(value, label)
        source_type_combo.set_active_id(source_type)
        source_type_combo.set_size_request(155, -1)
        source_type_combo.set_no_show_all(True)
        source_slot.pack_start(source_type_combo, False, False, 0)

        template_entry = Gtk.Entry()
        set_path_entry_value(template_entry, template)
        template_entry.set_placeholder_text("Source template")
        template_entry.set_hexpand(True)
        template_entry.set_no_show_all(True)
        self.configure_template_path_entry(template_entry)
        source_slot.pack_start(template_entry, True, True, 0)

        browse_button = Gtk.Button(label="...")
        browse_button.set_no_show_all(True)
        browse_button.connect("clicked", self.choose_template, template_entry)
        source_slot.pack_start(browse_button, False, False, 0)

        source_x_spin = Gtk.SpinButton.new_with_range(0, 20000, 1)
        source_x_spin.set_value(max(source_x, 0))
        source_x_spin.set_size_request(78, -1)
        source_x_spin.set_no_show_all(True)
        source_x_spin.connect("focus-in-event", self.select_row_by_widget)
        source_slot.pack_start(source_x_spin, False, False, 0)

        source_y_spin = Gtk.SpinButton.new_with_range(0, 20000, 1)
        source_y_spin.set_value(max(source_y, 0))
        source_y_spin.set_size_request(78, -1)
        source_y_spin.set_no_show_all(True)
        source_y_spin.connect("focus-in-event", self.select_row_by_widget)
        source_slot.pack_start(source_y_spin, False, False, 0)

        input_type_combo = Gtk.ComboBoxText()
        for value, label in self.INPUT_OPTIONS:
            input_type_combo.append(value, label)
        input_type_combo.set_active_id(input_type)
        input_type_combo.set_size_request(130, -1)
        input_type_combo.set_no_show_all(True)
        source_slot.pack_start(input_type_combo, False, False, 0)

        keys_entry = Gtk.Entry()
        keys_entry.set_text(keys)
        keys_entry.set_placeholder_text("Ctrl+S, Alt+F7, Ctrl+Shift+S")
        keys_entry.set_tooltip_text("Key combo format: Ctrl+S, Alt+F7, Ctrl+Shift+S")
        keys_entry.set_hexpand(True)
        keys_entry.set_no_show_all(True)
        keys_entry.connect("focus-in-event", self.select_row_by_widget)
        source_slot.pack_start(keys_entry, True, True, 0)

        record_keys_button = Gtk.Button(label="Record")
        record_keys_button.set_tooltip_text("Record the next key combo")
        record_keys_button.set_no_show_all(True)
        record_keys_button.connect("clicked", self.record_key_combo_clicked)
        source_slot.pack_start(record_keys_button, False, False, 0)

        text_entry = Gtk.Entry()
        text_entry.set_text(text)
        text_entry.set_placeholder_text("Text to type")
        text_entry.set_hexpand(True)
        text_entry.set_no_show_all(True)
        text_entry.connect("focus-in-event", self.select_row_by_widget)
        source_slot.pack_start(text_entry, True, True, 0)

        to_label = Gtk.Label(label="to")
        to_label.set_no_show_all(True)
        details_box.pack_start(to_label, False, False, 0)

        target_slot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        target_slot.set_hexpand(True)
        target_slot.set_no_show_all(True)
        details_box.pack_start(target_slot, True, True, 0)

        target_type_combo = Gtk.ComboBoxText()
        for value, label in self.TARGET_OPTIONS:
            target_type_combo.append(value, label)
        target_type_combo.set_active_id(target_type)
        target_type_combo.set_size_request(155, -1)
        target_type_combo.set_no_show_all(True)
        target_slot.pack_start(target_type_combo, False, False, 0)

        target_entry = Gtk.Entry()
        set_path_entry_value(target_entry, target_template)
        target_entry.set_placeholder_text("Target screenshot")
        target_entry.set_hexpand(True)
        target_entry.set_no_show_all(True)
        self.configure_template_path_entry(target_entry)
        target_slot.pack_start(target_entry, True, True, 0)

        target_browse_button = Gtk.Button(label="...")
        target_browse_button.set_no_show_all(True)
        target_browse_button.connect("clicked", self.choose_template, target_entry)
        target_slot.pack_start(target_browse_button, False, False, 0)

        match_combo = Gtk.ComboBoxText()
        for value, label in self.MATCH_OPTIONS:
            match_combo.append(value, label)
        match_combo.set_active_id(match_choice)
        match_combo.set_size_request(118, -1)
        match_combo.set_tooltip_text("Which matching screenshot instance to use")
        match_combo.set_no_show_all(True)
        target_slot.pack_start(match_combo, False, False, 0)

        x_spin = Gtk.SpinButton.new_with_range(0, 20000, 1)
        x_spin.set_value(max(x, 0))
        x_spin.set_size_request(78, -1)
        x_spin.set_no_show_all(True)
        x_spin.connect("focus-in-event", self.select_row_by_widget)
        target_slot.pack_start(x_spin, False, False, 0)

        y_spin = Gtk.SpinButton.new_with_range(0, 20000, 1)
        y_spin.set_value(max(y, 0))
        y_spin.set_size_request(78, -1)
        y_spin.set_no_show_all(True)
        y_spin.connect("focus-in-event", self.select_row_by_widget)
        target_slot.pack_start(y_spin, False, False, 0)

        drag_steps_label = Gtk.Label(label="Steps")
        drag_steps_label.set_no_show_all(True)
        target_slot.pack_start(drag_steps_label, False, False, 0)

        drag_steps_spin = Gtk.SpinButton.new_with_range(1, 200, 1)
        drag_steps_spin.set_value(drag_steps)
        drag_steps_spin.set_size_request(56, -1)
        drag_steps_spin.set_tooltip_text("Smooth drag movement steps")
        drag_steps_spin.set_no_show_all(True)
        drag_steps_spin.connect("focus-in-event", self.select_row_by_widget)
        target_slot.pack_start(drag_steps_spin, False, False, 0)

        wait_spin = Gtk.SpinButton.new_with_range(0.0, 60.0, 0.1)
        wait_spin.set_digits(2)
        wait_spin.set_value(max(wait, 0.0))
        wait_spin.set_size_request(120, -1)
        wait_spin.connect("focus-in-event", self.select_row_by_widget)
        row.pack_start(wait_spin, False, False, 0)

        delete_button = Gtk.Button()
        delete_button.set_tooltip_text("Node entfernen")
        delete_button.set_size_request(34, -1)
        delete_icon = Gtk.Image.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.BUTTON)
        delete_button.add(delete_icon)
        row.pack_start(delete_button, False, False, 0)

        row_data: dict[str, Gtk.Widget] = {
            "row": row_event,
            "row_content": row,
            "number": number_button,
            "note_buffer": note_buffer,
            "indent": indent,
            "handle": handle_event,
            "handle_label": handle_box,
            "block_bar": block_bar,
            "action": action_combo,
            "details": details_box,
            "condition_slot": condition_slot,
            "condition": condition_combo,
            "if_jump_mode": if_jump_combo,
            "if_jump_step": if_jump_spin,
            "condition_template": condition_entry,
            "condition_button": condition_button,
            "source_slot": source_slot,
            "to_label": to_label,
            "target_slot": target_slot,
            "button": button_combo,
            "animate_mouse": animate_mouse_check,
            "source_type": source_type_combo,
            "target_type": target_type_combo,
            "input_type": input_type_combo,
            "template": template_entry,
            "template_button": browse_button,
            "target": target_entry,
            "target_button": target_browse_button,
            "match_choice": match_combo,
            "keys": keys_entry,
            "record_keys_button": record_keys_button,
            "text": text_entry,
            "source_x": source_x_spin,
            "source_y": source_y_spin,
            "x": x_spin,
            "y": y_spin,
            "drag_steps_label": drag_steps_label,
            "drag_steps": drag_steps_spin,
            "wait": wait_spin,
            "delete": delete_button,
        }
        delete_button.connect("clicked", self.confirm_remove_row, row_data)
        number_button.connect("clicked", self.on_note_clicked, row_data)
        handle_event.connect("drag-data-get", self.on_row_drag_data_get, row_data)
        handle_event.connect("drag-begin", self.on_row_drag_begin, row_data)
        handle_event.connect("drag-end", self.on_row_drag_end)
        row_event.connect("drag-motion", self.on_row_drag_motion, row_data)
        row_event.connect("drag-leave", self.on_row_drag_leave)
        row_event.connect("drag-data-received", self.on_row_drag_data_received, row_data)
        action_combo.connect("changed", self.on_click_changed, row_data)
        condition_combo.connect("changed", self.on_click_changed, row_data)
        if_jump_combo.connect("changed", self.on_click_changed, row_data)
        button_combo.connect("changed", self.on_click_changed, row_data)
        animate_mouse_check.connect("toggled", self.select_row_by_widget)
        source_type_combo.connect("changed", self.on_click_changed, row_data)
        target_type_combo.connect("changed", self.on_click_changed, row_data)
        match_combo.connect("changed", self.select_row_by_widget)
        input_type_combo.connect("changed", self.on_click_changed, row_data)
        for widget in (
            row_event,
            handle_event,
            handle_box,
            block_bar,
            action_combo,
            condition_combo,
            if_jump_combo,
            if_jump_spin,
            condition_entry,
            condition_button,
            button_combo,
            animate_mouse_check,
            source_type_combo,
            target_type_combo,
            input_type_combo,
            template_entry,
            browse_button,
            target_entry,
            target_browse_button,
            match_combo,
            keys_entry,
            record_keys_button,
            text_entry,
            to_label,
            source_x_spin,
            source_y_spin,
            x_spin,
            y_spin,
            drag_steps_label,
            drag_steps_spin,
            wait_spin,
            delete_button,
        ):
            widget.connect("button-press-event", self.select_row_by_widget)
            self.widget_rows[id(widget)] = row_data

        self.rows_box.pack_start(row_event, False, False, 0)
        self.rows.append(row_data)
        self.selected_row = row_data
        row_event.show_all()
        self.update_target_visibility(row_data)
        self.update_row_numbers()

    def on_handle_enter(self, widget: Gtk.Widget, _event) -> bool:
        window = widget.get_window()
        display = widget.get_display()
        if window and display:
            cursor = Gdk.Cursor.new_from_name(display, "grab")
            if cursor is None:
                cursor = Gdk.Cursor.new_from_name(display, "pointer")
            window.set_cursor(cursor)
        return False

    def on_handle_leave(self, widget: Gtk.Widget, _event) -> bool:
        window = widget.get_window()
        if window:
            window.set_cursor(None)
        return False

    def show_drop_indicator(self, index: int) -> None:
        self.drop_index = max(0, min(index, len(self.rows)))
        self.rows_box.reorder_child(self.drop_indicator, self.drop_index + 1)
        self.drop_indicator.show()

    def hide_drop_indicator(self) -> None:
        self.drop_indicator.hide()
        self.drop_index = None

    def insertion_index_for_y(self, y: int) -> int:
        for index, row_data in enumerate(self.rows):
            row = row_data["row"]
            allocation = row.get_allocation()
            if y < allocation.y + (allocation.height / 2):
                return index
        return len(self.rows)

    def sync_row_widget_order(self) -> None:
        self.rows_box.reorder_child(self.drop_indicator, 1)
        for index, row_data in enumerate(self.rows):
            self.rows_box.reorder_child(row_data["row"], index + 2)

    def row_indent(self, row_data: dict[str, Gtk.Widget]) -> int:
        try:
            return max(0, int(row_data.get("indent", 0) or 0))
        except (TypeError, ValueError):
            return 0

    def row_is_if(self, row_data: dict[str, Gtk.Widget]) -> bool:
        action_combo = row_data.get("action")
        return isinstance(action_combo, Gtk.ComboBoxText) and action_combo.get_active_id() == "if"

    def set_row_indent(self, row_data: dict[str, Gtk.Widget], indent: int) -> None:
        indent = max(0, min(indent, self.MAX_BLOCK_INDENT))
        row_data["indent"] = indent
        row_content = row_data.get("row_content")
        if isinstance(row_content, Gtk.Widget):
            row_content.set_margin_left(28 * indent)
        block_bar = row_data.get("block_bar")
        if isinstance(block_bar, Gtk.Widget):
            if indent:
                block_bar.show()
            else:
                block_bar.hide()

    def block_end_for_index(
        self,
        index: int,
        rows: list[dict[str, Gtk.Widget]] | None = None,
    ) -> int:
        rows = self.rows if rows is None else rows
        if not 0 <= index < len(rows):
            return index
        parent_indent = self.row_indent(rows[index])
        end_index = index + 1
        while end_index < len(rows) and self.row_indent(rows[end_index]) > parent_indent:
            end_index += 1
        return end_index

    def target_indent_for_drop(
        self,
        target_index: int,
        rows: list[dict[str, Gtk.Widget]],
    ) -> int:
        if target_index > 0:
            previous_row = rows[target_index - 1]
            previous_indent = self.row_indent(previous_row)
            if self.row_is_if(previous_row):
                return min(previous_indent + 1, self.MAX_BLOCK_INDENT)
            if previous_indent:
                return previous_indent
        if target_index < len(rows):
            current_indent = self.row_indent(rows[target_index])
            if current_indent:
                return current_indent
        return 0

    def update_row_numbers(self) -> None:
        for index, row_data in enumerate(self.rows, start=1):
            btn = row_data.get("number")
            if not isinstance(btn, Gtk.Button):
                continue
            buf = row_data.get("note_buffer")
            has_note = isinstance(buf, Gtk.TextBuffer) and buf.get_char_count() > 0
            btn.set_label(f"{index}.")
            ctx = btn.get_style_context()
            if has_note:
                ctx.add_class("input-pilot-note-active")
                note_text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
                btn.set_tooltip_text(note_text)
            else:
                ctx.remove_class("input-pilot-note-active")
                btn.set_tooltip_text("Click to add a note")

    def on_note_clicked(self, button: Gtk.Button, row_data: dict) -> None:
        buf = row_data.get("note_buffer")
        if not isinstance(buf, Gtk.TextBuffer):
            return
        popover = Gtk.Popover()
        popover.set_relative_to(button)
        popover.set_position(Gtk.PositionType.RIGHT)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(10)

        label = Gtk.Label(label="Note")
        label.set_xalign(0)
        box.pack_start(label, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_size_request(280, 90)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        text_view = Gtk.TextView()
        text_view.set_buffer(buf)
        text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        text_view.set_accepts_tab(False)
        scroll.add(text_view)
        box.pack_start(scroll, True, True, 0)

        popover.add(box)
        popover.show_all()
        text_view.grab_focus()
        popover.connect("closed", lambda _p: self.update_row_numbers())

    def on_row_drag_data_get(
        self,
        _widget: Gtk.Widget,
        _context,
        selection_data,
        _info: int,
        _time: int,
        row_data: dict[str, Gtk.Widget],
    ) -> None:
        if row_data in self.rows:
            source_index = self.rows.index(row_data)
            selection_data.set_text(str(source_index), -1)

    def on_row_drag_begin(
        self,
        _widget: Gtk.Widget,
        _context,
        row_data: dict[str, Gtk.Widget],
    ) -> None:
        if row_data not in self.rows:
            return
        self.drag_source_index = self.rows.index(row_data)
        row = row_data["row"]
        row.set_opacity(0.18)
        self.show_drop_indicator(self.drag_source_index)

    def on_row_drag_end(self, _widget: Gtk.Widget, _context) -> None:
        if self.drag_source_index is not None and 0 <= self.drag_source_index < len(self.rows):
            source_row = self.rows[self.drag_source_index]["row"]
            source_row.set_opacity(1.0)
        for row_data in self.rows:
            row_data["row"].set_opacity(1.0)
        self.drag_source_index = None
        self.hide_drop_indicator()
        self.sync_row_widget_order()

    def on_row_drag_motion(
        self,
        widget: Gtk.Widget,
        context,
        _x: int,
        y: int,
        time_: int,
        target_row_data: dict[str, Gtk.Widget],
    ) -> bool:
        if target_row_data not in self.rows:
            return False
        target_index = self.insertion_index_for_y(widget.get_allocation().y + y)
        self.show_drop_indicator(target_index)
        Gdk.drag_status(context, Gdk.DragAction.MOVE, time_)
        return True

    def on_rows_box_drag_motion(
        self,
        _widget: Gtk.Widget,
        context,
        _x: int,
        y: int,
        time_: int,
    ) -> bool:
        self.show_drop_indicator(self.insertion_index_for_y(y))
        Gdk.drag_status(context, Gdk.DragAction.MOVE, time_)
        return True

    def on_row_drag_leave(self, _widget: Gtk.Widget, _context, _time: int) -> None:
        return

    def on_row_drag_data_received(
        self,
        widget: Gtk.Widget,
        context,
        _x: int,
        y: int,
        selection_data,
        _info: int,
        time_: int,
        target_row_data: dict[str, Gtk.Widget],
    ) -> None:
        try:
            source_index = int(selection_data.get_text() or "-1")
        except (TypeError, ValueError):
            Gtk.drag_finish(context, False, False, time_)
            return
        if target_row_data not in self.rows or not 0 <= source_index < len(self.rows):
            Gtk.drag_finish(context, False, False, time_)
            return

        target_index = self.drop_index
        if target_index is None:
            target_index = self.insertion_index_for_y(widget.get_allocation().y + y)
        self.move_row_to_index(source_index, target_index)
        Gtk.drag_finish(context, True, False, time_)

    def on_rows_box_drag_data_received(
        self,
        _widget: Gtk.Widget,
        context,
        _x: int,
        y: int,
        selection_data,
        _info: int,
        time_: int,
    ) -> None:
        try:
            source_index = int(selection_data.get_text() or "-1")
        except (TypeError, ValueError):
            Gtk.drag_finish(context, False, False, time_)
            return
        if not 0 <= source_index < len(self.rows):
            Gtk.drag_finish(context, False, False, time_)
            return

        target_index = self.drop_index
        if target_index is None:
            target_index = self.insertion_index_for_y(y)
        self.move_row_to_index(source_index, target_index)
        Gtk.drag_finish(context, True, False, time_)

    def move_row_to_index(self, source_index: int, target_index: int) -> None:
        if source_index == target_index:
            return
        if not 0 <= source_index < len(self.rows):
            return
        target_index = max(0, min(target_index, len(self.rows)))
        source_end = (
            self.block_end_for_index(source_index)
            if self.row_is_if(self.rows[source_index])
            else source_index + 1
        )
        if source_index < target_index < source_end:
            return
        moved_rows = self.rows[source_index:source_end]
        original_indent = self.row_indent(moved_rows[0])
        del self.rows[source_index:source_end]
        if source_index < target_index:
            target_index -= len(moved_rows)
        target_index = max(0, min(target_index, len(self.rows)))
        target_indent = self.target_indent_for_drop(target_index, self.rows)
        indent_delta = target_indent - original_indent
        for row_data in moved_rows:
            self.set_row_indent(row_data, self.row_indent(row_data) + indent_delta)
        for offset, row_data in enumerate(moved_rows):
            self.rows.insert(target_index + offset, row_data)
        self.sync_row_widget_order()
        self.selected_row = moved_rows[0]
        self.update_row_numbers()

    def on_click_changed(
        self,
        combo: Gtk.ComboBoxText,
        row_data: dict[str, Gtk.Widget],
    ) -> None:
        self.selected_row = row_data
        self.update_target_visibility(row_data)

    def update_target_visibility(self, row_data: dict[str, Gtk.Widget]) -> None:
        action_combo = row_data.get("action")
        button_combo = row_data.get("button")
        animate_mouse_check = row_data.get("animate_mouse")
        condition_slot = row_data.get("condition_slot")
        condition_combo = row_data.get("condition")
        if_jump_combo = row_data.get("if_jump_mode")
        if_jump_spin = row_data.get("if_jump_step")
        condition_entry = row_data.get("condition_template")
        condition_button = row_data.get("condition_button")
        source_slot = row_data.get("source_slot")
        to_label = row_data.get("to_label")
        target_slot = row_data.get("target_slot")
        source_type_combo = row_data.get("source_type")
        target_type_combo = row_data.get("target_type")
        input_type_combo = row_data.get("input_type")
        template_entry = row_data.get("template")
        template_button = row_data.get("template_button")
        target_entry = row_data.get("target")
        target_button = row_data.get("target_button")
        match_combo = row_data.get("match_choice")
        keys_entry = row_data.get("keys")
        record_keys_button = row_data.get("record_keys_button")
        text_entry = row_data.get("text")
        source_x_spin = row_data.get("source_x")
        source_y_spin = row_data.get("source_y")
        x_spin = row_data.get("x")
        y_spin = row_data.get("y")
        drag_steps_label = row_data.get("drag_steps_label")
        drag_steps_spin = row_data.get("drag_steps")
        if not isinstance(action_combo, Gtk.ComboBoxText):
            return
        action = action_combo.get_active_id() or "click"
        source_type = (
            source_type_combo.get_active_id()
            if isinstance(source_type_combo, Gtk.ComboBoxText)
            else "template"
        )
        target_type = (
            target_type_combo.get_active_id()
            if isinstance(target_type_combo, Gtk.ComboBoxText)
            else "template"
        )
        input_type = (
            input_type_combo.get_active_id()
            if isinstance(input_type_combo, Gtk.ComboBoxText)
            else "keys"
        )
        for widget in (
            condition_slot,
            condition_combo,
            if_jump_combo,
            if_jump_spin,
            condition_entry,
            condition_button,
            source_slot,
            to_label,
            target_slot,
            button_combo,
            source_type_combo,
            target_type_combo,
            input_type_combo,
            template_entry,
            template_button,
            target_entry,
            target_button,
            match_combo,
            keys_entry,
            record_keys_button,
            text_entry,
            source_x_spin,
            source_y_spin,
            x_spin,
            y_spin,
            drag_steps_label,
            drag_steps_spin,
        ):
            if isinstance(widget, Gtk.Widget):
                widget.hide()

        if action in {"click", "drag", "move"}:
            if isinstance(animate_mouse_check, Gtk.Widget):
                animate_mouse_check.show()

        if action == "click":
            if isinstance(source_slot, Gtk.Box):
                source_slot.set_hexpand(True)
                source_slot.show()
            if isinstance(target_slot, Gtk.Widget):
                target_slot.show()
            if isinstance(button_combo, Gtk.Widget):
                button_combo.show()
            if isinstance(target_type_combo, Gtk.Widget):
                target_type_combo.show()
        elif action == "drag":
            if isinstance(source_slot, Gtk.Box):
                source_slot.set_hexpand(True)
                source_slot.show()
            if isinstance(to_label, Gtk.Widget):
                to_label.show()
            if isinstance(target_slot, Gtk.Widget):
                target_slot.show()
            if isinstance(source_type_combo, Gtk.Widget):
                source_type_combo.show()
            if isinstance(target_type_combo, Gtk.Widget):
                target_type_combo.show()
        elif action == "move":
            if isinstance(target_slot, Gtk.Widget):
                target_slot.show()
            if isinstance(target_type_combo, Gtk.Widget):
                target_type_combo.show()
        elif action == "input":
            if isinstance(source_slot, Gtk.Widget):
                source_slot.show()
            if isinstance(input_type_combo, Gtk.Widget):
                input_type_combo.show()
        elif action == "if":
            for widget in (condition_slot, condition_combo, if_jump_combo):
                if isinstance(widget, Gtk.Widget):
                    widget.show()
            if (
                isinstance(if_jump_combo, Gtk.ComboBoxText)
                and if_jump_combo.get_active_id() == "step"
                and isinstance(if_jump_spin, Gtk.Widget)
            ):
                if_jump_spin.show()

        if action == "drag" and source_type == "template":
            for widget in (template_entry, template_button):
                if isinstance(widget, Gtk.Widget):
                    widget.show()
        if action == "drag" and source_type == "position":
            for widget in (source_x_spin, source_y_spin):
                if isinstance(widget, Gtk.Widget):
                    widget.show()

        if action in {"click", "drag", "move"} and target_type == "template":
            for widget in (target_entry, target_button, match_combo):
                if isinstance(widget, Gtk.Widget):
                    widget.show()
        if action in {"click", "drag", "move"} and target_type == "position":
            for widget in (x_spin, y_spin):
                if isinstance(widget, Gtk.Widget):
                    widget.show()
        if action == "drag":
            for widget in (drag_steps_label, drag_steps_spin):
                if isinstance(widget, Gtk.Widget):
                    widget.show()
        if action == "input" and input_type == "keys":
            for widget in (keys_entry, record_keys_button):
                if isinstance(widget, Gtk.Widget):
                    widget.show()
        if action == "input" and input_type == "text":
            if isinstance(text_entry, Gtk.Widget):
                text_entry.show()

        for combo in (source_type_combo, target_type_combo):
            if not isinstance(combo, Gtk.ComboBoxText):
                continue
            if action == "drag" and combo is source_type_combo:
                combo.show()
            elif action in {"click", "drag", "move"} and combo is target_type_combo:
                combo.show()
        if isinstance(input_type_combo, Gtk.ComboBoxText) and action == "input":
            input_type_combo.show()
        if isinstance(button_combo, Gtk.ComboBoxText) and action == "click":
            button_combo.show()

    def select_row_by_widget(self, widget: Gtk.Widget, *_args) -> bool:
        row_data = self.widget_rows.get(id(widget))
        if row_data in self.rows:
            self.selected_row = row_data
        return False

    def record_key_combo_clicked(self, button: Gtk.Button) -> None:
        row_data = self.widget_rows.get(id(button))
        if row_data not in self.rows:
            return
        keys_entry = row_data.get("keys")
        if not isinstance(keys_entry, Gtk.Entry):
            return
        dialog = KeyComboRecorderDialog(self)
        response = dialog.run()
        if response == Gtk.ResponseType.OK and dialog.combo:
            keys_entry.set_text(dialog.combo)
        dialog.destroy()

    def add_row(self, _button: Gtk.Button) -> None:
        insert_after = self.selected_row if self.selected_row in self.rows else None
        indent = 0
        if insert_after is not None:
            selected_action = insert_after.get("action")
            selected_indent = int(insert_after.get("indent", 0) or 0)
            if isinstance(selected_action, Gtk.ComboBoxText) and selected_action.get_active_id() == "if":
                indent = min(selected_indent + 1, self.MAX_BLOCK_INDENT)
            elif selected_indent:
                indent = selected_indent

        self.add_row_values("", "", "left", "", "", 0, 0, 0.0, indent=indent)
        new_row = self.rows[-1]
        if insert_after is not None and insert_after in self.rows[:-1]:
            self.rows.pop()
            insert_index = self.rows.index(insert_after) + 1
            self.rows.insert(insert_index, new_row)
            self.sync_row_widget_order()
            self.update_row_numbers()
        action_combo = new_row["action"]
        if isinstance(action_combo, Gtk.ComboBoxText):
            action_combo.grab_focus()

    def confirm_remove_row(
        self,
        _button: Gtk.Button,
        row_data: dict[str, Gtk.Widget],
    ) -> None:
        if row_data not in self.rows:
            return
        number = self.rows.index(row_data) + 1
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text=f"Remove node {number}?",
        )
        dialog.format_secondary_text("This step will be permanently deleted from the automation.")
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Remove", Gtk.ResponseType.OK)
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self.remove_row_data(row_data)

    def remove_row_data(self, row_data: dict[str, Gtk.Widget]) -> None:
        if row_data not in self.rows:
            return
        self.rows_box.remove(row_data["row"])
        for widget in row_data.values():
            self.widget_rows.pop(id(widget), None)
        self.rows.remove(row_data)
        self.selected_row = self.rows[-1] if self.rows else None
        if not self.rows:
            self.add_row_values("", "", "left", "", "", 0, 0, 0.0)
        self.update_row_numbers()

    def remove_selected_row(self, _button: Gtk.Button) -> None:
        if self.selected_row in self.rows:
            self.remove_row_data(self.selected_row)

    def configure_template_path_entry(self, entry: Gtk.Entry) -> None:
        entry.drag_dest_set(
            Gtk.DestDefaults.ALL,
            self.PATH_DND_TARGETS,
            Gdk.DragAction.COPY,
        )
        entry.connect("focus-in-event", self.on_template_path_focus_in)
        entry.connect("focus-out-event", self.on_template_path_focus_out)
        entry.connect("drag-data-received", self.on_template_path_dropped)

    def on_template_path_focus_in(self, entry: Gtk.Entry, *_args) -> bool:
        self.select_row_by_widget(entry)
        full_path = path_entry_value(entry)
        if full_path:
            set_path_entry_value(entry, full_path, compact=False)
        return False

    def on_template_path_focus_out(self, entry: Gtk.Entry, *_args) -> bool:
        set_path_entry_value(entry, path_entry_value(entry), compact=True)
        return False

    def on_template_path_dropped(
        self,
        entry: Gtk.Entry,
        context,
        _x: int,
        _y: int,
        selection_data,
        _info: int,
        time_: int,
    ) -> None:
        path = self.path_from_drop(selection_data)
        if path:
            set_path_entry_value(entry, path)
            self.select_row_by_widget(entry)
        Gtk.drag_finish(context, bool(path), False, time_)

    def path_from_drop(self, selection_data) -> str:
        for uri in selection_data.get_uris() or []:
            file_path = Gio.File.new_for_uri(uri).get_path()
            if file_path:
                return file_path
        text = selection_data.get_text() or ""
        text = text.strip()
        if text.startswith("file://"):
            file_path = Gio.File.new_for_uri(text).get_path()
            return file_path or ""
        return text.splitlines()[0].strip() if text else ""

    def choose_template(self, _button: Gtk.Button, entry: Gtk.Entry) -> None:
        chooser = Gtk.FileChooserDialog(
            title="Screenshot Template wählen",
            parent=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        chooser.add_buttons(
            "Abbrechen",
            Gtk.ResponseType.CANCEL,
            "Auswählen",
            Gtk.ResponseType.OK,
        )
        image_filter = Gtk.FileFilter()
        image_filter.set_name("Images")
        image_filter.add_mime_type("image/png")
        image_filter.add_mime_type("image/jpeg")
        chooser.add_filter(image_filter)

        response = chooser.run()
        if response == Gtk.ResponseType.OK:
            filename = chooser.get_filename()
            if filename:
                set_path_entry_value(entry, filename)
        chooser.destroy()

    def steps(self) -> list[dict[str, object]]:
        steps = []
        for row in self.rows:
            template_entry = row["template"]
            target_entry = row["target"]
            keys_entry = row["keys"]
            text_entry = row["text"]
            source_x_spin = row["source_x"]
            source_y_spin = row["source_y"]
            x_spin = row["x"]
            y_spin = row["y"]
            drag_steps_spin = row["drag_steps"]
            action_combo = row["action"]
            button_combo = row["button"]
            animate_mouse_check = row["animate_mouse"]
            source_type_combo = row["source_type"]
            target_type_combo = row["target_type"]
            input_type_combo = row["input_type"]
            condition_combo = row["condition"]
            if_jump_combo = row["if_jump_mode"]
            if_jump_spin = row["if_jump_step"]
            match_combo = row["match_choice"]
            wait_spin = row["wait"]
            if not (
                isinstance(template_entry, Gtk.Entry)
                and isinstance(target_entry, Gtk.Entry)
                and isinstance(keys_entry, Gtk.Entry)
                and isinstance(text_entry, Gtk.Entry)
                and isinstance(source_x_spin, Gtk.SpinButton)
                and isinstance(source_y_spin, Gtk.SpinButton)
                and isinstance(x_spin, Gtk.SpinButton)
                and isinstance(y_spin, Gtk.SpinButton)
                and isinstance(drag_steps_spin, Gtk.SpinButton)
                and isinstance(action_combo, Gtk.ComboBoxText)
                and isinstance(button_combo, Gtk.ComboBoxText)
                and isinstance(animate_mouse_check, Gtk.ToggleButton)
                and isinstance(source_type_combo, Gtk.ComboBoxText)
                and isinstance(target_type_combo, Gtk.ComboBoxText)
                and isinstance(input_type_combo, Gtk.ComboBoxText)
                and isinstance(condition_combo, Gtk.ComboBoxText)
                and isinstance(if_jump_combo, Gtk.ComboBoxText)
                and isinstance(if_jump_spin, Gtk.SpinButton)
                and isinstance(match_combo, Gtk.ComboBoxText)
                and isinstance(wait_spin, Gtk.SpinButton)
            ):
                continue
            action = action_combo.get_active_id() or "click"
            button = button_combo.get_active_id() or "left"
            source_type = source_type_combo.get_active_id() or "template"
            target_type = target_type_combo.get_active_id() or "template"
            input_type = input_type_combo.get_active_id() or "keys"
            condition = condition_combo.get_active_id() or "previous-node-failed"
            match_choice = match_combo.get_active_id() or "best"
            source_template = path_entry_value(template_entry)
            target_template = path_entry_value(target_entry)
            keys = keys_entry.get_text().strip()
            text = text_entry.get_text()
            template = source_template
            target = target_template
            click = "left"
            if action == "click":
                click = button
                if target_type == "template" and not target_template:
                    continue
                template = target_template if target_type == "template" else ""
                target = target_template if target_type == "template" else ""
            elif action == "drag":
                click = "drag-position" if target_type == "position" else "drag"
                if source_type == "template" and not source_template:
                    continue
                if target_type == "template" and not target_template:
                    continue
                template = source_template
                target = target_template
            elif action == "move":
                click = "previous-position" if target_type == "previous-position" else "position"
                if target_type == "template" and not target_template:
                    continue
                template = target_template if target_type == "template" else ""
                target = target_template if target_type == "template" else ""
            elif action == "input":
                click = input_type
                template = ""
                target = ""
                if input_type == "keys" and not keys:
                    continue
                if input_type == "text" and not text:
                    continue
            elif action == "if":
                click = "if"
                template = ""
                target = ""
            note_buf = row.get("note_buffer")
            note = ""
            if isinstance(note_buf, Gtk.TextBuffer):
                note = note_buf.get_text(note_buf.get_start_iter(), note_buf.get_end_iter(), False)
            steps.append(
                {
                    "template": template,
                    "target": target,
                    "action": action,
                    "button": button,
                    "source_type": source_type,
                    "target_type": target_type,
                    "input_type": input_type,
                    "condition": condition,
                    "condition_template": "",
                    "animate_mouse": animate_mouse_check.get_active()
                    and action in {"click", "drag", "move"},
                    "match_choice": match_choice,
                    "keys": keys,
                    "text": text,
                    "indent": int(row.get("indent", 0) or 0),
                    "source_x": source_x_spin.get_value_as_int(),
                    "source_y": source_y_spin.get_value_as_int(),
                    "x": x_spin.get_value_as_int(),
                    "y": y_spin.get_value_as_int(),
                    "drag_steps": drag_steps_spin.get_value_as_int(),
                    "if_jump_enabled": (
                        if_jump_combo.get_active_id() == "step" and action == "if"
                    ),
                    "if_jump_step": if_jump_spin.get_value_as_int(),
                    "click": click,
                    "wait": wait_spin.get_value(),
                    "note": note,
                }
            )
        return steps

    def automations(self) -> list[dict[str, object]]:
        self.save_current_automation()
        return self.normalize_automations(self.automation_state)


class KeyComboRecorderDialog(Gtk.Dialog):
    def __init__(self, parent: Gtk.Window) -> None:
        super().__init__(title="Record key combo", transient_for=parent, modal=True)
        self.combo = ""
        self.set_default_size(360, 120)
        self.set_border_width(12)
        self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        self.add_events(Gdk.EventMask.KEY_PRESS_MASK)
        self.connect("key-press-event", self.on_key_press)

        content = self.get_content_area()
        self.label = Gtk.Label(
            label="Press the desired key combination, e.g. Ctrl+S."
        )
        self.label.set_xalign(0)
        content.add(self.label)
        self.show_all()
        GLib.idle_add(self.grab_focus)

    def on_key_press(self, _widget: Gtk.Widget, event) -> bool:
        key_name = Gdk.keyval_name(event.keyval) or ""
        if key_name in PURE_MODIFIER_KEYVALS:
            return True

        normalized_key = self.normalize_key_name(key_name)
        if not normalized_key or normalized_key not in RECORDER_SUPPORTED_KEYS:
            self.label.set_text(f"Unsupported key: {key_name}")
            return True

        state = event.state
        modifiers = []
        if state & Gdk.ModifierType.CONTROL_MASK:
            modifiers.append("Ctrl")
        if state & Gdk.ModifierType.MOD1_MASK:
            modifiers.append("Alt")
        if state & Gdk.ModifierType.SHIFT_MASK:
            modifiers.append("Shift")

        meta_masks = [
            getattr(Gdk.ModifierType, "META_MASK", 0),
            getattr(Gdk.ModifierType, "SUPER_MASK", 0),
            getattr(Gdk.ModifierType, "MOD4_MASK", 0),
        ]
        if any(mask and state & mask for mask in meta_masks):
            modifiers.append("Meta")

        self.combo = "+".join([*modifiers, normalized_key])
        self.response(Gtk.ResponseType.OK)
        return True

    @staticmethod
    def normalize_key_name(key_name: str) -> str:
        if key_name in RECORDER_KEY_NAMES:
            return RECORDER_KEY_NAMES[key_name]
        if len(key_name) == 1 and key_name.isalpha():
            return key_name.upper()
        if len(key_name) == 1 and key_name.isdigit():
            return key_name
        if key_name.startswith("F") and key_name[1:].isdigit():
            return key_name
        return key_name


class FolderTemplateDialog(Gtk.Dialog):
    def __init__(self, templates: list[dict[str, object]]) -> None:
        super().__init__(title="Folder Templates")
        self.set_default_size(920, 420)
        self.set_border_width(10)
        self.rows: list[dict[str, Gtk.Widget]] = []
        self.widget_rows: dict[int, dict[str, Gtk.Widget]] = {}
        self.selected_row: dict[str, Gtk.Widget] | None = None
        self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        self.add_button("Ausführen", Gtk.ResponseType.APPLY)
        self.add_button("Speichern", Gtk.ResponseType.OK)

        content = self.get_content_area()
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.add(outer)

        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        outer.pack_start(scroller, True, True, 0)

        self.rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.rows_box.set_border_width(2)
        scroller.add(self.rows_box)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        for label, width in (
            ("Name", 220),
            ("Modifier", 130),
            ("Key", 130),
            ("Template folder", 430),
        ):
            header_label = Gtk.Label(label=label)
            header_label.set_xalign(0)
            header_label.set_size_request(width, -1)
            header.pack_start(header_label, False, False, 0)
        self.rows_box.pack_start(header, False, False, 0)

        for template in templates:
            self.add_row_values(
                str(template.get("name", "")),
                str(template.get("shortcut", "")),
                str(template.get("template", "")),
            )
        if not self.rows:
            self.add_row_values("Project Template", "Ctrl+N", str(DEFAULT_FOLDER_TEMPLATE))

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        outer.pack_start(buttons, False, False, 0)

        add_button = Gtk.Button(label="Add template")
        add_button.connect("clicked", self.add_row)
        buttons.pack_start(add_button, False, False, 0)

        remove_button = Gtk.Button(label="Remove")
        remove_button.connect("clicked", self.remove_selected_row)
        buttons.pack_start(remove_button, False, False, 0)

        self.show_all()

    def add_row_values(self, name: str, shortcut: str, template: str) -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        name_entry = Gtk.Entry()
        name_entry.set_text(name)
        name_entry.set_placeholder_text("Project Template")
        name_entry.set_size_request(220, -1)
        row.pack_start(name_entry, False, False, 0)

        modifier, key = parse_shortcut(shortcut) if shortcut else ("Ctrl", "N")
        modifier_combo = Gtk.ComboBoxText()
        for modifier_option in MODIFIER_OPTIONS:
            modifier_combo.append_text(modifier_option or "—")
        modifier_combo.set_active(
            MODIFIER_OPTIONS.index(modifier) if modifier in MODIFIER_OPTIONS else 0
        )
        modifier_combo.set_size_request(130, -1)
        row.pack_start(modifier_combo, False, False, 0)

        key_combo = Gtk.ComboBoxText()
        key_combo.append_text("—")
        for hotkey in HOTKEY_KEYS:
            key_combo.append_text(hotkey)
        key_combo.set_active(HOTKEY_KEYS.index(key) + 1 if key in HOTKEY_KEYS else 0)
        key_combo.set_size_request(130, -1)
        row.pack_start(key_combo, False, False, 0)

        template_entry = Gtk.Entry()
        template_entry.set_text(template)
        template_entry.set_placeholder_text(str(DEFAULT_FOLDER_TEMPLATE))
        template_entry.set_hexpand(True)
        row.pack_start(template_entry, True, True, 0)

        browse_button = Gtk.Button(label="...")
        browse_button.connect("clicked", self.choose_template_folder, template_entry)
        row.pack_start(browse_button, False, False, 0)

        row_data: dict[str, Gtk.Widget] = {
            "row": row,
            "name": name_entry,
            "modifier": modifier_combo,
            "key": key_combo,
            "template": template_entry,
            "browse": browse_button,
        }
        for widget in row_data.values():
            if isinstance(widget, Gtk.Widget):
                widget.connect("button-press-event", self.select_row_by_widget)
                self.widget_rows[id(widget)] = row_data
        name_entry.connect("focus-in-event", self.select_row_by_widget)
        template_entry.connect("focus-in-event", self.select_row_by_widget)

        self.rows_box.pack_start(row, False, False, 0)
        self.rows.append(row_data)
        self.selected_row = row_data
        row.show_all()

    def select_row_by_widget(self, widget: Gtk.Widget, *_args) -> bool:
        row_data = self.widget_rows.get(id(widget))
        if row_data in self.rows:
            self.selected_row = row_data
        return False

    def add_row(self, _button: Gtk.Button) -> None:
        self.add_row_values("Project Template", "Ctrl+N", str(DEFAULT_FOLDER_TEMPLATE))
        name_entry = self.rows[-1]["name"]
        if isinstance(name_entry, Gtk.Entry):
            name_entry.grab_focus()

    def remove_selected_row(self, _button: Gtk.Button) -> None:
        if self.selected_row in self.rows:
            row = self.selected_row["row"]
            self.rows_box.remove(row)
            for widget in self.selected_row.values():
                self.widget_rows.pop(id(widget), None)
            self.rows.remove(self.selected_row)
            self.selected_row = self.rows[-1] if self.rows else None
        if not self.rows:
            self.add_row_values("Project Template", "Ctrl+N", str(DEFAULT_FOLDER_TEMPLATE))

    def choose_template_folder(self, _button: Gtk.Button, entry: Gtk.Entry) -> None:
        chooser = Gtk.FileChooserDialog(
            title="Template-Ordner wählen",
            parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        chooser.add_buttons(
            "Abbrechen",
            Gtk.ResponseType.CANCEL,
            "Auswählen",
            Gtk.ResponseType.OK,
        )
        response = chooser.run()
        if response == Gtk.ResponseType.OK:
            filename = chooser.get_filename()
            if filename:
                entry.set_text(filename)
        chooser.destroy()

    def row_shortcut(self, row: dict[str, Gtk.Widget]) -> str:
        modifier_combo = row["modifier"]
        key_combo = row["key"]
        if not isinstance(modifier_combo, Gtk.ComboBoxText) or not isinstance(key_combo, Gtk.ComboBoxText):
            return ""
        key_index = key_combo.get_active()
        if key_index <= 0:
            return ""
        modifier_index = modifier_combo.get_active()
        modifier = MODIFIER_OPTIONS[modifier_index] if modifier_index >= 0 else ""
        key = HOTKEY_KEYS[key_index - 1]
        return shortcut_label(modifier, key)

    def selected_index(self) -> int:
        if self.selected_row in self.rows:
            return self.rows.index(self.selected_row) + 1
        return 1

    def templates(self) -> list[dict[str, object]]:
        templates = []
        for index, row in enumerate(self.rows, start=1):
            name_entry = row["name"]
            template_entry = row["template"]
            if not isinstance(name_entry, Gtk.Entry) or not isinstance(template_entry, Gtk.Entry):
                continue
            template = template_entry.get_text().strip()
            if not template:
                continue
            name = name_entry.get_text().strip() or f"Template {index}"
            templates.append(
                {
                    "name": name,
                    "shortcut": self.row_shortcut(row),
                    "template": template,
                    "default_name": name,
                }
            )
        return templates


class TextReplacementDialog(Gtk.Dialog):
    def __init__(self, replacements: list[dict[str, object]]) -> None:
        super().__init__(title="Textreplacement")
        self.set_default_size(720, 420)
        self.set_border_width(10)
        self.rows: list[tuple[Gtk.Entry, Gtk.Entry]] = []
        self.selected_row: tuple[Gtk.Entry, Gtk.Entry] | None = None

        content = self.get_content_area()
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.add(outer)

        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        outer.pack_start(scroller, True, True, 0)

        self.rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.rows_box.set_border_width(2)
        scroller.add(self.rows_box)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        input_header = Gtk.Label(label="Input")
        input_header.set_xalign(0)
        input_header.set_hexpand(True)
        replacement_header = Gtk.Label(label="Replacement / date format (e.g. dd.mm.yyyy)")
        replacement_header.set_xalign(0)
        replacement_header.set_hexpand(True)
        header.pack_start(input_header, True, True, 0)
        header.pack_start(replacement_header, True, True, 0)
        self.rows_box.pack_start(header, False, False, 0)

        for item in replacements:
            trigger = str(item.get("trigger", ""))
            display = str(item.get("date_format", "") or item.get("replacement", ""))
            self.add_row_values(trigger, display)
        if not replacements:
            self.add_row_values("", "")

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        outer.pack_start(buttons, False, False, 0)

        add_button = Gtk.Button(label="Add")
        add_button.connect("clicked", self.add_row)
        buttons.pack_start(add_button, False, False, 0)

        remove_button = Gtk.Button(label="Remove")
        remove_button.connect("clicked", self.remove_selected_row)
        buttons.pack_start(remove_button, False, False, 0)

        spacer = Gtk.Label()
        buttons.pack_start(spacer, True, True, 0)

        cancel_button = Gtk.Button(label="Cancel")
        cancel_button.connect("clicked", lambda _: self.response(Gtk.ResponseType.CANCEL))
        buttons.pack_start(cancel_button, False, False, 0)

        save_button = Gtk.Button(label="Save")
        save_button.connect("clicked", lambda _: self.response(Gtk.ResponseType.OK))
        save_button.get_style_context().add_class("suggested-action")
        buttons.pack_start(save_button, False, False, 0)

        self.show_all()

    def add_row_values(self, trigger: str, replacement: str) -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        trigger_entry = Gtk.Entry()
        trigger_entry.set_text(trigger)
        trigger_entry.set_hexpand(True)
        trigger_entry.set_placeholder_text("Text to replace")

        replacement_entry = Gtk.Entry()
        replacement_entry.set_text(replacement)
        replacement_entry.set_hexpand(True)
        replacement_entry.set_placeholder_text("Replace with or dd.mm.yyyy")
        trigger_entry.connect("focus-in-event", self.select_row, trigger_entry, replacement_entry)
        replacement_entry.connect("focus-in-event", self.select_row, trigger_entry, replacement_entry)

        row.pack_start(trigger_entry, True, True, 0)
        row.pack_start(replacement_entry, True, True, 0)
        self.rows_box.pack_start(row, False, False, 0)
        self.rows.append((trigger_entry, replacement_entry))
        self.selected_row = (trigger_entry, replacement_entry)
        row.show_all()

    def select_row(
        self,
        _widget: Gtk.Widget,
        _event,
        trigger_entry: Gtk.Entry,
        replacement_entry: Gtk.Entry,
    ) -> bool:
        self.selected_row = (trigger_entry, replacement_entry)
        return False

    def add_row(self, _button: Gtk.Button) -> None:
        self.add_row_values("", "")
        self.rows[-1][0].grab_focus()

    def remove_selected_row(self, _button: Gtk.Button) -> None:
        if self.selected_row in self.rows:
            trigger_entry, replacement_entry = self.selected_row
            row = trigger_entry.get_parent()
            self.rows_box.remove(row)
            self.rows.remove(self.selected_row)
            self.selected_row = self.rows[-1] if self.rows else None
        if not self.rows:
            self.add_row_values("", "")

    def replacements(self) -> list[dict[str, object]]:
        replacements = []
        for trigger_entry, replacement_entry in self.rows:
            trigger = trigger_entry.get_text().strip()
            replacement = replacement_entry.get_text()
            if trigger and replacement:
                replacements.append({"trigger": trigger, "replacement": replacement, "enabled": True})
        return replacements


class ShortcutConfigDialog(Gtk.Dialog):
    SHORTCUT_WIDTH = 230
    RECORD_WIDTH = 86
    BROWSE_WIDTH = 86
    REMOVE_WIDTH = 36

    def __init__(self, shortcuts: dict[str, str]) -> None:
        super().__init__(title="Hotkeys")
        self.set_default_size(900, 440)
        self.set_border_width(10)
        self.rows: list[dict[str, Gtk.Widget]] = []

        content = self.get_content_area()
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.add(outer)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        shortcut_header = Gtk.Label(label="Shortcut")
        shortcut_header.set_xalign(0)
        shortcut_header.set_size_request(self.SHORTCUT_WIDTH, -1)
        record_spacer = Gtk.Label()
        record_spacer.set_size_request(self.RECORD_WIDTH, -1)
        target_header = Gtk.Label(label="Path or link")
        target_header.set_xalign(0)
        target_header.set_hexpand(True)
        header.pack_start(shortcut_header, False, False, 0)
        header.pack_start(record_spacer, False, False, 0)
        header.pack_start(target_header, True, True, 0)
        for width in (self.BROWSE_WIDTH, self.REMOVE_WIDTH):
            spacer = Gtk.Label()
            spacer.set_size_request(width, -1)
            header.pack_start(spacer, False, False, 0)
        outer.pack_start(header, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        outer.pack_start(scroller, True, True, 0)

        self.rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.rows_box.set_border_width(2)
        scroller.add(self.rows_box)

        for sc, target in shortcuts.items():
            self._add_row(canonical_shortcut(sc), target)
        if not shortcuts:
            self._add_row("F1", "")

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        outer.pack_start(buttons, False, False, 0)

        add_button = Gtk.Button(label="Add")
        add_button.connect("clicked", self._on_add)
        buttons.pack_start(add_button, False, False, 0)

        spacer = Gtk.Label()
        buttons.pack_start(spacer, True, True, 0)

        cancel_button = Gtk.Button(label="Cancel")
        cancel_button.connect("clicked", lambda _: self.response(Gtk.ResponseType.CANCEL))
        buttons.pack_start(cancel_button, False, False, 0)

        save_button = Gtk.Button(label="Save")
        save_button.connect("clicked", self._on_save)
        save_button.get_style_context().add_class("suggested-action")
        buttons.pack_start(save_button, False, False, 0)

        self.show_all()

    def _on_save(self, _button: Gtk.Button) -> None:
        seen: dict[str, int] = {}
        duplicates: list[str] = []
        invalid: list[str] = []
        for row_data in self.rows:
            shortcut_entry = row_data["shortcut"]
            target_entry = row_data["target"]
            if not isinstance(shortcut_entry, Gtk.Entry) or not isinstance(target_entry, Gtk.Entry):
                continue
            if not target_entry.get_text().strip():
                continue
            label = canonical_shortcut(shortcut_entry.get_text())
            if not label:
                continue
            try:
                modifier, key = parse_shortcut(label)
                key_codes_for(modifier, key)
            except (KeyError, ValueError):
                invalid.append(label)
                continue
            shortcut_entry.set_text(label)
            seen[label] = seen.get(label, 0) + 1
        duplicates = [label for label, count in seen.items() if count > 1]
        if invalid:
            dlg = Gtk.MessageDialog(
                transient_for=self,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK,
                text="Unsupported shortcuts: " + ", ".join(invalid),
            )
            dlg.format_secondary_text("Use Record or enter combinations such as Ctrl+Alt+Shift+2.")
            dlg.run()
            dlg.destroy()
            return
        if duplicates:
            dlg = Gtk.MessageDialog(
                transient_for=self,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK,
                text="Duplicate shortcuts: " + ", ".join(duplicates),
            )
            dlg.format_secondary_text("Please remove or change the duplicates before saving.")
            dlg.run()
            dlg.destroy()
            return
        self.response(Gtk.ResponseType.OK)

    def _add_row(self, shortcut: str, target: str) -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        shortcut_entry = Gtk.Entry()
        shortcut_entry.set_text(canonical_shortcut(shortcut))
        shortcut_entry.set_placeholder_text("Ctrl+Alt+Shift+2")
        shortcut_entry.set_tooltip_text("Type a shortcut or use Record.")
        shortcut_entry.set_size_request(self.SHORTCUT_WIDTH, -1)

        record_button = Gtk.Button(label="Record")
        record_button.set_size_request(self.RECORD_WIDTH, -1)
        record_button.set_tooltip_text("Record the next shortcut")
        record_button.connect("clicked", self._on_record, shortcut_entry)

        target_entry = Gtk.Entry()
        target_entry.set_text(target)
        target_entry.set_hexpand(True)
        target_entry.set_placeholder_text("Path or link")

        browse_button = Gtk.Button(label="Browse")
        browse_button.set_size_request(self.BROWSE_WIDTH, -1)
        browse_button.connect("clicked", self._on_browse, target_entry)

        remove_button = Gtk.Button()
        remove_button.set_size_request(self.REMOVE_WIDTH, -1)
        remove_button.add(
            Gtk.Image.new_from_icon_name("list-remove-symbolic", Gtk.IconSize.BUTTON)
        )
        remove_button.set_tooltip_text("Remove")
        row_data: dict[str, Gtk.Widget] = {
            "row": row,
            "shortcut": shortcut_entry,
            "target": target_entry,
        }
        remove_button.connect("clicked", self._on_remove, row_data)

        row.pack_start(shortcut_entry, False, False, 0)
        row.pack_start(record_button, False, False, 0)
        row.pack_start(target_entry, True, True, 0)
        row.pack_start(browse_button, False, False, 0)
        row.pack_start(remove_button, False, False, 0)

        self.rows_box.pack_start(row, False, False, 0)
        self.rows.append(row_data)
        row.show_all()

    def _on_add(self, _button: Gtk.Button) -> None:
        self._add_row("", "")
        shortcut_entry = self.rows[-1]["shortcut"]
        if isinstance(shortcut_entry, Gtk.Entry):
            shortcut_entry.grab_focus()

    def _on_record(self, _button: Gtk.Button, shortcut_entry: Gtk.Entry) -> None:
        dialog = KeyComboRecorderDialog(self)
        response = dialog.run()
        if response == Gtk.ResponseType.OK and dialog.combo:
            shortcut_entry.set_text(canonical_shortcut(dialog.combo))
        dialog.destroy()

    def _on_browse(self, _button: Gtk.Button, entry: Gtk.Entry) -> None:
        chooser = Gtk.FileChooserDialog(
            title="Select folder",
            parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            buttons=("Cancel", Gtk.ResponseType.CANCEL, "Select", Gtk.ResponseType.OK),
        )
        if chooser.run() == Gtk.ResponseType.OK:
            filename = chooser.get_filename()
            if filename:
                entry.set_text(filename)
        chooser.destroy()

    def _on_remove(
        self,
        _button: Gtk.Button,
        row_data: dict[str, Gtk.Widget],
    ) -> None:
        row = row_data.get("row")
        shortcut_entry = row_data.get("shortcut")
        label = (
            canonical_shortcut(shortcut_entry.get_text())
            if isinstance(shortcut_entry, Gtk.Entry)
            else ""
        ) or "empty shortcut"

        confirm = Gtk.MessageDialog(
            transient_for=self,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=f"Remove shortcut {label!r}?",
        )
        confirm.add_button("Cancel", Gtk.ResponseType.CANCEL)
        btn = confirm.add_button("Remove", Gtk.ResponseType.OK)
        btn.get_style_context().add_class("destructive-action")
        confirm.set_default_response(Gtk.ResponseType.CANCEL)
        response = confirm.run()
        confirm.destroy()
        if response != Gtk.ResponseType.OK:
            return

        if isinstance(row, Gtk.Widget):
            self.rows_box.remove(row)
        if row_data in self.rows:
            self.rows.remove(row_data)

    def shortcuts(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for row_data in self.rows:
            shortcut_entry = row_data["shortcut"]
            target_entry = row_data["target"]
            if not isinstance(shortcut_entry, Gtk.Entry) or not isinstance(target_entry, Gtk.Entry):
                continue
            target = target_entry.get_text().strip()
            label = canonical_shortcut(shortcut_entry.get_text())
            if target and label:
                result[label] = target
        return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show a small automation tray icon.")
    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_TEMPLATE,
        help=f"Button template for the tray click action (default: {DEFAULT_TEMPLATE})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check imports and ydotool status without showing the tray icon.",
    )
    parser.add_argument(
        "--ydotool-socket",
        default=DEFAULT_YDOTOOL_SOCKET,
        help=f"ydotool socket path (default: {DEFAULT_YDOTOOL_SOCKET})",
    )
    parser.add_argument(
        "--apply-shortcuts",
        action="store_true",
        help="Apply configured F1-F11 shortcuts and exit.",
    )
    parser.add_argument(
        "--deactivate-shortcuts",
        action="store_true",
        help="Deactivate configured F1-F11 shortcuts and exit.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.apply_shortcuts:
        apply_shortcuts(load_shortcuts())
        return 0

    if args.deactivate_shortcuts:
        deactivate_shortcuts()
        return 0

    if args.check:
        print("GTK/AppIndicator imports: ok")
        print(f"click image script: {CLICK_IMAGE}")
        print(f"template: {args.template}")
        print(f"ydotool socket: {args.ydotool_socket}")
        print(f"ydotool: {check_ydotool(args.ydotool_socket)}")
        return 0

    tray: AutomationTray | None = None

    def stop_tray(_signum=None, _frame=None):
        deactivate_shortcuts()
        unload_kwin_active_window_script()
        if tray:
            tray.dbus_service.shutdown()
        Gtk.main_quit()

    signal.signal(signal.SIGINT, stop_tray)
    signal.signal(signal.SIGTERM, stop_tray)

    apply_window_icon()
    apply_shortcuts(load_shortcuts())
    tray = AutomationTray(args.template.expanduser(), args.ydotool_socket)
    Gtk.main()
    deactivate_shortcuts()
    unload_kwin_active_window_script()
    if tray:
        tray.dbus_service.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
