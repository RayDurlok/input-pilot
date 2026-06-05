#!/usr/bin/env python3
"""Run configured Input Pilot mouse template sequences."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_SERVER = SCRIPT_DIR / "input-pilot-template-server.py"
CLICK_SCRIPT = SCRIPT_DIR / "wayland-click-image.py"
CONFIG_FILE = Path.home() / ".config/wayland-automation/mousemove-sequence.json"
DEFAULT_YDOTOOL_SOCKET = "/tmp/ydotool_socket"
MODIFIER_KEY_CODES = {
    "CTRL": 29,
    "CONTROL": 29,
    "ALT": 56,
    "SHIFT": 42,
    "META": 125,
    "SUPER": 125,
}
KEY_CODES = {
    "A": 30,
    "B": 48,
    "C": 46,
    "D": 32,
    "E": 18,
    "F": 33,
    "G": 34,
    "H": 35,
    "I": 23,
    "J": 36,
    "K": 37,
    "L": 38,
    "M": 50,
    "N": 49,
    "O": 24,
    "P": 25,
    "Q": 16,
    "R": 19,
    "S": 31,
    "T": 20,
    "U": 22,
    "V": 47,
    "W": 17,
    "X": 45,
    "Y": 21,
    "Z": 44,
    **{str(number): code for number, code in zip(range(1, 10), range(2, 11))},
    "0": 11,
    **{f"F{number}": 58 + number for number in range(1, 11)},
    "F11": 87,
    "F12": 88,
    "SPACE": 57,
    "TAB": 15,
    "ENTER": 28,
    "RETURN": 28,
    "ESC": 1,
    "ESCAPE": 1,
    "LEFT": 105,
    "RIGHT": 106,
    "UP": 103,
    "DOWN": 108,
    "HOME": 102,
    "END": 107,
    "PAGEUP": 104,
    "PAGEDOWN": 109,
    "INSERT": 110,
    "DELETE": 111,
    "BACKSPACE": 14,
}


def load_click_module():
    spec = importlib.util.spec_from_file_location("input_pilot_click_image", CLICK_SCRIPT)
    if not spec or not spec.loader:
        raise SystemExit(f"Could not load click script: {CLICK_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_automation(config_file: Path, index: int) -> dict[str, object]:
    if not config_file.exists():
        return {"name": "Automation", "debug": False, "steps": []}
    with config_file.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        automations = data.get("automations")
        if isinstance(automations, list):
            if index < 1 or index > len(automations):
                raise SystemExit(f"Automation index out of range: {index}")
            automation = automations[index - 1]
            if not isinstance(automation, dict):
                raise SystemExit(f"Automation index is invalid: {index}")
            return automation
        else:
            return data
    if isinstance(data, list):
        return {"name": "Automation", "debug": False, "steps": data}
    raise SystemExit(f"Mousemove config must contain automations or steps: {config_file}")


def load_steps(config_file: Path, index: int) -> list[dict[str, object]]:
    data = load_automation(config_file, index).get("steps", [])
    if not isinstance(data, list):
        raise SystemExit(f"Mousemove config must contain a steps array: {config_file}")
    return [item for item in data if isinstance(item, dict)]


def notify_debug(enabled: bool, message: str) -> None:
    if not enabled or not shutil.which("notify-send"):
        return
    subprocess.run(["notify-send", "Input Pilot Debug", message], check=False)


def result_text(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(
        part.strip()
        for part in (result.stdout or "", result.stderr or "")
        if part and part.strip()
    )


def run_template_command(
    command: list[str],
    debug: bool,
    not_found_message: str,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode == 0:
        return result

    output = result_text(result)
    if "Match below threshold" in output:
        notify_debug(debug, not_found_message)
    elif output:
        notify_debug(debug, output.splitlines()[-1])
    else:
        notify_debug(debug, f"Command failed: {' '.join(command)}")
    return result


def step_command(step: dict[str, object], ydotool_socket: str | None) -> list[str]:
    template = str(step.get("template", "")).strip()
    if not template:
        raise SystemExit("Mousemove step is missing a template path")
    template_path = Path(template).expanduser()
    if not template_path.is_file():
        raise SystemExit(f"Template image not found: {template_path}")

    click = str(step.get("click", "left")).strip().lower()
    command = [str(TEMPLATE_SERVER), str(template_path), "--no-return-cursor"]
    if click == "hover":
        wait_seconds = float(step.get("wait", 0.0) or 0.0)
        command.extend(["--move-only", "--hold", str(max(wait_seconds, 0.25))])
    elif click == "right":
        command.extend(["--button", "right"])
    elif click == "double-left":
        command.extend(["--button", "left", "--double-click"])
    elif click == "left":
        command.extend(["--button", "left"])
    else:
        raise SystemExit(f"Unknown click type: {click}")

    if ydotool_socket:
        command.extend(["--ydotool-socket", ydotool_socket])
    return command


def move_to_template_command(template: str, ydotool_socket: str | None) -> list[str]:
    template_path = Path(template).expanduser()
    if not template_path.is_file():
        raise SystemExit(f"Template image not found: {template_path}")
    command = [str(TEMPLATE_SERVER), str(template_path), "--no-return-cursor", "--move-only"]
    if ydotool_socket:
        command.extend(["--ydotool-socket", ydotool_socket])
    return command


def run_ydotool(arguments: list[str], socket_path: str | None) -> None:
    command = ["ydotool", *arguments]
    env = None
    if socket_path:
        import os

        env = dict(os.environ, YDOTOOL_SOCKET=socket_path)
    subprocess.run(command, check=True, env=env)


def type_string(text: str, ydotool_socket: str | None) -> None:
    if not text:
        raise SystemExit("Input string node is empty")
    run_ydotool(["type", "--key-delay=0", "--key-hold=1", "--", text], ydotool_socket)


def send_key_combo(combo: str, ydotool_socket: str | None) -> None:
    parts = [part.strip().upper() for part in combo.split("+") if part.strip()]
    if not parts:
        raise SystemExit("Key combo node is empty")
    key_name = parts[-1]
    modifier_codes = []
    for modifier in parts[:-1]:
        if modifier not in MODIFIER_KEY_CODES:
            raise SystemExit(f"Unsupported key combo modifier: {modifier}")
        modifier_codes.append(MODIFIER_KEY_CODES[modifier])
    if key_name not in KEY_CODES:
        raise SystemExit(f"Unsupported key combo key: {key_name}")

    key_code = KEY_CODES[key_name]
    events = [f"{code}:1" for code in modifier_codes]
    events.append(f"{key_code}:1")
    events.append(f"{key_code}:0")
    events.extend(f"{code}:0" for code in reversed(modifier_codes))
    run_ydotool(["key", *events], ydotool_socket)


def run_drag_step(step: dict[str, object], ydotool_socket: str | None, debug: bool) -> int:
    source = str(step.get("template", "")).strip()
    target = str(step.get("target", "")).strip()
    if not source:
        notify_debug(debug, "Source screenshot/template is empty.")
        raise SystemExit("Drag step is missing a source template path")
    if not target:
        notify_debug(debug, "Target screenshot/template is empty.")
        raise SystemExit("Drag step is missing a target template path")

    source_path = Path(source).expanduser()
    target_path = Path(target).expanduser()
    if not source_path.is_file():
        notify_debug(debug, f"Source screenshot/template file does not exist: {source_path}")
        raise SystemExit(f"Template image not found: {source_path}")
    if not target_path.is_file():
        notify_debug(debug, f"Target screenshot/template file does not exist: {target_path}")
        raise SystemExit(f"Template image not found: {target_path}")

    source_result = run_template_command(
        move_to_template_command(source, ydotool_socket),
        debug,
        "Source screenshot couldn't be found on screen.",
    )
    if source_result.returncode != 0:
        return source_result.returncode

    try:
        run_ydotool(["click", "0x40"], ydotool_socket)
        target_result = run_template_command(
            move_to_template_command(target, ydotool_socket),
            debug,
            "Target screenshot couldn't be found on screen.",
        )
        return target_result.returncode
    finally:
        run_ydotool(["click", "0x80"], ydotool_socket)


def run_drag_to_position_step(
    step: dict[str, object],
    ydotool_socket: str | None,
    debug: bool,
    click_module,
) -> int:
    source = str(step.get("template", "")).strip()
    if not source:
        notify_debug(debug, "Source screenshot/template is empty.")
        raise SystemExit("Drag-to-position step is missing a source template path")
    source_path = Path(source).expanduser()
    if not source_path.is_file():
        notify_debug(debug, f"Source screenshot/template file does not exist: {source_path}")
        raise SystemExit(f"Template image not found: {source_path}")

    try:
        x = int(float(step.get("x", 0) or 0))
        y = int(float(step.get("y", 0) or 0))
    except (TypeError, ValueError) as exc:
        notify_debug(debug, "Drag-to-position node has invalid coordinates.")
        raise SystemExit("Drag-to-position node has invalid coordinates") from exc

    source_result = run_template_command(
        move_to_template_command(source, ydotool_socket),
        debug,
        "Source screenshot couldn't be found on screen.",
    )
    if source_result.returncode != 0:
        return source_result.returncode

    try:
        run_ydotool(["click", "0x40"], ydotool_socket)
        current_position = click_module.read_cursor_position()
        click_module.move_cursor_to(
            x,
            y,
            ydotool_socket,
            verify=False,
            initial_position=current_position,
        )
        return 0
    finally:
        run_ydotool(["click", "0x80"], ydotool_socket)


def run_sequence(config_file: Path, ydotool_socket: str | None, index: int) -> int:
    automation = load_automation(config_file, index)
    debug = bool(automation.get("debug", False))
    steps = load_steps(config_file, index)
    if not steps:
        notify_debug(debug, "No mousemove nodes are configured.")
        raise SystemExit(f"No mousemove steps configured: {config_file}")

    click_module = load_click_module()
    original_position = click_module.read_cursor_position()
    exit_code = 0
    try:
        for step_index, step in enumerate(steps, start=1):
            click = str(step.get("click", "left")).strip().lower()
            if click == "drag":
                print(f"step {step_index}: drag")
                exit_code = run_drag_step(step, ydotool_socket, debug)
                if exit_code != 0:
                    break
            elif click == "drag-position":
                print(f"step {step_index}: drag to position")
                exit_code = run_drag_to_position_step(
                    step,
                    ydotool_socket,
                    debug,
                    click_module,
                )
                if exit_code != 0:
                    break
            elif click == "keys":
                combo = str(step.get("keys", "")).strip()
                print(f"step {step_index}: keys {combo}")
                try:
                    send_key_combo(combo, ydotool_socket)
                except SystemExit as exc:
                    notify_debug(debug, str(exc))
                    raise
            elif click == "text":
                text = str(step.get("text", ""))
                print(f"step {step_index}: text")
                try:
                    type_string(text, ydotool_socket)
                except SystemExit as exc:
                    notify_debug(debug, str(exc))
                    raise
            elif click == "position":
                try:
                    x = int(float(step.get("x", 0) or 0))
                    y = int(float(step.get("y", 0) or 0))
                except (TypeError, ValueError) as exc:
                    notify_debug(debug, "Mouse position node has invalid coordinates.")
                    raise SystemExit("Mouse position node has invalid coordinates") from exc
                print(f"step {step_index}: move {x},{y}")
                current_position = click_module.read_cursor_position()
                click_module.move_cursor_to(
                    x,
                    y,
                    ydotool_socket,
                    verify=False,
                    initial_position=current_position,
                )
            elif click == "previous-position":
                print(f"step {step_index}: previous mouse position")
                current_position = click_module.read_cursor_position()
                click_module.move_cursor_to(
                    original_position.x,
                    original_position.y,
                    ydotool_socket,
                    verify=False,
                    initial_position=current_position,
                )
            else:
                try:
                    command = step_command(step, ydotool_socket)
                except SystemExit as exc:
                    notify_debug(debug, str(exc))
                    raise
                print(f"step {step_index}: {' '.join(command)}")
                result = run_template_command(
                    command,
                    debug,
                    "Screenshot couldn't be found on screen.",
                )
                if result.returncode != 0:
                    exit_code = result.returncode
                    break

            wait_seconds = 0.0 if click == "hover" else float(step.get("wait", 0.0) or 0.0)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
    finally:
        current_position = click_module.read_cursor_position()
        click_module.move_cursor_to(
            original_position.x,
            original_position.y,
            ydotool_socket,
            verify=False,
            initial_position=current_position,
        )
    return exit_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an Input Pilot mousemove sequence")
    parser.add_argument("--config", type=Path, default=CONFIG_FILE)
    parser.add_argument("--ydotool-socket", default=DEFAULT_YDOTOOL_SOCKET)
    parser.add_argument("--index", type=int, default=1, help="1-based automation index")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run_sequence(args.config.expanduser(), args.ydotool_socket, args.index)


if __name__ == "__main__":
    raise SystemExit(main())
