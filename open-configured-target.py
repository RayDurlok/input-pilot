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
PAUSE_FILE = STATE_DIR / "wayland-automation/paused"
DEFAULT_YDOTOOL_SOCKET = "/tmp/ydotool_socket"
AUTO_DIALOG_TRIGGER_SETTLE_SECONDS = 0.08
EXPLICIT_DIALOG_TRIGGER_SETTLE_SECONDS = 0.35
LOCATION_FOCUS_DELAY_SECONDS = 0.1
NEW_TAB_SETTLE_SECONDS = 0.18
PASTE_SETTLE_DELAY_SECONDS = 0.08
CLIPBOARD_RESTORE_DELAY_SECONDS = 0.7
# Dolphin's location bar is local and instant, so it needs far less settling
# than a (possibly network/portal) file dialog. These keep the folder hotkeys
# snappy while the conservative values above stay for the dialog flow.
DOLPHIN_TRIGGER_SETTLE_SECONDS = 0.05
DOLPHIN_FOCUS_DELAY_SECONDS = 0.04
DOLPHIN_PASTE_SETTLE_SECONDS = 0.03
DOLPHIN_CLIPBOARD_RESTORE_DELAY_SECONDS = 0.12
DOLPHIN_NEW_TAB_SETTLE_SECONDS = 0.12
ACTIVE_WINDOW_MAX_AGE_SECONDS = 6 * 60 * 60
SHORTCUT_OPTIONS_KEY = "_options"
FOLDER_OPEN_MODE_DEFAULT = "default"
FOLDER_OPEN_MODE_ACTIVE_DOLPHIN = "active-dolphin-window"
FOLDER_OPEN_MODE_NEW_DOLPHIN_TAB = "new-dolphin-tab"
FOLDER_OPEN_MODES = {
    FOLDER_OPEN_MODE_DEFAULT,
    FOLDER_OPEN_MODE_ACTIVE_DOLPHIN,
    FOLDER_OPEN_MODE_NEW_DOLPHIN_TAB,
}


class AutomationError(RuntimeError):
    pass


def is_paused() -> bool:
    return PAUSE_FILE.exists()


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


def load_config_data() -> dict[str, object]:
    if not CONFIG_FILE.exists():
        return {}
    with CONFIG_FILE.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {}
    return data


def target_from_config_value(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("target", "")).strip()
    return ""


def load_config() -> dict[str, str]:
    data = load_config_data()
    return {
        canonical_shortcut(str(key)): target
        for key, value in data.items()
        if not str(key).startswith("_")
        if canonical_shortcut(str(key))
        for target in (target_from_config_value(value),)
        if target
    }


def load_folder_open_mode(data: dict[str, object]) -> str:
    options = data.get(SHORTCUT_OPTIONS_KEY)
    if not isinstance(options, dict):
        return FOLDER_OPEN_MODE_DEFAULT
    mode = str(options.get("folder_open_mode", FOLDER_OPEN_MODE_DEFAULT)).strip()
    return mode if mode in FOLDER_OPEN_MODES else FOLDER_OPEN_MODE_DEFAULT


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
            ["notify-send", "Input Pilot", message],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


# MIME types that wl-copy auto-derives from a text source. They are never worth
# preserving on their own, because re-offering any single type brings them back.
_TEXT_ALIAS_TYPES = {
    "text/plain",
    "text/plain;charset=utf-8",
    "text/plain;charset=us-ascii",
    "utf8_string",
    "string",
    "text",
}


def _is_clipboard_marker(mime: str) -> bool:
    """True for KDE/Klipper hint types (e.g. ``application/x-kde-cutselection``,
    ``application/x-kde-onlyReplaceEmpty``) that carry no real clipboard payload.
    Saving/restoring one of these as the clipboard wipes the actual content."""
    return mime.lower().startswith("application/x-kde-")


def _pick_clipboard_type(types: list[str]) -> str | None:
    """Pick the single richest MIME type to preserve from a clipboard offer.

    wl-copy can only serve one explicit type (it still auto-adds the text
    aliases), so we keep the most meaningful one. ``text/uri-list`` is
    prioritised so that copied files survive a save/restore round-trip; without
    it the restore would drop the file list and only leave plain text behind.
    """

    def first(name: str) -> str | None:
        for candidate in types:
            if candidate.lower() == name:
                return candidate
        return None

    uri_list = first("text/uri-list")
    if uri_list:
        return uri_list
    for candidate in types:  # any image (png, jpeg, …)
        if candidate.lower().startswith("image/"):
            return candidate
    for candidate in types:  # any other non-text, non-marker payload
        lowered = candidate.lower()
        if lowered in _TEXT_ALIAS_TYPES or _is_clipboard_marker(lowered):
            continue
        return candidate
    for preferred in ("text/plain;charset=utf-8", "utf8_string", "text/plain"):
        match = first(preferred)
        if match:
            return match
    # Only text aliases and/or KDE hint markers remain; never return a marker
    # (that would restore an empty clipboard), fall back to any real type.
    for candidate in types:
        if not _is_clipboard_marker(candidate.lower()):
            return candidate
    return None


