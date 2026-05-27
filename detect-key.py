#!/usr/bin/env python3
"""Show and log key presses seen by a focused GTK window."""

from __future__ import annotations

import os
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402


LOG_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
LOG_FILE = LOG_DIR / "wayland-automation" / "key-detect.log"


class KeyDetectWindow(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(title="Key Detect")
        self.set_default_size(420, 120)
        self.set_border_width(16)
        self.label = Gtk.Label(
            label="Click this window, press F1, then close it.\nWaiting for key..."
        )
        self.add(self.label)
        self.connect("key-press-event", self.on_key_press)
        self.connect("destroy", Gtk.main_quit)

    def on_key_press(self, _widget, event) -> bool:
        key_name = Gdk.keyval_name(event.keyval) or "unknown"
        line = (
            f"keyval={event.keyval} name={key_name} hardware_keycode="
            f"{event.hardware_keycode} state={int(event.state)}"
        )
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        self.label.set_text(line)
        return False


def main() -> int:
    window = KeyDetectWindow()
    window.show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
