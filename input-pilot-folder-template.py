#!/usr/bin/env python3
"""Create folders from configured templates in the active Dolphin directory."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402


CONFIG_FILE = Path.home() / ".config/wayland-automation/folder-templates.json"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
LOG_FILE = STATE_DIR / "wayland-automation/folder-template.log"
ACTIVE_WINDOW_FILE = STATE_DIR / "wayland-automation/active-window.json"
DEFAULT_TEMPLATE_FOLDER = Path.home() / "Templates/Input Pilot Folder Template"
DEFAULT_YDOTOOL_SOCKET = "/tmp/ydotool_socket"
TRIGGER_SETTLE_SECONDS = 0.25
LOCATION_FOCUS_SECONDS = 0.12
CLIPBOARD_SETTLE_SECONDS = 0.1


def log(message: str) -> None:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {message}\n")
    except OSError:
        return


def notify(message: str) -> None:
    if shutil.which("notify-send"):
        subprocess.Popen(
            ["notify-send", "Input Pilot", message],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def load_templates() -> list[dict[str, str]]:
    default = [
        {
            "name": "Project Template",
            "shortcut": "Ctrl+N",
            "template": str(DEFAULT_TEMPLATE_FOLDER),
            "default_name": "New Project",
        }
    ]
    if not CONFIG_FILE.exists():
        return default
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        log(f"could not load config: {exc}")
        return default
    if not isinstance(data, list):
        return default

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
                "shortcut": str(item.get("shortcut", "")).strip(),
                "template": template,
                "default_name": str(item.get("default_name", "")).strip()
                or "New Project",
            }
        )
    return templates or default


def active_window_pid() -> int | None:
    try:
        with ACTIVE_WINDOW_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    haystack = " ".join(
        str(data.get(key, ""))
        for key in ("caption", "resource_class", "resource_name")
    ).lower()
    if "dolphin" not in haystack:
        return None
    try:
        pid = int(data.get("window_pid", 0))
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def run_command(command: list[str], timeout: float = 2.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )


def dolphin_services() -> list[str]:
    result = run_command(["busctl", "--user", "list"], timeout=2)
    if result.returncode != 0:
        return []
    services = []
    for line in result.stdout.splitlines():
        match = re.search(r"\borg\.kde\.dolphin-\d+\b", line)
        if match:
            services.append(match.group(0))
    return sorted(set(services))


def service_for_active_dolphin() -> str | None:
    pid = active_window_pid()
    if pid:
        service = f"org.kde.dolphin-{pid}"
        if service in dolphin_services():
            return service

    for service in dolphin_services():
        result = run_command(
            [
                "busctl",
                "--user",
                "call",
                service,
                "/dolphin/Dolphin_1",
                "org.kde.dolphin.MainWindow",
                "isActiveWindow",
            ],
            timeout=1,
        )
        if result.returncode == 0 and "true" in result.stdout.lower():
            return service
    return None


def clipboard_text() -> str | None:
    result = run_command(["wl-paste", "--no-newline"], timeout=1)
    if result.returncode != 0:
        return None
    return result.stdout


def set_clipboard(text: str) -> None:
    try:
        subprocess.run(
            ["wl-copy"],
            input=text,
            text=True,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=1,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return


def ydotool_key(*events: str) -> None:
    env = dict(os.environ)
    env.setdefault("YDOTOOL_SOCKET", DEFAULT_YDOTOOL_SOCKET)
    result = subprocess.run(
        ["ydotool", "key", *events],
        env=env,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=2,
    )
    if result.returncode != 0:
        raise RuntimeError("ydotool could not send a key.")


def path_from_clipboard_location(text: str) -> Path:
    first_line = text.splitlines()[0].strip()
    parsed = urlparse(first_line)
    if parsed.scheme == "file":
        return Path(unquote(parsed.path))
    return Path(first_line).expanduser()


def activate_dolphin_action(service: str, action: str) -> bool:
    result = run_command(
        [
            "busctl",
            "--user",
            "call",
            service,
            "/dolphin/Dolphin_1",
            "org.kde.KMainWindow",
            "activateAction",
            "s",
            action,
        ],
        timeout=2,
    )
    return result.returncode == 0 and "true" in result.stdout.lower()


def location_from_dolphin_bar(service: str) -> Path:
    old_clipboard = clipboard_text()
    time.sleep(TRIGGER_SETTLE_SECONDS)

    if not activate_dolphin_action(service, "replace_location"):
        activate_dolphin_action(service, "editable_location")

    time.sleep(LOCATION_FOCUS_SECONDS)
    try:
        ydotool_key("29:1", "30:1", "30:0", "29:0")
        ydotool_key("29:1", "46:1", "46:0", "29:0")
        ydotool_key("1:1", "1:0")
        time.sleep(CLIPBOARD_SETTLE_SECONDS)
        copied = clipboard_text()
    finally:
        if old_clipboard is not None:
            set_clipboard(old_clipboard)

    if not copied:
        raise RuntimeError("Dolphin location is empty.")
    return path_from_clipboard_location(copied)


def active_dolphin_directory() -> Path:
    service = service_for_active_dolphin()
    if not service:
        raise RuntimeError("No active Dolphin window found.")

    directory = location_from_dolphin_bar(service)
    if not directory.is_dir():
        raise RuntimeError(f"Current Dolphin location is not a folder: {directory}")
    return directory


def prompt_folder_name(default_name: str, parent: Path) -> str | None:
    dialog = Gtk.Dialog(title="Create Folder Template", modal=True)
    dialog.set_border_width(10)
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("Create", Gtk.ResponseType.OK)

    content = dialog.get_content_area()
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    content.add(outer)

    label = Gtk.Label(label=f"New folder in:\n{parent}")
    label.set_xalign(0)
    outer.pack_start(label, False, False, 0)

    entry = Gtk.Entry()
    entry.set_text(default_name)
    entry.set_activates_default(True)
    outer.pack_start(entry, False, False, 0)
    dialog.set_default_response(Gtk.ResponseType.OK)

    dialog.show_all()
    entry.grab_focus()
    entry.select_region(0, -1)
    response = dialog.run()
    name = entry.get_text().strip()
    dialog.destroy()
    if response != Gtk.ResponseType.OK:
        return None
    if not name or "/" in name or "\0" in name:
        raise RuntimeError("Invalid folder name.")
    return name


def create_from_template(template_config: dict[str, str]) -> Path:
    template = Path(template_config["template"]).expanduser()
    if not template.is_dir():
        raise RuntimeError(f"Template folder is missing: {template}")

    parent = active_dolphin_directory()
    if str(template_config.get("shortcut", "")).strip().lower() == "ctrl+n":
        service = service_for_active_dolphin()
        if service:
            activate_dolphin_action(service, "toggle_selection_mode")

    name = prompt_folder_name(template_config.get("default_name", "New Project"), parent)
    if name is None:
        raise RuntimeError("Cancelled.")

    destination = parent / name
    if destination.exists():
        raise RuntimeError(f"Target folder already exists: {destination}")

    shutil.copytree(template, destination, symlinks=True)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a folder from an Input Pilot template")
    parser.add_argument("--index", type=int, default=1)
    args = parser.parse_args()

    templates = load_templates()
    if args.index < 1 or args.index > len(templates):
        notify(f"Folder Template {args.index} does not exist.")
        return 1

    template = templates[args.index - 1]
    try:
        destination = create_from_template(template)
    except RuntimeError as exc:
        log(str(exc))
        if str(exc) != "Cancelled.":
            notify(str(exc))
        return 1

    log(f"created folder template index={args.index} destination={destination}")
    notify(f"Folder created: {destination.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
