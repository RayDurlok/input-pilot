#!/usr/bin/env python3
"""Open a configured target for a function key."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


CONFIG_FILE = Path.home() / ".config/wayland-automation/shortcuts.json"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
LOG_FILE = STATE_DIR / "wayland-automation/configured-shortcuts.log"
ACTIVE_WINDOW_FILE = STATE_DIR / "wayland-automation/active-window.json"
DEFAULT_YDOTOOL_SOCKET = "/tmp/ydotool_socket"
AUTO_DIALOG_TRIGGER_SETTLE_SECONDS = 0.08
EXPLICIT_DIALOG_TRIGGER_SETTLE_SECONDS = 0.35
LOCATION_FOCUS_DELAY_SECONDS = 0.1
PASTE_SETTLE_DELAY_SECONDS = 0.08
CLIPBOARD_RESTORE_DELAY_SECONDS = 0.7
ACTIVE_WINDOW_MAX_AGE_SECONDS = 6 * 60 * 60


class AutomationError(RuntimeError):
    pass


def canonical_shortcut(shortcut: str) -> str:
    parts = [part.strip() for part in shortcut.split("+") if part.strip()]
    if not parts:
        return ""
    key = parts[-1].upper()
    modifier_names = {
        "ALT": "Alt",
        "CTRL": "Ctrl",
        "CONTROL": "Ctrl",
        "META": "Meta",
        "SUPER": "Meta",
        "SHIFT": "Shift",
    }
    modifiers = [modifier_names.get(part.upper(), part.title()) for part in parts[:-1]]
    return f"{'+'.join(modifiers)}+{key}" if modifiers else key


def load_config() -> dict[str, str]:
    if not CONFIG_FILE.exists():
        return {}
    with CONFIG_FILE.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {}
    return {
        canonical_shortcut(str(key)): str(value)
        for key, value in data.items()
        if canonical_shortcut(str(key))
    }


def normalize_target(target: str) -> str:
    target = target.strip()
    parsed = urlparse(target)
    if parsed.scheme:
        return target
    return str(Path(target).expanduser())


def log_invocation(key: str, target: str, mode: str) -> None:
    log_event(f"mode={mode} key={key} target={target} pid={os.getpid()}")


def log_event(message: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")


def notify(message: str) -> None:
    if shutil.which("notify-send"):
        subprocess.Popen(
            ["notify-send", "Wayland Automation", message],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def clipboard_text() -> str | None:
    try:
        result = subprocess.run(
            ["wl-paste", "--no-newline"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def set_clipboard(text: str) -> None:
    try:
        subprocess.run(
            ["wl-copy"],
            input=text,
            text=True,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise AutomationError("wl-copy ist nicht installiert.") from exc
    except subprocess.CalledProcessError as exc:
        raise AutomationError("wl-copy konnte den Pfad nicht in die Zwischenablage legen.") from exc


def ydotool_key(*events: str) -> None:
    env = dict(os.environ)
    env.setdefault("YDOTOOL_SOCKET", DEFAULT_YDOTOOL_SOCKET)
    try:
        result = subprocess.run(
            ["ydotool", "key", *events],
            env=env,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=2,
        )
    except FileNotFoundError as exc:
        raise AutomationError("ydotool ist nicht installiert.") from exc
    except subprocess.TimeoutExpired as exc:
        raise AutomationError("ydotool hat nicht innerhalb von 2 Sekunden reagiert.") from exc
    if result.returncode != 0:
        detail = result.stdout.strip()
        if detail:
            log_event(f"ydotool-error output={detail!r}")
        raise AutomationError(
            f"ydotool ist nicht erreichbar. Socket: {env.get('YDOTOOL_SOCKET')}"
        )


def open_in_file_dialog(directory: str, trigger_settle_seconds: float) -> None:
    old_clipboard = clipboard_text()
    try:
        set_clipboard(directory)
        log_event(f"dialog-step clipboard-set target={directory}")
        # Global shortcuts fire before the physical modifier keys are always up.
        time.sleep(trigger_settle_seconds)
        # Ctrl+L focuses the location field in common KDE/GTK file dialogs.
        ydotool_key("29:1", "38:1", "38:0", "29:0")
        log_event("dialog-step sent=ctrl+l")
        time.sleep(LOCATION_FOCUS_DELAY_SECONDS)
        ydotool_key("29:1", "30:1", "30:0", "29:0")
        log_event("dialog-step sent=ctrl+a")
        ydotool_key("29:1", "47:1", "47:0", "29:0")
        log_event("dialog-step sent=ctrl+v")
        time.sleep(PASTE_SETTLE_DELAY_SECONDS)
        ydotool_key("28:1", "28:0")
        log_event("dialog-step sent=enter")
    finally:
        if old_clipboard is not None:
            time.sleep(CLIPBOARD_RESTORE_DELAY_SECONDS)
            try:
                set_clipboard(old_clipboard)
                log_event("dialog-step clipboard-restored")
            except AutomationError:
                pass


def active_window_is_file_dialog() -> bool:
    try:
        with ACTIVE_WINDOW_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        log_event("auto-dialog state=missing")
        return False

    try:
        timestamp = datetime.fromisoformat(str(data.get("timestamp", "")))
        age = (datetime.now().astimezone() - timestamp).total_seconds()
    except ValueError:
        log_event("auto-dialog state=invalid-timestamp")
        return False

    if age > ACTIVE_WINDOW_MAX_AGE_SECONDS:
        log_event(f"auto-dialog state=stale age={age:.1f}")
        return False

    is_file_dialog = bool(data.get("is_file_dialog"))
    caption = str(data.get("caption", ""))
    resource_class = str(data.get("resource_class", ""))
    window_type = str(data.get("window_type", ""))
    log_event(
        "auto-dialog "
        f"state={'file-dialog' if is_file_dialog else 'normal'} "
        f"caption={caption!r} class={resource_class!r} type={window_type!r}"
    )
    return is_file_dialog


def main() -> int:
    auto_mode = False
    dialog_mode = False
    args = sys.argv[1:]
    if args and args[0] == "--auto":
        auto_mode = True
        args = args[1:]
    if args and args[0] == "--dialog":
        dialog_mode = True
        args = args[1:]

    if len(args) != 1:
        print("Usage: open-configured-target.py [--auto|--dialog] F1", file=sys.stderr)
        return 2

    key = canonical_shortcut(args[0])
    target = load_config().get(key, "").strip()
    if not target:
        return 0

    normalized = normalize_target(target)
    if auto_mode and Path(normalized).is_dir() and active_window_is_file_dialog():
        dialog_mode = True

    if dialog_mode:
        if not Path(normalized).is_dir():
            return 0
        log_invocation(key, normalized, "auto-dialog" if auto_mode else "dialog")
        try:
            settle_seconds = (
                AUTO_DIALOG_TRIGGER_SETTLE_SECONDS
                if auto_mode
                else EXPLICIT_DIALOG_TRIGGER_SETTLE_SECONDS
            )
            open_in_file_dialog(normalized, settle_seconds)
        except AutomationError as exc:
            notify(str(exc))
            return 1
        return 0

    log_invocation(key, normalized, "open")
    subprocess.Popen(["xdg-open", normalized], start_new_session=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
