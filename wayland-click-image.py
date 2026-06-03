#!/usr/bin/env python3
"""Find a template image on the current KDE Wayland screen and click it."""

from __future__ import annotations

import argparse
import json
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
CURSOR_POSITION_FILE = AUTOMATION_STATE_DIR / "cursor-position.json"
SCRIPT_DIR = Path(__file__).resolve().parent
KWIN_CURSOR_SCRIPT = SCRIPT_DIR / "kwin-cursor-position.js"
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
TEMPLATE_IMAGE_CACHE = {}
KWIN_CAPTURE_USABLE = None


@dataclass(frozen=True)
class ScreenOutput:
    name: str
    priority: int
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class CursorPosition:
    x: int
    y: int


@dataclass(frozen=True)
class TemplateActionResult:
    match_score: float
    screenshot_x: int
    screenshot_y: int
    click_x: int
    click_y: int
    coordinate_mode: str
    search_scope: str
    capture_source: str
    template_width: int
    template_height: int
    cursor_position: CursorPosition | None = None

    def summary(self) -> str:
        return (
            f"match={self.match_score:.3f} screenshot_x={self.screenshot_x} "
            f"screenshot_y={self.screenshot_y} click_x={self.click_x} "
            f"click_y={self.click_y} mode={self.coordinate_mode} "
            f"scope={self.search_scope} "
            f"capture={self.capture_source} "
            f"template={self.template_width}x{self.template_height}"
        )

    def cursor_summary(self) -> str | None:
        if not self.cursor_position:
            return None
        return f"cursor_x={self.cursor_position.x} cursor_y={self.cursor_position.y}"


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
    current_priority = 9999
    for raw_line in result.stdout.splitlines():
        line = strip_ansi(raw_line).strip()
        output_match = re.search(r"Output:\s+\d+\s+(\S+)", line)
        if output_match:
            current_name = output_match.group(1)
            current_priority = 9999
            continue
        priority_match = re.search(r"priority\s+(\d+)", line)
        if priority_match:
            current_priority = int(priority_match.group(1))
            continue
        geometry_match = re.search(
            r"Geometry:\s+(-?\d+),(-?\d+)\s+(\d+)x(\d+)",
            line,
        )
        if geometry_match and current_name:
            outputs.append(
                ScreenOutput(
                    name=current_name,
                    priority=current_priority,
                    x=int(geometry_match.group(1)),
                    y=int(geometry_match.group(2)),
                    width=int(geometry_match.group(3)),
                    height=int(geometry_match.group(4)),
                )
            )
    return outputs


def primary_output(outputs: list[ScreenOutput]) -> ScreenOutput | None:
    if not outputs:
        return None
    return min(outputs, key=lambda output: output.priority)


def virtual_origin(outputs: list[ScreenOutput]) -> tuple[int, int]:
    if not outputs:
        return 0, 0
    return min(output.x for output in outputs), min(output.y for output in outputs)


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


def run_ydotool(
    arguments: list[str],
    socket: str | None,
    timeout: float = 2,
) -> None:
    ydotool = require_command(
        "ydotool",
        "sudo dnf install ydotool; then start ydotoold, for example: sudo ydotoold",
    )
    env = None
    if socket:
        env = dict(os.environ, YDOTOOL_SOCKET=socket)
    subprocess.run([ydotool, *arguments], check=True, env=env, timeout=timeout)


