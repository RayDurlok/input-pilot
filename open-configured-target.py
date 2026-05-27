#!/usr/bin/env python3
"""Open a configured target for a function key."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


CONFIG_FILE = Path.home() / ".config/wayland-automation/shortcuts.json"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
LOG_FILE = STATE_DIR / "wayland-automation/configured-shortcuts.log"


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


def log_invocation(key: str, target: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} key={key} target={target} pid={os.getpid()}\n")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: open-configured-target.py F1", file=sys.stderr)
        return 2

    key = canonical_shortcut(sys.argv[1])
    target = load_config().get(key, "").strip()
    if not target:
        return 0

    normalized = normalize_target(target)
    log_invocation(key, normalized)
    subprocess.Popen(["xdg-open", normalized], start_new_session=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
