#!/usr/bin/env python3
"""Small KDE tray helper for local Wayland automation actions."""

from __future__ import annotations

import argparse
import json
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
CONFIG_FILE = Path.home() / ".config/wayland-automation/shortcuts.json"
OPEN_CONFIGURED_TARGET = SCRIPT_DIR / "open-configured-target.py"
FUNCTION_KEYS = [f"F{number}" for number in range(1, 12)]
MODIFIER_OPTIONS = ["", "Alt", "Ctrl", "Meta", "Shift", "Ctrl+Alt", "Meta+Alt"]
MODIFIER_CODES = {
    "Alt": 0x08000000,
    "Ctrl": 0x04000000,
    "Meta": 0x10000000,
    "Shift": 0x02000000,
}
QT_KEY_F1 = 16777264
QT_KEY_HELP = 16777304


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
    number = int(function_key[1:])
    modifier_code = modifier_value(modifier)
    codes = [modifier_code | (QT_KEY_F1 + number - 1)]
    if function_key == "F1" and not modifier:
        codes.append(QT_KEY_HELP)
    return codes


def run_detached(command: list[str]) -> None:
    subprocess.Popen(command, start_new_session=True)


def notify(title: str, message: str) -> None:
    if shutil.which("notify-send"):
        run_detached(["notify-send", title, message])


def load_shortcuts() -> dict[str, str]:
    if not CONFIG_FILE.exists():
        return {"F1": "/home/jakob/Downloads/"}
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


def desktop_id_for(shortcut: str) -> str:
    safe = shortcut.lower().replace("+", "-")
    return f"wayland-automation-configured-{safe}.desktop"


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
                f"Comment=Open configured Wayland Automation target for {shortcut}",
                f"Exec={OPEN_CONFIGURED_TARGET} {shortcut}",
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


def run_checked(command: list[str]) -> None:
    subprocess.run(command, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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
    configured = set(shortcuts)
    for modifier in MODIFIER_OPTIONS:
        for function_key in FUNCTION_KEYS:
            shortcut = shortcut_label(modifier, function_key)
            target = shortcuts.get(shortcut, "").strip()
            if target:
                register_shortcut(shortcut, target)
            elif shortcut not in configured:
                unregister_shortcut(shortcut)


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
        menu.append(make_item("Konfiguration...", self.show_configuration))
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

    def show_configuration(self, _item: Gtk.MenuItem) -> None:
        dialog = ShortcutConfigDialog(load_shortcuts())
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            shortcuts = dialog.shortcuts()
            save_shortcuts(shortcuts)
            apply_shortcuts(shortcuts)
            notify("Wayland Automation", "Shortcuts gespeichert.")
        dialog.destroy()

    def quit(self, _item: Gtk.MenuItem) -> None:
        Gtk.main_quit()


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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.apply_shortcuts:
        apply_shortcuts(load_shortcuts())
        return 0

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