def save_clipboard() -> tuple[str, bytes] | None:
    """Capture the clipboard as (mime_type, raw_bytes) preserving its real type."""
    try:
        listing = subprocess.run(
            ["wl-paste", "--list-types"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if listing.returncode != 0:
        return None
    types = [line.strip() for line in listing.stdout.splitlines() if line.strip()]
    mime = _pick_clipboard_type(types)
    if mime is None:
        return None
    try:
        data = subprocess.run(
            ["wl-paste", "--no-newline", "--type", mime],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=1,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if data.returncode != 0:
        return None
    return mime, data.stdout


def restore_clipboard(saved: tuple[str, bytes]) -> None:
    mime, data = saved
    try:
        subprocess.run(
            ["wl-copy", "--type", mime],
            input=data,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass


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
        raise AutomationError("wl-copy is not installed.") from exc
    except subprocess.CalledProcessError as exc:
        raise AutomationError("wl-copy could not place the path on the clipboard.") from exc


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
        raise AutomationError("ydotool is not installed.") from exc
    except subprocess.TimeoutExpired as exc:
        raise AutomationError("ydotool did not respond within 2 seconds.") from exc
    if result.returncode != 0:
        detail = result.stdout.strip()
        if detail:
            log_event(f"ydotool-error output={detail!r}")
        raise AutomationError(
            f"ydotool is not reachable. Socket: {env.get('YDOTOOL_SOCKET')}"
        )


def drive_location_bar(
    directory: str,
    trigger_settle_seconds: float,
    *,
    new_tab: bool = False,
    log_prefix: str = "dialog-step",
    focus_delay: float = LOCATION_FOCUS_DELAY_SECONDS,
    paste_settle: float = PASTE_SETTLE_DELAY_SECONDS,
    restore_delay: float = CLIPBOARD_RESTORE_DELAY_SECONDS,
    new_tab_settle: float = NEW_TAB_SETTLE_SECONDS,
) -> None:
    """Type ``directory`` into the focused window's location bar and confirm.

    Works for KDE/GTK file dialogs and for Dolphin (Ctrl+L = "Replace Location").
    With ``new_tab`` a Ctrl+T is sent first so Dolphin opens a fresh tab before
    the path is entered. The delays default to the conservative file-dialog
    values; the Dolphin path overrides them with much shorter ones since its
    location bar is local and instant.
    """
    old_clipboard = save_clipboard()
    try:
        set_clipboard(directory)
        log_event(f"{log_prefix} clipboard-set target={directory}")
        # Global shortcuts fire before the physical modifier keys are always up.
        time.sleep(trigger_settle_seconds)
        if new_tab:
            # Ctrl+T opens a new Dolphin tab to receive the path.
            ydotool_key("29:1", "20:1", "20:0", "29:0")
            log_event(f"{log_prefix} sent=ctrl+t")
            time.sleep(new_tab_settle)
        # Ctrl+L focuses the location field in common KDE/GTK file dialogs.
        ydotool_key("29:1", "38:1", "38:0", "29:0")
        log_event(f"{log_prefix} sent=ctrl+l")
        time.sleep(focus_delay)
        ydotool_key("29:1", "30:1", "30:0", "29:0")
        log_event(f"{log_prefix} sent=ctrl+a")
        ydotool_key("29:1", "47:1", "47:0", "29:0")
        log_event(f"{log_prefix} sent=ctrl+v")
        time.sleep(paste_settle)
        ydotool_key("28:1", "28:0")
        log_event(f"{log_prefix} sent=enter")
    finally:
        if old_clipboard is not None:
            time.sleep(restore_delay)
            restore_clipboard(old_clipboard)
            log_event(f"{log_prefix} clipboard-restored type={old_clipboard[0]}")


def open_in_file_dialog(directory: str, trigger_settle_seconds: float) -> None:
    drive_location_bar(directory, trigger_settle_seconds)


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


def active_window_is_dolphin() -> bool:
    """True when the most recently focused window is a Dolphin window.

    Dolphin exposes no D-Bus method to change the current view's URL, so the
    Dolphin folder modes drive the *focused* window's location bar instead. That
    only makes sense when Dolphin actually holds the focus.
    """
    try:
        with ACTIVE_WINDOW_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return False
    haystack = " ".join(
        str(data.get(key, ""))
        for key in ("caption", "resource_class", "resource_name")
    ).lower()
    return "dolphin" in haystack


def open_folder_target(directory: str, folder_open_mode: str) -> None:
    if folder_open_mode == FOLDER_OPEN_MODE_DEFAULT:
        subprocess.Popen(["xdg-open", directory], start_new_session=True)
        return

    # The Dolphin modes navigate the focused window via its location bar
    # (Ctrl+L); fall back to a fresh window when Dolphin is not in front.
    if not active_window_is_dolphin():
        log_event(f"dolphin-open fallback reason=no-active-dolphin mode={folder_open_mode}")
        subprocess.Popen(["xdg-open", directory], start_new_session=True)
        return

    new_tab = folder_open_mode == FOLDER_OPEN_MODE_NEW_DOLPHIN_TAB
    try:
        drive_location_bar(
            directory,
            DOLPHIN_TRIGGER_SETTLE_SECONDS,
            new_tab=new_tab,
            log_prefix="dolphin-step",
            focus_delay=DOLPHIN_FOCUS_DELAY_SECONDS,
            paste_settle=DOLPHIN_PASTE_SETTLE_SECONDS,
            restore_delay=DOLPHIN_CLIPBOARD_RESTORE_DELAY_SECONDS,
            new_tab_settle=DOLPHIN_NEW_TAB_SETTLE_SECONDS,
        )
        log_event(f"dolphin-open mode={folder_open_mode} via=location-bar new_tab={new_tab}")
    except AutomationError as exc:
        log_event(f"dolphin-open failed mode={folder_open_mode} exc={exc!r}")
        subprocess.Popen(["xdg-open", directory], start_new_session=True)


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

    if is_paused():
        log_event(f"paused skip key={args[0]}")
        return 0

    config_data = load_config_data()
    folder_open_mode = load_folder_open_mode(config_data)
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

    log_invocation(key, normalized, f"open:{folder_open_mode}")
    if Path(normalized).is_dir():
        open_folder_target(normalized, folder_open_mode)
    else:
        subprocess.Popen(["xdg-open", normalized], start_new_session=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
