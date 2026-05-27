#!/usr/bin/env python3
"""Small KDE tray helper for local Wayland automation actions."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AppIndicator3", "0.1")
from gi.repository import AppIndicator3, Gtk  # noqa: E402


APP_ID = "wayland-automation"
SCRIPT_DIR = Path(__file__).resolve().parent
OPEN_DOWNLOADS = SCRIPT_DIR / "open-downloads.sh"
CLICK_IMAGE = SCRIPT_DIR / "wayland-click-image.py"
DEFAULT_TEMPLATE = Path.home() / "Pictures/button-templates/resolve-render.png"
DEFAULT_YDOTOOL_SOCKET = "/tmp/ydotool_socket"


def run_detached(command: list[str]) -> None:
    subprocess.Popen(command, start_new_session=True)


def notify(title: str, message: str) -> None:
    if shutil.which("notify-send"):
        run_detached(["notify-send", title, message])


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


def make_item(label: str, callback) -> Gtk.MenuItem:
    item = Gtk.MenuItem(label=label)
    item.connect("activate", callback)
    item.show()
    return item


class AutomationTray:
    def __init__(self, template: Path, ydotool_socket: str | None) -> None:
        self.template = template
        self.ydotool_socket = ydotool_socket
        self.indicator = AppIndicator3.Indicator.new(
            APP_ID,
            "input-mouse",
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_title("Wayland Automation")
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_menu(self.build_menu())

    def build_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()

        menu.append(make_item("Downloads öffnen", self.open_downloads))
        menu.append(make_item("Button-Template klicken", self.click_template))
        menu.append(make_item("ydotool prüfen", self.show_ydotool_status))

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
                "Wayland Automation",
                f"Template fehlt: {self.template}",
            )
            return
        command = [str(CLICK_IMAGE), str(self.template)]
        if self.ydotool_socket:
            command.extend(["--ydotool-socket", self.ydotool_socket])
        run_detached(command)

    def show_ydotool_status(self, _item: Gtk.MenuItem) -> None:
        notify("Wayland Automation", check_ydotool(self.ydotool_socket))

    def quit(self, _item: Gtk.MenuItem) -> None:
        Gtk.main_quit()


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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.check:
        print("GTK/AppIndicator imports: ok")
        print(f"open downloads script: {OPEN_DOWNLOADS}")
        print(f"click image script: {CLICK_IMAGE}")
        print(f"template: {args.template}")
        print(f"ydotool socket: {args.ydotool_socket}")
        print(f"ydotool: {check_ydotool(args.ydotool_socket)}")
        return 0

    AutomationTray(args.template.expanduser(), args.ydotool_socket)
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