def refresh_cursor_position() -> None:
    if not KWIN_CURSOR_SCRIPT.exists():
        raise SystemExit(f"KWin cursor script not found: {KWIN_CURSOR_SCRIPT}")
    if not shutil.which("busctl"):
        raise SystemExit("Missing command: busctl")

    script_path = str(KWIN_CURSOR_SCRIPT)
    subprocess.run(
        [
            "busctl",
            "--user",
            "call",
            "org.kde.KWin",
            "/Scripting",
            "org.kde.kwin.Scripting",
            "unloadScript",
            "s",
            script_path,
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            "busctl",
            "--user",
            "call",
            "org.kde.KWin",
            "/Scripting",
            "org.kde.kwin.Scripting",
            "loadScript",
            "s",
            script_path,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            "busctl",
            "--user",
            "call",
            "org.kde.KWin",
            "/Scripting",
            "org.kde.kwin.Scripting",
            "start",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def read_cursor_position() -> CursorPosition:
    CURSOR_POSITION_FILE.unlink(missing_ok=True)
    refresh_cursor_position()
    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline:
        if CURSOR_POSITION_FILE.exists():
            with CURSOR_POSITION_FILE.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            return CursorPosition(x=int(data["x"]), y=int(data["y"]))
        time.sleep(0.03)
    raise SystemExit("Could not read fresh KWin cursor position")


def move_cursor_to(
    target_x: int,
    target_y: int,
    socket: str | None,
    tolerance: int = 8,
    max_iterations: int = 2,
    verify: bool = True,
) -> CursorPosition:
    position = read_cursor_position()
    for _iteration in range(max_iterations):
        ensure_not_aborted()
        dx = target_x - position.x
        dy = target_y - position.y
        if abs(dx) <= tolerance and abs(dy) <= tolerance:
            return position

        step_x = dx
        step_y = dy

        run_ydotool(["mousemove", "--", str(step_x), str(step_y)], socket)
        if not verify:
            return CursorPosition(target_x, target_y)

        time.sleep(0.01)
        position = read_cursor_position()

    return position


def start_screenshot(output: Path, current_monitor: bool = False) -> subprocess.Popen:
    spectacle = require_command("spectacle", "sudo dnf install spectacle")
    command = [spectacle, "-b", "-n"]
    if current_monitor:
        command.append("-m")
    command.extend(["-o", str(output)])
    return subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


def wait_for_screenshot(process: subprocess.Popen) -> None:
    _, stderr = process.communicate()
    if process.returncode != 0:
        raise subprocess.CalledProcessError(
            process.returncode,
            process.args,
            stderr=stderr,
        )


def capture_area_with_kwin(output: Path, area: ScreenOutput) -> bool:
    global KWIN_CAPTURE_USABLE
    if KWIN_CAPTURE_USABLE is False:
        return False

    try:
        from gi.repository import Gio, GLib  # type: ignore
    except (ImportError, ValueError):
        KWIN_CAPTURE_USABLE = False
        return False

    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        fd_list = Gio.UnixFDList.new()
        fd_index = fd_list.append(fd)
        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        connection.call_with_unix_fd_list_sync(
            "org.kde.KWin",
            "/org/kde/KWin/ScreenShot2",
            "org.kde.KWin.ScreenShot2",
            "CaptureArea",
            GLib.Variant(
                "(iiuua{sv}h)",
                (area.x, area.y, area.width, area.height, {}, fd_index),
            ),
            GLib.VariantType.new("(a{sv})"),
            Gio.DBusCallFlags.NONE,
            5000,
            fd_list,
            None,
        )
        success = output.exists() and output.stat().st_size > 0
        if success:
            KWIN_CAPTURE_USABLE = True
        return success
    except GLib.GError:
        KWIN_CAPTURE_USABLE = False
        output.unlink(missing_ok=True)
        return False
    finally:
        os.close(fd)


def load_template_image(cv2, template_path: Path):
    stat = template_path.stat()
    cache_key = str(template_path)
    cache_value = TEMPLATE_IMAGE_CACHE.get(cache_key)
    cache_token = (stat.st_mtime_ns, stat.st_size)
    if cache_value and cache_value[0] == cache_token:
        return cache_value[1]

    template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
    if template is None:
        raise SystemExit(f"Could not read template image: {template_path}")
    TEMPLATE_IMAGE_CACHE[cache_key] = (cache_token, template)
    return template


def image_matches_output(
    image,
    output: ScreenOutput | None,
) -> bool:
    if not output:
        return False
    if image is None:
        return False
    height, width = image.shape[:2]
    return width == output.width and height == output.height


def match_template_on_screen(
    cv2,
    screen,
    template,
    screen_scope: str,
    primary: ScreenOutput | None,
    current_monitor_image: bool = False,
) -> tuple[float, int, int, int, int, str]:
    search_offset_x = 0
    search_offset_y = 0
    search_scope = "all"
    if screen_scope == "primary" and primary:
        if current_monitor_image:
            height, width = screen.shape[:2]
            if width == primary.width and height == primary.height:
                search_offset_x = primary.x
                search_offset_y = primary.y
                search_scope = f"primary-current:{primary.name}"
        else:
            outputs = read_screen_outputs()
            origin_x, origin_y = virtual_origin(outputs)
            crop_x = primary.x - origin_x
            crop_y = primary.y - origin_y
            crop = screen[
                crop_y : crop_y + primary.height,
                crop_x : crop_x + primary.width,
            ]
            if crop.size:
                screen = crop
                search_offset_x = primary.x
                search_offset_y = primary.y
                search_scope = f"primary:{primary.name}"

    screen_h, screen_w = screen.shape[:2]
    template_h, template_w = template.shape[:2]
    if template_w > screen_w or template_h > screen_h:
        raise SystemExit("Template image is larger than the screen screenshot")

    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    _, max_score, _, max_loc = cv2.minMaxLoc(result)

    center_x = int(search_offset_x + max_loc[0] + template_w / 2)
    center_y = int(search_offset_y + max_loc[1] + template_h / 2)
    return max_score, center_x, center_y, template_w, template_h, search_scope


def click_at(
    x: int,
    y: int,
    socket: str | None,
    repeat: int = 1,
    next_delay_ms: int = 35,
) -> CursorPosition:
    if repeat <= 0:
        ensure_not_aborted()
        final_position = move_cursor_to(x, y, socket, verify=True)
        return final_position

    final_position = move_cursor_to(x, y, socket, verify=False)

    ensure_not_aborted()
    if repeat == 1:
        run_ydotool(["click", "0xC0"], socket)
    else:
        run_ydotool(
            [
                "click",
                f"--repeat={repeat}",
                f"--next-delay={max(next_delay_ms, 0)}",
                "0xC0",
            ],
            socket,
        )
    return final_position


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
        "--move-only",
        action="store_true",
        help="Move to the detected position but do not click",
    )
    parser.add_argument(
        "--double-click",
        action="store_true",
        help="Double left-click the detected template center",
    )
    parser.add_argument(
        "--double-click-delay",
        type=int,
        default=35,
        help="Milliseconds between double-click input events (default: 35)",
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
        default="global",
        help=(
            "Coordinate mode for ydotool clicks. global uses the screenshot "
            "position directly; output-local maps the global "
            "screenshot position to the matching monitor's local coordinates "
            "(default: global)."
        ),
    )
    parser.add_argument(
        "--screen-scope",
        choices=("primary", "all"),
        default="primary",
        help="Screen area to search for the template (default: primary).",
    )
    return parser.parse_args()


def run_template_action(args: argparse.Namespace, cv2=None) -> TemplateActionResult:
    global KWIN_CAPTURE_USABLE

    template_path = Path(args.template).expanduser()
    if not template_path.is_file():
        raise SystemExit(f"Template image not found: {template_path}")

    if args.delay > 0:
        time.sleep(args.delay)

    with (
        AutomationLock(),
        tempfile.TemporaryDirectory(prefix="wayland-click-image-") as tmp_dir,
    ):
        outputs = read_screen_outputs() if args.screen_scope == "primary" else []
        primary = primary_output(outputs)
        screenshot_path = Path(tmp_dir) / "screen.png"
        use_current_monitor_fast_path = args.screen_scope == "primary" and primary
        kwin_capture = bool(
            use_current_monitor_fast_path
            and capture_area_with_kwin(screenshot_path, primary)
        )
        screenshot_process = None
        if not kwin_capture:
            screenshot_process = start_screenshot(
                screenshot_path,
                current_monitor=bool(use_current_monitor_fast_path),
            )
        capture_source = (
            "kwin-area"
            if kwin_capture
            else "spectacle-current"
            if use_current_monitor_fast_path
            else "spectacle-full"
        )
        cv2 = cv2 or import_cv2()
        if screenshot_process:
            wait_for_screenshot(screenshot_process)
        screen = cv2.imread(str(screenshot_path), cv2.IMREAD_COLOR)
        if screen is None and kwin_capture:
            KWIN_CAPTURE_USABLE = False
            kwin_capture = False
            capture_source = (
                "spectacle-current"
                if use_current_monitor_fast_path
                else "spectacle-full"
            )
            screenshot_process = start_screenshot(
                screenshot_path,
                current_monitor=bool(use_current_monitor_fast_path),
            )
            wait_for_screenshot(screenshot_process)
            screen = cv2.imread(str(screenshot_path), cv2.IMREAD_COLOR)
        if screen is None:
            raise SystemExit(f"Could not read screenshot: {screenshot_path}")
        template = load_template_image(cv2, template_path)

        if args.debug_image:
            debug_path = Path(args.debug_image).expanduser()
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            debug_path.write_bytes(screenshot_path.read_bytes())

        current_monitor_image = bool(
            (kwin_capture or use_current_monitor_fast_path)
            and image_matches_output(screen, primary)
        )
        max_score, center_x, center_y, template_w, template_h, search_scope = (
            match_template_on_screen(
                cv2,
                screen,
                template,
                args.screen_scope,
                primary,
                current_monitor_image=current_monitor_image,
            )
        )
        if (
            args.screen_scope == "primary"
            and use_current_monitor_fast_path
            and max_score < args.threshold
        ):
            screenshot_process = start_screenshot(screenshot_path, current_monitor=False)
            capture_source = "spectacle-full"
            wait_for_screenshot(screenshot_process)
            screen = cv2.imread(str(screenshot_path), cv2.IMREAD_COLOR)
            if screen is None:
                raise SystemExit(f"Could not read screenshot: {screenshot_path}")
            if args.debug_image:
                debug_path.write_bytes(screenshot_path.read_bytes())
            max_score, center_x, center_y, template_w, template_h, search_scope = (
                match_template_on_screen(
                    cv2,
                    screen,
                    template,
                    args.screen_scope,
                    primary,
                    current_monitor_image=False,
                )
            )

        click_x, click_y, coordinate_mode = click_coordinates_for_point(
            center_x,
            center_y,
            use_output_local_coordinates=args.coordinate_mode == "output-local",
        )

        if max_score < args.threshold:
            raise SystemExit(
                f"Match below threshold {args.threshold:.2f}; not clicking"
            )

        cursor_position = None
        if args.move_only:
            cursor_position = click_at(
                click_x,
                click_y,
                args.ydotool_socket,
                repeat=0,
                next_delay_ms=args.double_click_delay,
            )
        elif not args.dry_run:
            cursor_position = click_at(
                click_x,
                click_y,
                args.ydotool_socket,
                repeat=2 if args.double_click else 1,
                next_delay_ms=args.double_click_delay,
            )

        return TemplateActionResult(
            match_score=max_score,
            screenshot_x=center_x,
            screenshot_y=center_y,
            click_x=click_x,
            click_y=click_y,
            coordinate_mode=coordinate_mode,
            search_scope=search_scope,
            capture_source=capture_source,
            template_width=template_w,
            template_height=template_h,
            cursor_position=cursor_position,
        )


def main() -> int:
    args = parse_args()

    def cleanup(_signum=None, _frame=None):
        CLICK_ABORT_FILE.touch()
        CLICK_LOCK_FILE.unlink(missing_ok=True)
        raise SystemExit("Click automation interrupted")

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    result = run_template_action(args)
    print(result.summary())
    cursor_summary = result.cursor_summary()
    if cursor_summary:
        print(cursor_summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
