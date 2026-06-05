#!/usr/bin/env python3
"""Small KDE tray helper for local Wayland automation actions."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("AppIndicator3", "0.1")
from gi.repository import AppIndicator3, Gdk, Gio, GLib, Gtk  # noqa: E402


APP_ID = "input-pilot"
APP_NAME = "Input Pilot"
SCRIPT_DIR = Path(__file__).resolve().parent
OPEN_DOWNLOADS = SCRIPT_DIR / "open-downloads.sh"
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
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
ACTIVE_WINDOW_FILE = STATE_DIR / "wayland-automation/active-window.json"
CURSOR_POSITION_FILE = STATE_DIR / "wayland-automation/cursor-position.json"
TEXT_REPLACEMENT_PID_FILE = STATE_DIR / "wayland-automation/text-replacement.pid"
TEXT_REPLACEMENT_LOG_FILE = STATE_DIR / "wayland-automation/text-replacement.log"
BUILTIN_TEXT_REPLACEMENTS = [
    ("dt.", "dd.mm.yyyy"),
    ("dt_", "yyyy_mm_dd"),
    ("rnr.", "yyyymmdd"),
]
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
    modifiers = [modifier_names.get(part.upper(), part.title()) for part in parts[:-1]]
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


def load_text_replacements() -> list[dict[str, object]]:
    if not TEXT_REPLACEMENTS_FILE.exists():
        return []
    try:
        with TEXT_REPLACEMENTS_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []

    replacements = []
    for item in data:
        if not isinstance(item, dict):
            continue
        trigger = str(item.get("trigger", "")).strip()
        replacement = str(item.get("replacement", ""))
        if trigger and replacement:
            replacements.append(
                {
                    "trigger": trigger,
                    "replacement": replacement,
                    "enabled": bool(item.get("enabled", True)),
                }
            )
    return replacements


def save_text_replacements(replacements: list[dict[str, object]]) -> None:
    TEXT_REPLACEMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    clean = []
    seen = set()
    for item in replacements:
        trigger = str(item.get("trigger", "")).strip()
        replacement = str(item.get("replacement", ""))
        if not trigger or not replacement or trigger in seen:
            continue
        seen.add(trigger)
        clean.append(
            {
                "trigger": trigger,
                "replacement": replacement,
                "enabled": bool(item.get("enabled", True)),
            }
        )
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
        keys = str(item.get("keys", "")).strip()
        text = str(item.get("text", ""))
        try:
            x = int(float(item.get("x", 0) or 0))
            y = int(float(item.get("y", 0) or 0))
        except (TypeError, ValueError):
            x = 0
            y = 0
        try:
            wait = float(item.get("wait", 0.0) or 0.0)
        except (TypeError, ValueError):
            wait = 0.0
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
        }
        if (
            template
            or (click == "keys" and keys)
            or (click == "text" and text)
            or click in {"position", "previous-position"}
            or (click == "drag-position" and template)
        ):
            steps.append(
                {
                    "template": template,
                    "click": click if click in valid_clicks else "left",
                    "target": str(item.get("target", "")).strip(),
                    "keys": keys,
                    "text": text,
                    "x": max(x, 0),
                    "y": max(y, 0),
                    "wait": max(wait, 0.0),
                }
            )
    return steps


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
    for index, item in enumerate(automations, start=1):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip() or f"Automation {index}"
        shortcut = canonical_shortcut(str(item.get("shortcut", "")))
        clean_automations.append(
            {
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


def save_mouse_config(automations: list[dict[str, object]]) -> None:
    MOUSE_SEQUENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    clean_automations = []
    for index, item in enumerate(automations, start=1):
        name = str(item.get("name", "")).strip() or f"Automation {index}"
        shortcut = canonical_shortcut(str(item.get("shortcut", "")))
        clean_automations.append(
            {
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


def mouse_sequence_desktop_id(index: int) -> str:
    return f"wayland-automation-mouse-sequence-{index}.desktop"


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


def write_mouse_sequence_desktop_file(index: int, name: str) -> str:
    desktop_id = mouse_sequence_desktop_id(index)
    desktop_path = Path.home() / ".local/share/applications" / desktop_id
    desktop_path.parent.mkdir(parents=True, exist_ok=True)
    command = f"{MOUSE_SEQUENCE_RUNNER} --index {index}"
    desktop_path.write_text(
        "\n".join(
            [
                "[Desktop Entry]",
                "Type=Application",
                f"Name=Run Input Pilot mousemove sequence {name}",
                f"Comment=Run Input Pilot mousemove sequence {name}",
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
                "Name=Abort Input Pilot template click",
                "Comment=Emergency stop for Input Pilot template clicking",
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
    shortcut = canonical_shortcut(shortcut)
    if not shortcut:
        return
    modifier, function_key = parse_shortcut(shortcut)
    desktop_id = write_mouse_sequence_desktop_file(index, name)
    shortcut_name = f"Run Input Pilot mousemove sequence {name}"
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
        "codex-open-downloads.desktop",
        "wayland-automation-open-downloads.desktop",
        "wayland-automation-open-nextcloud-files.desktop",
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
    register_folder_template_shortcuts(load_folder_templates())
    configured = set(shortcuts)
    for modifier in MODIFIER_OPTIONS:
        for function_key in FUNCTION_KEYS:
            shortcut = shortcut_label(modifier, function_key)
            target = shortcuts.get(shortcut, "").strip()
            if target:
                register_shortcut(shortcut, target)
            elif shortcut not in configured:
                unregister_shortcut(shortcut)

    for function_key in FUNCTION_KEYS:
        target = shortcuts.get(function_key, "").strip()
        dialog_shortcut = shortcut_label(DIALOG_MODIFIER, function_key)
        if target and Path(target).expanduser().is_dir() and dialog_shortcut not in shortcuts:
            register_dialog_shortcut(function_key, str(Path(target).expanduser()))
        else:
            unregister_dialog_shortcut(function_key)


def deactivate_shortcuts() -> None:
    disable_legacy_shortcuts()
    unregister_emergency_shortcut()
    unregister_mouse_sequence_shortcuts()
    unregister_folder_template_shortcuts()
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
        self.indicator.set_icon_full("preferences-desktop-keyboard", APP_NAME)
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

    def open_downloads(self, _item: Gtk.MenuItem) -> None:
        run_detached([str(OPEN_DOWNLOADS)])

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
            save_mouse_config(automations)
            unregister_mouse_sequence_shortcuts()
            notify(
                APP_NAME,
                f"{len(automations)} Input-Automationen gespeichert. Trigger laufen über Input Pilot.",
            )
            if response == Gtk.ResponseType.APPLY:
                command = [str(MOUSE_SEQUENCE_RUNNER), "--index", str(dialog.selected_index())]
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
        dialog = ShortcutConfigDialog(load_shortcuts())
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            shortcuts = dialog.shortcuts()
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
    ROW_DND_TARGETS = [
        Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0)
    ]
    CLICK_OPTIONS = [
        ("left", "Left click"),
        ("right", "Right click"),
        ("double-left", "Double left click"),
        ("hover", "Hover"),
        ("drag", "Drag to template"),
        ("drag-position", "Drag to mouse position"),
        ("keys", "Key combo"),
        ("text", "Input string"),
        ("position", "Mouse position"),
        ("previous-position", "Previous mouse position"),
    ]

    def __init__(self, automations: list[dict[str, object]]) -> None:
        super().__init__(title="Input Automations")
        self.set_default_size(980, 540)
        self.set_border_width(10)
        self.install_css()
        self.automation_state = self.normalize_automations(automations)
        self.current_index = 0
        self.loading = False
        self.rows: list[dict[str, Gtk.Widget]] = []
        self.widget_rows: dict[int, dict[str, Gtk.Widget]] = {}
        self.selected_row: dict[str, Gtk.Widget] | None = None
        self.drag_source_index: int | None = None
        self.drop_index: int | None = None
        self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        self.add_button("Ausführen", Gtk.ResponseType.APPLY)
        self.add_button("Speichern", Gtk.ResponseType.OK)

        content = self.get_content_area()
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.add(outer)

        automation_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        outer.pack_start(automation_row, False, False, 0)

        automation_label = Gtk.Label(label="Automation")
        automation_label.set_xalign(0)
        automation_row.pack_start(automation_label, False, False, 0)

        self.automation_combo = Gtk.ComboBoxText()
        self.automation_combo.set_size_request(220, -1)
        self.automation_combo.connect("changed", self.on_automation_changed)
        automation_row.pack_start(self.automation_combo, False, False, 0)

        self.name_entry = Gtk.Entry()
        self.name_entry.set_placeholder_text("Name")
        automation_row.pack_start(self.name_entry, True, True, 0)

        add_automation_button = Gtk.Button(label="Automation hinzufügen")
        add_automation_button.connect("clicked", self.add_automation)
        automation_row.pack_start(add_automation_button, False, False, 0)

        remove_automation_button = Gtk.Button(label="Automation entfernen")
        remove_automation_button.connect("clicked", self.remove_automation)
        automation_row.pack_start(remove_automation_button, False, False, 0)

        trigger_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        outer.pack_start(trigger_row, False, False, 0)

        trigger_label = Gtk.Label(label="Trigger")
        trigger_label.set_xalign(0)
        trigger_row.pack_start(trigger_label, False, False, 0)

        self.modifier_combo = Gtk.ComboBoxText()
        for modifier_option in MODIFIER_OPTIONS:
            self.modifier_combo.append_text(modifier_option or "Keine")
        trigger_row.pack_start(self.modifier_combo, False, False, 0)

        self.key_combo = Gtk.ComboBoxText()
        self.key_combo.append_text("Keine")
        for key in HOTKEY_KEYS:
            self.key_combo.append_text(key)
        trigger_row.pack_start(self.key_combo, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        outer.pack_start(scroller, True, True, 0)

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
            ("Screenshot Template", 330),
            ("Target Template", 300),
            ("Action", 170),
            ("Wait/Sleep", 120),
        ):
            header_label = Gtk.Label(label=label)
            header_label.set_xalign(0)
            header_label.set_size_request(width, -1)
            header.pack_start(header_label, False, False, 0)
        self.rows_box.pack_start(header, False, False, 0)
        self.rows_box.pack_start(self.drop_indicator, False, False, 0)
        self.drop_indicator.hide()

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        outer.pack_start(buttons, False, False, 0)

        self.debug_check = Gtk.CheckButton(label="Debug")
        self.debug_check.set_tooltip_text("Show helpful notifications while running this automation")
        buttons.pack_start(self.debug_check, False, False, 0)

        add_button = Gtk.Button(label="Node hinzufügen")
        add_button.connect("clicked", self.add_row)
        buttons.pack_start(add_button, False, False, 0)

        remove_button = Gtk.Button(label="Entfernen")
        remove_button.connect("clicked", self.remove_selected_row)
        buttons.pack_start(remove_button, False, False, 0)

        self.refresh_automation_combo(0)
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
        for index, automation in enumerate(automations, start=1):
            if not isinstance(automation, dict):
                continue
            normalized.append(
                {
                    "name": str(automation.get("name", "")).strip()
                    or f"Automation {index}",
                    "shortcut": canonical_shortcut(str(automation.get("shortcut", ""))),
                    "debug": bool(automation.get("debug", False)),
                    "steps": clean_mouse_steps(automation.get("steps", [])),
                }
            )
        if not normalized:
            normalized.append(
                {"name": "Automation 1", "shortcut": "", "debug": False, "steps": []}
            )
        return normalized

    def refresh_automation_combo(self, active_index: int) -> None:
        self.loading = True
        self.automation_combo.remove_all()
        for automation in self.automation_state:
            self.automation_combo.append_text(str(automation.get("name", "Automation")))
        self.automation_combo.set_active(max(0, min(active_index, len(self.automation_state) - 1)))
        self.loading = False

    def on_automation_changed(self, _combo: Gtk.ComboBoxText) -> None:
        if self.loading:
            return
        new_index = self.automation_combo.get_active()
        if new_index < 0 or new_index == self.current_index:
            return
        self.save_current_automation()
        self.load_automation(new_index)

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
                    )
        if not self.rows:
            self.add_row_values("", "", "left", "", "", 0, 0, 0.0)
        self.update_row_numbers()

    def save_current_automation(self) -> None:
        if not self.automation_state:
            return
        self.automation_state[self.current_index] = {
            "name": self.name_entry.get_text().strip()
            or f"Automation {self.current_index + 1}",
            "shortcut": self.shortcut(),
            "debug": self.debug_check.get_active(),
            "steps": self.steps(),
        }
        self.refresh_automation_combo(self.current_index)

    def add_automation(self, _button: Gtk.Button) -> None:
        self.save_current_automation()
        self.automation_state.append(
            {
                "name": f"Automation {len(self.automation_state) + 1}",
                "shortcut": "",
                "debug": False,
                "steps": [],
            }
        )
        self.refresh_automation_combo(len(self.automation_state) - 1)
        self.load_automation(len(self.automation_state) - 1)
        self.name_entry.grab_focus()

    def remove_automation(self, _button: Gtk.Button) -> None:
        if len(self.automation_state) <= 1:
            self.automation_state = [
                {"name": "Automation 1", "shortcut": "", "debug": False, "steps": []}
            ]
            self.refresh_automation_combo(0)
            self.load_automation(0)
            return
        self.automation_state.pop(self.current_index)
        next_index = min(self.current_index, len(self.automation_state) - 1)
        self.refresh_automation_combo(next_index)
        self.load_automation(next_index)

    def selected_index(self) -> int:
        return self.current_index + 1

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
    ) -> None:
        row_event = Gtk.EventBox()
        row_event.set_visible_window(False)
        row_event.drag_dest_set(
            Gtk.DestDefaults.ALL,
            self.ROW_DND_TARGETS,
            Gdk.DragAction.MOVE,
        )

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
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

        number_label = Gtk.Label(label="")
        number_label.set_xalign(0)
        number_label.set_size_request(24, -1)
        number_label.get_style_context().add_class("input-pilot-row-number")
        reorder_box.pack_start(number_label, False, False, 0)
        row.pack_start(reorder_box, False, False, 0)

        source_slot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        source_slot.set_size_request(330, -1)
        row.pack_start(source_slot, False, False, 0)

        template_entry = Gtk.Entry()
        template_entry.set_text(template)
        template_entry.set_placeholder_text("Source template")
        template_entry.set_hexpand(True)
        template_entry.set_no_show_all(True)
        template_entry.connect("focus-in-event", self.select_row_by_widget)
        source_slot.pack_start(template_entry, True, True, 0)

        browse_button = Gtk.Button(label="...")
        browse_button.set_no_show_all(True)
        browse_button.connect("clicked", self.choose_template, template_entry)
        source_slot.pack_start(browse_button, False, False, 0)

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

        x_spin = Gtk.SpinButton.new_with_range(0, 20000, 1)
        x_spin.set_value(max(x, 0))
        x_spin.set_size_request(90, -1)
        x_spin.set_no_show_all(True)
        x_spin.connect("focus-in-event", self.select_row_by_widget)
        source_slot.pack_start(x_spin, False, False, 0)

        y_spin = Gtk.SpinButton.new_with_range(0, 20000, 1)
        y_spin.set_value(max(y, 0))
        y_spin.set_size_request(90, -1)
        y_spin.set_no_show_all(True)
        y_spin.connect("focus-in-event", self.select_row_by_widget)
        source_slot.pack_start(y_spin, False, False, 0)

        target_slot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        target_slot.set_size_request(300, -1)
        row.pack_start(target_slot, False, False, 0)

        target_entry = Gtk.Entry()
        target_entry.set_text(target)
        target_entry.set_placeholder_text("Drag target template")
        target_entry.set_hexpand(True)
        target_entry.set_no_show_all(True)
        target_entry.connect("focus-in-event", self.select_row_by_widget)
        target_slot.pack_start(target_entry, True, True, 0)

        target_browse_button = Gtk.Button(label="...")
        target_browse_button.set_no_show_all(True)
        target_browse_button.connect("clicked", self.choose_template, target_entry)
        target_slot.pack_start(target_browse_button, False, False, 0)

        click_combo = Gtk.ComboBoxText()
        for value, label in self.CLICK_OPTIONS:
            click_combo.append(value, label)
        valid_clicks = {value for value, _ in self.CLICK_OPTIONS}
        click_combo.set_active_id(click if click in valid_clicks else "left")
        click_combo.set_size_request(170, -1)
        row.pack_start(click_combo, False, False, 0)

        wait_spin = Gtk.SpinButton.new_with_range(0.0, 60.0, 0.1)
        wait_spin.set_digits(2)
        wait_spin.set_value(max(wait, 0.0))
        wait_spin.set_size_request(120, -1)
        wait_spin.connect("focus-in-event", self.select_row_by_widget)
        row.pack_start(wait_spin, False, False, 0)

        row_data: dict[str, Gtk.Widget] = {
            "row": row_event,
            "row_content": row,
            "number": number_label,
            "handle": handle_event,
            "handle_label": handle_box,
            "source_slot": source_slot,
            "target_slot": target_slot,
            "template": template_entry,
            "template_button": browse_button,
            "target": target_entry,
            "target_button": target_browse_button,
            "keys": keys_entry,
            "record_keys_button": record_keys_button,
            "text": text_entry,
            "x": x_spin,
            "y": y_spin,
            "click": click_combo,
            "wait": wait_spin,
        }
        handle_event.connect("drag-data-get", self.on_row_drag_data_get, row_data)
        handle_event.connect("drag-begin", self.on_row_drag_begin, row_data)
        handle_event.connect("drag-end", self.on_row_drag_end)
        row_event.connect("drag-motion", self.on_row_drag_motion, row_data)
        row_event.connect("drag-leave", self.on_row_drag_leave)
        row_event.connect("drag-data-received", self.on_row_drag_data_received, row_data)
        click_combo.connect("changed", self.on_click_changed, row_data)
        for widget in (
            row_event,
            handle_event,
            handle_box,
            template_entry,
            browse_button,
            target_entry,
            target_browse_button,
            keys_entry,
            record_keys_button,
            text_entry,
            x_spin,
            y_spin,
            click_combo,
            wait_spin,
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

    def update_row_numbers(self) -> None:
        for index, row_data in enumerate(self.rows, start=1):
            number_label = row_data.get("number")
            if isinstance(number_label, Gtk.Label):
                number_label.set_text(f"{index}.")

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
        row_data = self.rows.pop(source_index)
        if source_index < target_index:
            target_index -= 1
        target_index = max(0, min(target_index, len(self.rows)))
        self.rows.insert(target_index, row_data)
        self.sync_row_widget_order()
        self.selected_row = row_data
        self.update_row_numbers()

    def on_click_changed(
        self,
        combo: Gtk.ComboBoxText,
        row_data: dict[str, Gtk.Widget],
    ) -> None:
        self.selected_row = row_data
        self.update_target_visibility(row_data)

    def update_target_visibility(self, row_data: dict[str, Gtk.Widget]) -> None:
        click_combo = row_data.get("click")
        template_entry = row_data.get("template")
        template_button = row_data.get("template_button")
        target_entry = row_data.get("target")
        target_button = row_data.get("target_button")
        keys_entry = row_data.get("keys")
        record_keys_button = row_data.get("record_keys_button")
        text_entry = row_data.get("text")
        x_spin = row_data.get("x")
        y_spin = row_data.get("y")
        if not isinstance(click_combo, Gtk.ComboBoxText):
            return
        click = click_combo.get_active_id()
        template_visible = click in {
            "left",
            "right",
            "double-left",
            "hover",
            "drag",
            "drag-position",
        }
        for widget in (template_entry, template_button):
            if isinstance(widget, Gtk.Widget):
                widget.show() if template_visible else widget.hide()

        visible = click == "drag"
        for widget in (target_entry, target_button):
            if isinstance(widget, Gtk.Widget):
                widget.show() if visible else widget.hide()
        if isinstance(keys_entry, Gtk.Widget):
            keys_entry.show() if click == "keys" else keys_entry.hide()
        if isinstance(record_keys_button, Gtk.Widget):
            record_keys_button.show() if click == "keys" else record_keys_button.hide()
        if isinstance(text_entry, Gtk.Widget):
            text_entry.show() if click == "text" else text_entry.hide()
        position_visible = click in {"position", "drag-position"}
        for widget in (x_spin, y_spin):
            if isinstance(widget, Gtk.Widget):
                widget.show() if position_visible else widget.hide()

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
        self.add_row_values("", "", "left", "", "", 0, 0, 0.0)
        template_entry = self.rows[-1]["template"]
        if isinstance(template_entry, Gtk.Entry):
            template_entry.grab_focus()

    def remove_selected_row(self, _button: Gtk.Button) -> None:
        if self.selected_row in self.rows:
            row = self.selected_row["row"]
            self.rows_box.remove(row)
            for widget in self.selected_row.values():
                self.widget_rows.pop(id(widget), None)
            self.rows.remove(self.selected_row)
            self.selected_row = self.rows[-1] if self.rows else None
        if not self.rows:
            self.add_row_values("", "", "left", "", "", 0, 0, 0.0)

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
                entry.set_text(filename)
        chooser.destroy()

    def steps(self) -> list[dict[str, object]]:
        steps = []
        for row in self.rows:
            template_entry = row["template"]
            target_entry = row["target"]
            keys_entry = row["keys"]
            text_entry = row["text"]
            x_spin = row["x"]
            y_spin = row["y"]
            click_combo = row["click"]
            wait_spin = row["wait"]
            if not (
                isinstance(template_entry, Gtk.Entry)
                and isinstance(target_entry, Gtk.Entry)
                and isinstance(keys_entry, Gtk.Entry)
                and isinstance(text_entry, Gtk.Entry)
                and isinstance(x_spin, Gtk.SpinButton)
                and isinstance(y_spin, Gtk.SpinButton)
                and isinstance(click_combo, Gtk.ComboBoxText)
                and isinstance(wait_spin, Gtk.SpinButton)
            ):
                continue
            template = template_entry.get_text().strip()
            click = click_combo.get_active_id() or "left"
            keys = keys_entry.get_text().strip()
            text = text_entry.get_text()
            if click == "keys" and not keys:
                continue
            if click == "text" and not text:
                continue
            if click not in {"keys", "text", "position", "previous-position"} and not template:
                continue
            steps.append(
                {
                    "template": template,
                    "target": target_entry.get_text().strip(),
                    "keys": keys,
                    "text": text,
                    "x": x_spin.get_value_as_int(),
                    "y": y_spin.get_value_as_int(),
                    "click": click,
                    "wait": wait_spin.get_value(),
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
            label="Gewünschte Tastenkombination drücken, z.B. Ctrl+S."
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

        add_button = Gtk.Button(label="Template hinzufügen")
        add_button.connect("clicked", self.add_row)
        buttons.pack_start(add_button, False, False, 0)

        remove_button = Gtk.Button(label="Entfernen")
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
            modifier_combo.append_text(modifier_option or "Keine")
        modifier_combo.set_active(
            MODIFIER_OPTIONS.index(modifier) if modifier in MODIFIER_OPTIONS else 0
        )
        modifier_combo.set_size_request(130, -1)
        row.pack_start(modifier_combo, False, False, 0)

        key_combo = Gtk.ComboBoxText()
        key_combo.append_text("Keine")
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
        self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
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
        input_header = Gtk.Label(label="Input")
        input_header.set_xalign(0)
        input_header.set_hexpand(True)
        replacement_header = Gtk.Label(label="Replacement")
        replacement_header.set_xalign(0)
        replacement_header.set_hexpand(True)
        header.pack_start(input_header, True, True, 0)
        header.pack_start(replacement_header, True, True, 0)
        self.rows_box.pack_start(header, False, False, 0)

        self.add_builtin_rows()

        for item in replacements:
            self.add_row_values(
                str(item.get("trigger", "")),
                str(item.get("replacement", "")),
            )
        if not replacements:
            self.add_row_values("", "")

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        outer.pack_start(buttons, False, False, 0)

        add_button = Gtk.Button(label="Hinzufügen")
        add_button.connect("clicked", self.add_row)
        buttons.pack_start(add_button, False, False, 0)

        remove_button = Gtk.Button(label="Entfernen")
        remove_button.connect("clicked", self.remove_selected_row)
        buttons.pack_start(remove_button, False, False, 0)

        self.show_all()

    def add_builtin_rows(self) -> None:
        label = Gtk.Label(label="Built-ins")
        label.set_xalign(0)
        self.rows_box.pack_start(label, False, False, 0)
        for trigger, replacement in BUILTIN_TEXT_REPLACEMENTS:
            self.add_readonly_row(trigger, replacement)

    def add_readonly_row(self, trigger: str, replacement: str) -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        trigger_entry = Gtk.Entry()
        trigger_entry.set_text(trigger)
        trigger_entry.set_hexpand(True)
        trigger_entry.set_editable(False)
        trigger_entry.set_sensitive(False)

        replacement_entry = Gtk.Entry()
        replacement_entry.set_text(replacement)
        replacement_entry.set_hexpand(True)
        replacement_entry.set_editable(False)
        replacement_entry.set_sensitive(False)

        row.pack_start(trigger_entry, True, True, 0)
        row.pack_start(replacement_entry, True, True, 0)
        self.rows_box.pack_start(row, False, False, 0)

    def add_row_values(self, trigger: str, replacement: str) -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        trigger_entry = Gtk.Entry()
        trigger_entry.set_text(trigger)
        trigger_entry.set_hexpand(True)
        trigger_entry.set_placeholder_text("Text to replace")

        replacement_entry = Gtk.Entry()
        replacement_entry.set_text(replacement)
        replacement_entry.set_hexpand(True)
        replacement_entry.set_placeholder_text("Replace with")
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
                replacements.append(
                    {
                        "trigger": trigger,
                        "replacement": replacement,
                        "enabled": True,
                    }
                )
        return replacements


class ShortcutConfigDialog(Gtk.Dialog):
    def __init__(self, shortcuts: dict[str, str]) -> None:
        super().__init__(title="Shortcut-Konfiguration")
        self.set_default_size(760, 440)
        self.set_border_width(10)
        self.entries: dict[str, Gtk.Entry] = {}
        self.shortcuts_state = dict(shortcuts)
        self.current_modifier = ""
        self.modifier_combo = Gtk.ComboBoxText()
        self.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        self.add_button("Speichern", Gtk.ResponseType.OK)

        content = self.get_content_area()
        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        top_label = Gtk.Label(label="Modifier")
        top_label.set_xalign(0)
        for modifier in MODIFIER_OPTIONS:
            self.modifier_combo.append_text(modifier or "Keine")
        self.modifier_combo.set_active(0)
        self.modifier_combo.connect("changed", self.on_modifier_changed)
        top_row.pack_start(top_label, False, False, 0)
        top_row.pack_start(self.modifier_combo, False, False, 0)
        content.add(top_row)

        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        grid.set_border_width(8)
        content.add(grid)

        key_header = Gtk.Label(label="Taste")
        key_header.set_xalign(0)
        target_header = Gtk.Label(label="Pfad oder Link")
        target_header.set_xalign(0)
        grid.attach(key_header, 0, 0, 1, 1)
        grid.attach(target_header, 1, 0, 3, 1)

        for row, key in enumerate(FUNCTION_KEYS, start=1):
            key_label = Gtk.Label(label=key)
            key_label.set_xalign(0)
            entry = Gtk.Entry()
            entry.set_hexpand(True)
            entry.set_text(self.shortcuts_state.get(key, ""))
            entry.set_placeholder_text(key)
            browse_button = Gtk.Button(label="Auswählen")
            clear_button = Gtk.Button(label="Leeren")
            browse_button.connect("clicked", self.on_browse, entry)
            clear_button.connect("clicked", self.on_clear, entry)

            self.entries[key] = entry
            grid.attach(key_label, 0, row, 1, 1)
            grid.attach(entry, 1, row, 1, 1)
            grid.attach(browse_button, 2, row, 1, 1)
            grid.attach(clear_button, 3, row, 1, 1)

        self.show_all()

    def selected_modifier(self) -> str:
        index = self.modifier_combo.get_active()
        if index < 0:
            return ""
        return MODIFIER_OPTIONS[index]

    def save_visible_entries(self) -> None:
        for key, entry in self.entries.items():
            shortcut = shortcut_label(self.current_modifier, key)
            value = entry.get_text().strip()
            if value:
                self.shortcuts_state[shortcut] = value
            else:
                self.shortcuts_state.pop(shortcut, None)

    def on_modifier_changed(self, _combo: Gtk.ComboBoxText) -> None:
        self.save_visible_entries()
        modifier = self.selected_modifier()
        self.current_modifier = modifier
        for key, entry in self.entries.items():
            shortcut = shortcut_label(modifier, key)
            entry.set_text(self.shortcuts_state.get(shortcut, ""))
            entry.set_placeholder_text(shortcut)

    def on_browse(self, _button: Gtk.Button, entry: Gtk.Entry) -> None:
        chooser = Gtk.FileChooserDialog(
            title="Pfad auswählen",
            parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            buttons=(
                "Abbrechen",
                Gtk.ResponseType.CANCEL,
                "Auswählen",
                Gtk.ResponseType.OK,
            ),
        )
        if chooser.run() == Gtk.ResponseType.OK:
            filename = chooser.get_filename()
            if filename:
                entry.set_text(filename)
        chooser.destroy()

    def on_clear(self, _button: Gtk.Button, entry: Gtk.Entry) -> None:
        entry.set_text("")

    def shortcuts(self) -> dict[str, str]:
        self.save_visible_entries()
        return dict(self.shortcuts_state)


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
        print(f"open downloads script: {OPEN_DOWNLOADS}")
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
