#!/usr/bin/env python3
"""Find a template image on the current KDE Wayland screen and click it."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
AUTOMATION_STATE_DIR = STATE_DIR / "wayland-automation"
CLICK_LOCK_FILE = AUTOMATION_STATE_DIR / "click-template.lock"
CLICK_ABORT_FILE = AUTOMATION_STATE_DIR / "click-template.abort"
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


@dataclass(frozen=True)
class ScreenOutput:
    name: str
    x: int
    y: int
    width: int
    height: int


def require_command(name: str, install_hint: str) -> str:
    path = shutil.which(name)
    if path:
        return path
    raise SystemExit(f"Missing command: {name}\nInstall/setup hint: {install_hint}")


def import_cv2():
    try:
        import cv2  # type: ignore
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing Python module: cv2\n"
            "Install/setup hint: sudo dnf install python3-opencv"
        ) from exc
    return cv2


class AutomationLock:
    def __enter__(self):
        AUTOMATION_STATE_DIR.mkdir(parents=True, exist_ok=True)
        if CLICK_LOCK_FILE.exists():
            raise SystemExit(f"Click automation already running: {CLICK_LOCK_FILE}")
        CLICK_ABORT_FILE.unlink(missing_ok=True)
        CLICK_LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        CLICK_LOCK_FILE.unlink(missing_ok=True)
        CLICK_ABORT_FILE.unlink(missing_ok=True)


def abort_requested() -> bool:
    return CLICK_ABORT_FILE.exists()


def ensure_not_aborted() -> None:
    if abort_requested():
        raise SystemExit("Click automation aborted")


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


def read_screen_outputs() -> list[ScreenOutput]:
    if not shutil.which("kscreen-doctor"):
        return []
    try:
        result = subprocess.run(
            ["kscreen-doctor", "-o"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        )
    except subprocess.TimeoutExpired:
        return []
    if result.returncode != 0:
        return []

    outputs: list[ScreenOutput] = []
    current_name = ""
    for raw_line in result.stdout.splitlines():
        line = strip_ansi(raw_line).strip()
        output_match = re.search(r"Output:\s+\d+\s+(\S+)", line)
        if output_match:
            current_name = output_match.group(1)
            continue
        geometry_match = re.search(
            r"Geometry:\s+(-?\d+),(-?\d+)\s+(\d+)x(\d+)",
            line,
        )
        if geometry_match and current_name:
            outputs.append(
                ScreenOutput(
                    name=current_name,
                    x=int(geometry_match.group(1)),
                    y=int(geometry_match.group(2)),
                    width=int(geometry_match.group(3)),
                    height=int(geometry_match.group(4)),
                )
            )
    return outputs


def output_for_point(
    x: int,
    y: int,
    outputs: list[ScreenOutput],
) -> ScreenOutput | None:
    for output in outputs:
        within_x = output.x <= x < output.x + output.width
        within_y = output.y <= y < output.y + output.height
        if within_x and within_y:
            return output
    return None


def click_coordinates_for_point(
    x: int,
    y: int,
    use_output_local_coordinates: bool,
) -> tuple[int, int, str]:
    if not use_output_local_coordinates:
        return x, y, "global"

    output = output_for_point(x, y, read_screen_outputs())
    if not output:
        return x, y, "global-no-output-match"
    return x - output.x, y - output.y, f"output-local:{output.name}"


def take_screenshot(output: Path) -> None:
    spectacle = require_command("spectacle", "sudo dnf install spectacle")
    subprocess.run(
        [spectacle, "-b", "-n", "-o", str(output)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


def click_at(
    x: int,
    y: int,
    socket: str | None,
    repeat: int = 1,
    next_delay_ms: int = 80,
) -> None:
    ydotool = require_command(
        "ydotool",
        "sudo dnf install ydotool; then start ydotoold, for example: sudo ydotoold",
    )
    env = None
    if socket:
        env = dict(os.environ, YDOTOOL_SOCKET=socket)

    for _index in range(repeat):
        ensure_not_aborted()
        subprocess.run(
            [ydotool, "mousemove", "--absolute", "-x", str(x), "-y", str(y)],
            check=True,
            env=env,
        )
        subprocess.run([ydotool, "click", "0xC0"], check=True, env=env)
        if repeat > 1:
            time.sleep(max(next_delay_ms, 0) / 1000)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find a screenshot snippet on KDE Wayland and click its center."
    )
    parser.add_argument("template", help="Path to the button/template image to find")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.82,
        help="Minimum match score from 0.0 to 1.0 (default: 0.82)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Seconds to wait before taking the screenshot",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print the detected position; do not click",
    )
    parser.add_argument(
        "--double-click",
        action="store_true",
        help="Double left-click the detected template center",
    )
    parser.add_argument(
        "--double-click-delay",
        type=int,
        default=80,
        help="Milliseconds between double-click events (default: 80)",
    )
    parser.add_argument(
        "--debug-image",
        help="Optional path to save the full screenshot used for matching",
    )
    parser.add_argument(
        "--ydotool-socket",
        default=None,
        help="Optional ydotool socket path, e.g. /tmp/ydotool_socket",
    )
    parser.add_argument(
        "--coordinate-mode",
        choices=("output-local", "global"),
        default="output-local",
        help=(
            "Coordinate mode for ydotool clicks. output-local maps the global "
            "screenshot position to the matching monitor's local coordinates "
            "(default: output-local)."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cv2 = import_cv2()

    template_path = Path(args.template).expanduser()
    if not template_path.is_file():
        raise SystemExit(f"Template image not found: {template_path}")

    if args.delay > 0:
        time.sleep(args.delay)

    def cleanup(_signum=None, _frame=None):
        CLICK_ABORT_FILE.touch()
        CLICK_LOCK_FILE.unlink(missing_ok=True)
        raise SystemExit("Click automation interrupted")

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    with (
        AutomationLock(),
        tempfile.TemporaryDirectory(prefix="wayland-click-image-") as tmp_dir,
    ):
        screenshot_path = Path(tmp_dir) / "screen.png"
        take_screenshot(screenshot_path)

        if args.debug_image:
            debug_path = Path(args.debug_image).expanduser()
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            debug_path.write_bytes(screenshot_path.read_bytes())

        screen = cv2.imread(str(screenshot_path), cv2.IMREAD_COLOR)
        template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
        if screen is None:
            raise SystemExit(f"Could not read screenshot: {screenshot_path}")
        if template is None:
            raise SystemExit(f"Could not read template image: {template_path}")

        screen_h, screen_w = screen.shape[:2]
        template_h, template_w = template.shape[:2]
        if template_w > screen_w or template_h > screen_h:
            raise SystemExit("Template image is larger than the screen screenshot")

        result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        _, max_score, _, max_loc = cv2.minMaxLoc(result)

        center_x = int(max_loc[0] + template_w / 2)
        center_y = int(max_loc[1] + template_h / 2)
        click_x, click_y, coordinate_mode = click_coordinates_for_point(
            center_x,
            center_y,
            use_output_local_coordinates=args.coordinate_mode == "output-local",
        )
        print(
            f"match={max_score:.3f} screenshot_x={center_x} screenshot_y={center_y} "
            f"click_x={click_x} click_y={click_y} mode={coordinate_mode} "
            f"template={template_w}x{template_h}"
        )

        if max_score < args.threshold:
            raise SystemExit(
                f"Match below threshold {args.threshold:.2f}; not clicking"
            )

        if not args.dry_run:
            click_at(
                click_x,
                click_y,
                args.ydotool_socket,
                repeat=2 if args.double_click else 1,
                next_delay_ms=args.double_click_delay,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
