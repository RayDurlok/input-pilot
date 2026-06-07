#!/usr/bin/env python3
"""Run configured Input Pilot mouse template sequences."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import re
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
CLIPBOARD_RESTORE_DELAY_SECONDS = 0.15
TEMPLATE_CLICK_RE = re.compile(r"\bclick_x=(-?\d+)\s+click_y=(-?\d+)\b")
MATCH_CHOICES = {"best", "rightmost", "leftmost", "topmost", "bottommost", "middle"}
AUTOMATION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{5,63}$")
STATE_DIR = Path.home() / ".local/state/wayland-automation"
SEQUENCE_LOG_FILE = STATE_DIR / "mouse-sequence.log"
SEQUENCE_ABORT_FILE = STATE_DIR / "mouse-sequence.abort"
SEQUENCE_LOCK_MAX_AGE = 30.0
MAX_SEQUENCE_JUMPS = 3
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


def load_automations(config_file: Path) -> list[dict[str, object]]:
    if not config_file.exists():
        raise SystemExit(f"Config not found: {config_file}")
    with config_file.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        automations = data.get("automations")
        if isinstance(automations, list):
            return [item for item in automations if isinstance(item, dict)]
        return [data]
    if isinstance(data, list):
        return [{"name": "Automation", "debug": False, "steps": data}]
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


def log_sequence(message: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with SEQUENCE_LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")


def sequence_abort_requested() -> bool:
    return SEQUENCE_ABORT_FILE.exists()


def ensure_sequence_not_aborted() -> None:
    if sequence_abort_requested():
        raise SystemExit("Input automation aborted")


def interruptible_sleep(seconds: float) -> None:
    deadline = time.monotonic() + max(seconds, 0.0)
    while time.monotonic() < deadline:
        ensure_sequence_not_aborted()
        time.sleep(min(0.05, max(deadline - time.monotonic(), 0.0)))


class SequenceRunLock:
    def __init__(self, index: int) -> None:
        self.path = STATE_DIR / f"mouse-sequence-{index}.lock"
        self.fd: int | None = None

    def __enter__(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        self.remove_stale_lock()
        try:
            self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            log_sequence(f"sequence lock busy path={self.path}")
            return None
        os.write(self.fd, str(os.getpid()).encode("utf-8"))
        log_sequence(f"sequence lock acquired path={self.path}")
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        if self.fd is None:
            return
        os.close(self.fd)
        self.fd = None
        self.path.unlink(missing_ok=True)
        log_sequence(f"sequence lock released path={self.path}")

    def remove_stale_lock(self) -> None:
        try:
            age = time.time() - self.path.stat().st_mtime
        except FileNotFoundError:
            return
        if age > SEQUENCE_LOCK_MAX_AGE:
            log_sequence(f"sequence lock stale removed path={self.path} age={age:.1f}")
            self.path.unlink(missing_ok=True)


def result_text(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(
        part.strip()
        for part in (result.stdout or "", result.stderr or "")
        if part and part.strip()
    )


def step_match_choice(step: dict[str, object]) -> str:
    choice = str(step.get("match_choice", "best")).strip().lower()
    return choice if choice in MATCH_CHOICES else "best"


def run_template_command(
    command: list[str],
    debug: bool,
    not_found_message: str,
) -> subprocess.CompletedProcess[str]:
    ensure_sequence_not_aborted()
    log_sequence(f"template_command start {' '.join(command)}")
    result = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    ensure_sequence_not_aborted()
    log_sequence(f"template_command exit={result.returncode} {result_text(result).splitlines()[-1:]}")
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
    command = [
        str(TEMPLATE_SERVER),
        str(template_path),
        "--no-return-cursor",
        "--match-choice",
        step_match_choice(step),
    ]
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

    if bool(step.get("animate_mouse", False)):
        command.extend(["--animate-mouse", "--mouse-steps", "50"])

    if ydotool_socket:
        command.extend(["--ydotool-socket", ydotool_socket])
    return command


def move_to_template_command(
    template: str,
    ydotool_socket: str | None,
    match_choice: str = "best",
) -> list[str]:
    template_path = Path(template).expanduser()
    if not template_path.is_file():
        raise SystemExit(f"Template image not found: {template_path}")
    command = [
        str(TEMPLATE_SERVER),
        str(template_path),
        "--no-return-cursor",
        "--move-only",
        "--match-choice",
        match_choice if match_choice in MATCH_CHOICES else "best",
    ]
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


def clipboard_text() -> str | None:
    wl_paste = shutil.which("wl-paste")
    if not wl_paste:
        return None
    result = subprocess.run(
        [wl_paste, "--no-newline"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=1,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def set_clipboard(text: str) -> None:
    wl_copy = shutil.which("wl-copy")
    if not wl_copy:
        raise SystemExit("wl-copy is not installed")
    subprocess.run(
        [wl_copy, "--"],
        input=text,
        check=True,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def paste_string(text: str, ydotool_socket: str | None) -> None:
    ensure_sequence_not_aborted()
    if not text:
        raise SystemExit("Input string node is empty")
    saved_clipboard = clipboard_text()
    set_clipboard(text)
    try:
        run_ydotool(["key", "29:1", "47:1", "47:0", "29:0"], ydotool_socket)
        ensure_sequence_not_aborted()
    finally:
        if saved_clipboard is not None:
            interruptible_sleep(CLIPBOARD_RESTORE_DELAY_SECONDS)
            set_clipboard(saved_clipboard)


def type_string_by_keys(text: str, ydotool_socket: str | None) -> None:
    ensure_sequence_not_aborted()
    if not text:
        raise SystemExit("Input string node is empty")
    run_ydotool(["type", "--key-delay=0", "--key-hold=1", "--", text], ydotool_socket)


def send_key_combo(combo: str, ydotool_socket: str | None) -> None:
    ensure_sequence_not_aborted()
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
    ensure_sequence_not_aborted()


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
        move_to_template_command(source, ydotool_socket, step_match_choice(step)),
        debug,
        "Source screenshot couldn't be found on screen.",
    )
    if source_result.returncode != 0:
        return source_result.returncode

    try:
        run_ydotool(["click", "0x40"], ydotool_socket)
        target_result = run_template_command(
            move_to_template_command(target, ydotool_socket, step_match_choice(step)),
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
        move_to_template_command(source, ydotool_socket, step_match_choice(step)),
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


def read_int_field(step: dict[str, object], key: str, label: str) -> int:
    try:
        return int(float(step.get(key, 0) or 0))
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"{label} has invalid coordinates") from exc


def move_to_point(
    x: int,
    y: int,
    ydotool_socket: str | None,
    click_module,
    animate_mouse: bool = False,
):
    current_position = click_module.read_cursor_position()
    if animate_mouse:
        return click_module.smooth_move_cursor_to(
            x,
            y,
            ydotool_socket,
            steps=50,
            initial_position=current_position,
        )
    return click_module.move_cursor_to(
        x,
        y,
        ydotool_socket,
        verify=False,
        initial_position=current_position,
    )


def move_to_step_position(
    step: dict[str, object],
    role: str,
    ydotool_socket: str | None,
    debug: bool,
    click_module,
    original_position,
) -> tuple[int, object | None]:
    position_type = str(step.get(f"{role}_type", "")).strip().lower()
    if role == "target" and not position_type:
        position_type = str(step.get("target_type", "")).strip().lower()
    if role == "source" and not position_type:
        position_type = str(step.get("source_type", "")).strip().lower()
    if position_type not in {"template", "position", "previous-position"}:
        position_type = "template"

    if position_type == "template":
        action = str(step.get("action", "")).strip().lower()
        template = ""
        if role == "source":
            template = str(step.get("template", "")).strip()
        elif action == "drag":
            template = str(step.get("target", "")).strip()
        else:
            template = str(step.get("target", "")).strip() or str(step.get("template", "")).strip()
        label = "Source" if role == "source" else "Target"
        if not template:
            notify_debug(debug, f"{label} screenshot/template is empty.")
            raise SystemExit(f"{label} screenshot/template is empty")
        log_sequence(f"move_to_{role} template={template}")
        result = run_template_command(
            move_to_template_command(template, ydotool_socket, step_match_choice(step)),
            debug,
            f"{label} screenshot couldn't be found on screen.",
        )
        if result.returncode != 0:
            log_sequence(f"move_to_{role} failed exit={result.returncode}")
            return result.returncode, None
        position = click_module.read_cursor_position()
        log_sequence(f"move_to_{role} ok cursor={position.x},{position.y}")
        return 0, position

    if position_type == "previous-position":
        log_sequence(f"move_to_{role} previous={original_position.x},{original_position.y}")
        position = move_to_point(
            original_position.x,
            original_position.y,
            ydotool_socket,
            click_module,
            animate_mouse=(
                role == "target"
                and str(step.get("action", "")).strip().lower() == "move"
                and bool(step.get("animate_mouse", False))
            ),
        )
        return 0, position

    prefix = "source_" if role == "source" else ""
    label = "Source mouse position" if role == "source" else "Mouse position"
    x = read_int_field(step, f"{prefix}x", label)
    y = read_int_field(step, f"{prefix}y", label)
    log_sequence(f"move_to_{role} position={x},{y}")
    position = move_to_point(
        x,
        y,
        ydotool_socket,
        click_module,
        animate_mouse=(
            role == "target"
            and str(step.get("action", "")).strip().lower() == "move"
            and bool(step.get("animate_mouse", False))
        ),
    )
    return 0, position


def parse_template_position(output: str) -> tuple[int, int] | None:
    match = TEMPLATE_CLICK_RE.search(output)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def locate_template_position(
    template: str,
    ydotool_socket: str | None,
    debug: bool,
    not_found_message: str,
    match_choice: str = "best",
) -> tuple[int, int] | None:
    template_path = Path(template).expanduser()
    if not template_path.is_file():
        raise SystemExit(f"Template image not found: {template_path}")
    command = [
        str(TEMPLATE_SERVER),
        str(template_path),
        "--dry-run",
        "--match-choice",
        match_choice if match_choice in MATCH_CHOICES else "best",
    ]
    if ydotool_socket:
        command.extend(["--ydotool-socket", ydotool_socket])
    result = run_template_command(command, debug, not_found_message)
    if result.returncode != 0:
        return None
    position = parse_template_position(result_text(result))
    if position is None:
        notify_debug(debug, "Template position could not be read from matcher output.")
        raise SystemExit("Template position could not be read from matcher output")
    return position


def target_coordinates_for_drag(
    step: dict[str, object],
    ydotool_socket: str | None,
    debug: bool,
    original_position,
) -> tuple[int, int] | None:
    target_type = str(step.get("target_type", "template")).strip().lower()
    if target_type == "previous-position":
        return original_position.x, original_position.y
    if target_type == "position":
        x = read_int_field(step, "x", "Target mouse position")
        y = read_int_field(step, "y", "Target mouse position")
        return x, y

    template = str(step.get("target", "")).strip()
    if not template:
        notify_debug(debug, "Target screenshot/template is empty.")
        raise SystemExit("Target screenshot/template is empty")
    return locate_template_position(
        template,
        ydotool_socket,
        debug,
        "Target screenshot couldn't be found on screen.",
        step_match_choice(step),
    )


def smooth_drag_to(
    start_x: int,
    start_y: int,
    target_x: int,
    target_y: int,
    ydotool_socket: str | None,
    debug: bool = False,
    steps: int = 2,
) -> None:
    ensure_sequence_not_aborted()
    dx = target_x - start_x
    dy = target_y - start_y
    distance = math.hypot(dx, dy)
    log_sequence(
        f"smooth_drag start={start_x},{start_y} target={target_x},{target_y} distance={distance:.1f}"
    )
    if distance <= 1:
        run_ydotool(["mousemove", "--", "1", "0"], ydotool_socket)
        run_ydotool(["mousemove", "--", "-1", "0"], ydotool_socket)
        return

    unit_x = dx / distance
    unit_y = dy / distance
    start_drag_x = round(unit_x * min(16, distance))
    start_drag_y = round(unit_y * min(16, distance))
    if start_drag_x or start_drag_y:
        run_ydotool(["mousemove", "--", str(start_drag_x), str(start_drag_y)], ydotool_socket)
        interruptible_sleep(0.02)

    current_start_x = start_x + start_drag_x
    current_start_y = start_y + start_drag_y
    dx = target_x - current_start_x
    dy = target_y - current_start_y
    distance = math.hypot(dx, dy)
    if distance <= 1:
        return

    steps = max(1, min(int(steps or 2), 200))
    log_sequence(f"smooth_drag steps={steps} start_pull={start_drag_x},{start_drag_y}")
    notify_debug(
        debug,
        f"Smooth drag: {steps} steps from {start_x},{start_y} to {target_x},{target_y}.",
    )
    previous_x = current_start_x
    previous_y = current_start_y
    for step_index in range(1, steps + 1):
        ensure_sequence_not_aborted()
        progress = step_index / steps
        next_x = round(current_start_x + dx * progress)
        next_y = round(current_start_y + dy * progress)
        move_x = next_x - previous_x
        move_y = next_y - previous_y
        if move_x or move_y:
            run_ydotool(["mousemove", "--", str(move_x), str(move_y)], ydotool_socket)
        previous_x = next_x
        previous_y = next_y
        interruptible_sleep(0.003)


def run_model_step(
    step: dict[str, object],
    ydotool_socket: str | None,
    debug: bool,
    click_module,
    original_position,
) -> int:
    ensure_sequence_not_aborted()
    action = str(step.get("action", "")).strip().lower()
    log_sequence(f"run_model_step action={action}")
    if action == "input":
        input_type = str(step.get("input_type", "keys")).strip().lower()
        log_sequence(f"input type={input_type}")
        if input_type == "text":
            paste_string(str(step.get("text", "")), ydotool_socket)
        elif input_type == "typed-text":
            type_string_by_keys(str(step.get("text", "")), ydotool_socket)
        else:
            send_key_combo(str(step.get("keys", "")).strip(), ydotool_socket)
        return 0

    if action == "move":
        target_type = str(step.get("target_type", "template")).strip().lower()
        if target_type == "template":
            template = (
                str(step.get("target", "")).strip()
                or str(step.get("template", "")).strip()
            )
            wait_seconds = max(float(step.get("wait", 0.0) or 0.0), 0.25)
            legacy_step = dict(step, template=template, click="hover", wait=wait_seconds)
            result = run_template_command(
                step_command(legacy_step, ydotool_socket),
                debug,
                "Screenshot couldn't be found on screen.",
            )
            return result.returncode
        return move_to_step_position(
            step,
            "target",
            ydotool_socket,
            debug,
            click_module,
            original_position,
        )[0]

    if action == "click":
        target_type = str(step.get("target_type", "template")).strip().lower()
        if target_type == "template":
            template = str(step.get("target", "")).strip() or str(step.get("template", "")).strip()
            button = str(step.get("button", "left")).strip().lower()
            legacy_step = dict(step, template=template, click=button)
            result = run_template_command(
                step_command(legacy_step, ydotool_socket),
                debug,
                "Screenshot couldn't be found on screen.",
            )
            return result.returncode
        exit_code, position = move_to_step_position(
            step,
            "target",
            ydotool_socket,
            debug,
            click_module,
            original_position,
        )
        if exit_code != 0:
            return exit_code
        button = str(step.get("button", "left")).strip().lower()
        if button == "hover":
            return 0
        if position is None:
            position = click_module.read_cursor_position()
        click_module.click_at(
            position.x,
            position.y,
            ydotool_socket,
            repeat=2 if button == "double-left" else 1,
            button_code="0xC1" if button == "right" else "0xC0",
            return_cursor=False,
            animate_mouse=bool(step.get("animate_mouse", False)) and button != "hover",
            mouse_steps=50,
        )
        return 0

    if action == "drag":
        log_sequence(
            "drag begin "
            f"source_type={step.get('source_type')} target_type={step.get('target_type')}"
        )
        target_position = target_coordinates_for_drag(
            step,
            ydotool_socket,
            debug,
            original_position,
        )
        if target_position is None:
            log_sequence("drag target_position missing")
            return 1
        log_sequence(f"drag target_position={target_position[0]},{target_position[1]}")
        exit_code, source_position = move_to_step_position(
            step,
            "source",
            ydotool_socket,
            debug,
            click_module,
            original_position,
        )
        if exit_code != 0:
            log_sequence(f"drag source failed exit={exit_code}")
            return exit_code
        drag_reached_target = False
        try:
            log_sequence("drag mouse_down")
            run_ydotool(["click", "0x40"], ydotool_socket)
            interruptible_sleep(0.03)
            if source_position is None:
                source_position = click_module.read_cursor_position()
            log_sequence(f"drag source_position={source_position.x},{source_position.y}")
            drag_steps = read_int_field(step, "drag_steps", "Smooth drag steps")
            smooth_drag_to(
                source_position.x,
                source_position.y,
                target_position[0],
                target_position[1],
                ydotool_socket,
                debug,
                drag_steps,
            )
            run_ydotool(["mousemove", "--", "1", "0"], ydotool_socket)
            run_ydotool(["mousemove", "--", "-1", "0"], ydotool_socket)
            interruptible_sleep(0.03)
            drag_reached_target = True
            log_sequence("drag reached target")
            return 0
        finally:
            run_ydotool(["click", "0x80"], ydotool_socket)
            log_sequence("drag mouse_up")
            if drag_reached_target:
                interruptible_sleep(0.08)

    raise SystemExit(f"Unknown automation action: {action}")


def step_indent(step: dict[str, object]) -> int:
    try:
        return max(0, int(float(step.get("indent", 0) or 0)))
    except (TypeError, ValueError):
        return 0


def block_end_index(
    steps: list[dict[str, object]],
    start_index: int,
    parent_indent: int,
) -> int:
    index = start_index
    while index < len(steps) and step_indent(steps[index]) > parent_indent:
        index += 1
    return index


def evaluate_if_condition(
    step: dict[str, object],
    state: dict[str, object],
) -> bool:
    condition = str(step.get("condition", "previous-node-failed")).strip().lower()
    if condition == "screenshot-missing":
        condition = "previous-node-failed"
    elif condition == "screenshot-found":
        condition = "previous-node-succeeded"
    last_step_success = bool(state.get("last_step_success", True))
    if condition == "always":
        return True
    if condition == "previous-node-succeeded":
        return last_step_success
    return not last_step_success


def if_jump_target(
    step: dict[str, object],
    steps: list[dict[str, object]],
) -> int | None:
    if not bool(step.get("if_jump_enabled", False)):
        return None
    try:
        target_step = int(float(step.get("if_jump_step", 0) or 0))
    except (TypeError, ValueError):
        return None
    if target_step < 1 or target_step > len(steps):
        return None
    return target_step - 1


def next_step_handles_failure(
    steps: list[dict[str, object]],
    current_index: int,
    expected_indent: int,
) -> bool:
    next_index = current_index + 1
    if next_index >= len(steps):
        return False
    next_step = steps[next_index]
    if step_indent(next_step) != expected_indent:
        return False
    action = str(next_step.get("action", "")).strip().lower()
    click = str(next_step.get("click", "")).strip().lower()
    if action != "if" and click != "if":
        return False
    condition = str(next_step.get("condition", "previous-node-failed")).strip().lower()
    return condition in {"previous-node-failed", "screenshot-missing"}


def run_single_sequence_step(
    step_index: int,
    step: dict[str, object],
    ydotool_socket: str | None,
    debug: bool,
    click_module,
    original_position,
) -> int:
    ensure_sequence_not_aborted()
    action = str(step.get("action", "")).strip().lower()
    click = str(step.get("click", "left")).strip().lower()
    log_sequence(f"step {step_index} action={action} click={click}")

    if action in {"click", "drag", "move", "input"}:
        print(f"step {step_index}: {action}")
        try:
            exit_code = run_model_step(
                step,
                ydotool_socket,
                debug,
                click_module,
                original_position,
            )
        except SystemExit as exc:
            notify_debug(debug, str(exc))
            raise
        if exit_code != 0:
            return exit_code
    elif click == "drag":
        print(f"step {step_index}: drag")
        exit_code = run_drag_step(step, ydotool_socket, debug)
        if exit_code != 0:
            return exit_code
    elif click == "drag-position":
        print(f"step {step_index}: drag to position")
        exit_code = run_drag_to_position_step(
            step,
            ydotool_socket,
            debug,
            click_module,
        )
        if exit_code != 0:
            return exit_code
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
            paste_string(text, ydotool_socket)
        except SystemExit as exc:
            notify_debug(debug, str(exc))
            raise
    elif click == "typed-text":
        text = str(step.get("text", ""))
        print(f"step {step_index}: typed text")
        try:
            type_string_by_keys(text, ydotool_socket)
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
            return result.returncode

    button = str(step.get("button", "")).strip().lower()
    target_type = str(step.get("target_type", "")).strip().lower()
    if action == "move" and target_type == "template":
        wait_seconds = 0.0
    elif action == "click" and button == "hover" and target_type == "template":
        wait_seconds = 0.0
    else:
        wait_seconds = float(step.get("wait", 0.0) or 0.0)
    if wait_seconds > 0:
        interruptible_sleep(wait_seconds)
    return 0


def run_steps_range(
    steps: list[dict[str, object]],
    start_index: int,
    end_index: int,
    expected_indent: int,
    ydotool_socket: str | None,
    debug: bool,
    click_module,
    original_position,
    state: dict[str, object],
) -> int:
    index = start_index
    while index < end_index:
        ensure_sequence_not_aborted()

        step = steps[index]
        indent = step_indent(step)
        if indent < expected_indent:
            break
        if indent > expected_indent:
            index += 1
            continue

        action = str(step.get("action", "")).strip().lower()
        click = str(step.get("click", "left")).strip().lower()
        if action == "if" or click == "if":
            child_start = index + 1
            child_end = block_end_index(steps, child_start, indent)
            condition_matches = evaluate_if_condition(step, state)
            log_sequence(
                f"step {index + 1} if condition_matches={condition_matches} "
                f"children={child_end - child_start}"
            )
            print(f"step {index + 1}: if {condition_matches}")
            if condition_matches:
                exit_code = run_steps_range(
                    steps,
                    child_start,
                    child_end,
                    indent + 1,
                    ydotool_socket,
                    debug,
                    click_module,
                    original_position,
                    state,
                )
                if exit_code != 0:
                    return exit_code
                jump_target = if_jump_target(step, steps)
                if jump_target is not None:
                    state["jump_count"] = int(state.get("jump_count", 0) or 0) + 1
                    if int(state["jump_count"]) >= MAX_SEQUENCE_JUMPS:
                        notify_debug(debug, "Automation stopped: jump loop limit reached.")
                        log_sequence(
                            f"sequence stopped jump loop limit reached jumps={state['jump_count']}"
                        )
                        return 1
                    log_sequence(f"step {index + 1} if jump_to_step={jump_target + 1}")
                    if expected_indent == 0:
                        index = jump_target
                        continue
                    state["jump_to_index"] = jump_target
                    return 0
                if "jump_to_index" in state:
                    if expected_indent == 0:
                        index = int(state.pop("jump_to_index"))
                        continue
                    return 0
            index = child_end
            continue

        if "jump_to_index" in state:
            if expected_indent == 0:
                index = int(state.pop("jump_to_index"))
                continue
            return 0

        exit_code = run_single_sequence_step(
            index + 1,
            step,
            ydotool_socket,
            debug,
            click_module,
            original_position,
        )
        if exit_code != 0:
            state["last_step_success"] = False
            if next_step_handles_failure(steps, index, expected_indent):
                index += 1
                continue
            return exit_code
        state["last_step_success"] = True
        index += 1
    return 0


def run_sequence(config_file: Path, ydotool_socket: str | None, index: int) -> int:
    automation = load_automation(config_file, index)
    debug = bool(automation.get("debug", False))
    steps = load_steps(config_file, index)
    log_sequence(
        f"run index={index} name={automation.get('name', 'Automation')} steps={len(steps)}"
    )
    if not steps:
        notify_debug(debug, "No mousemove nodes are configured.")
        raise SystemExit(f"No mousemove steps configured: {config_file}")

    with SequenceRunLock(index) as lock:
        if lock is None:
            return 0

        SEQUENCE_ABORT_FILE.unlink(missing_ok=True)
        click_module = load_click_module()
        original_position = click_module.read_cursor_position()
        try:
            exit_code = run_steps_range(
                steps,
                0,
                len(steps),
                0,
                ydotool_socket,
                debug,
                click_module,
                original_position,
                {"last_step_success": True, "jump_count": 0},
            )
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


def find_index_by_name(config_file: Path, name: str) -> int:
    automations = load_automations(config_file)
    name_lower = name.strip().casefold()
    matches = []
    for i, auto in enumerate(automations, start=1):
        if isinstance(auto, dict) and str(auto.get("name", "")).strip().casefold() == name_lower:
            matches.append(i)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise SystemExit(
            f"Automation name {name!r} is ambiguous; matching indexes: "
            + ", ".join(str(index) for index in matches)
        )
    raise SystemExit(f"No automation named {name!r} found in {config_file}")


def clean_automation_id(raw_id: str) -> str:
    candidate = raw_id.strip().lower()
    return candidate if AUTOMATION_ID_RE.fullmatch(candidate) else ""


def find_index_by_id(config_file: Path, automation_id: str) -> int:
    clean_id = clean_automation_id(automation_id)
    if not clean_id:
        raise SystemExit(f"Invalid automation id: {automation_id!r}")
    automations = load_automations(config_file)
    for i, auto in enumerate(automations, start=1):
        if clean_automation_id(str(auto.get("id", ""))) == clean_id:
            return i
    raise SystemExit(f"No automation id {automation_id!r} found in {config_file}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an Input Pilot mousemove sequence")
    parser.add_argument("--config", type=Path, default=CONFIG_FILE)
    parser.add_argument("--ydotool-socket", default=DEFAULT_YDOTOOL_SOCKET)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--id", default=None, help="stable automation id")
    group.add_argument("--index", type=int, default=None, help="1-based automation index")
    group.add_argument("--name", default=None, help="automation name (case-insensitive)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = args.config.expanduser()
    if args.id is not None:
        index = find_index_by_id(config, args.id)
    elif args.name is not None:
        index = find_index_by_name(config, args.name)
    else:
        index = args.index if args.index is not None else 1
    return run_sequence(config, args.ydotool_socket, index)


if __name__ == "__main__":
    raise SystemExit(main())
