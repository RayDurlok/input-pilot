#!/usr/bin/env python3
"""Find a template image on the current KDE Wayland screen and click it."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


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

    subprocess.run(
        [ydotool, "mousemove", "--absolute", "-x", str(x), "-y", str(y)],
        check=True,
        env=env,
    )
    click_command = [ydotool, "click"]
    if repeat > 1:
        click_command.extend(
            ["--repeat", str(repeat), "--next-delay", str(next_delay_ms)]
        )
    click_command.append("0xC0")
    subprocess.run(click_command, check=True, env=env)


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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cv2 = import_cv2()

    template_path = Path(args.template).expanduser()
    if not template_path.is_file():
        raise SystemExit(f"Template image not found: {template_path}")

    if args.delay > 0:
        time.sleep(args.delay)

    with tempfile.TemporaryDirectory(prefix="wayland-click-image-") as tmp_dir:
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
        print(
            f"match={max_score:.3f} x={center_x} y={center_y} "
            f"template={template_w}x{template_h}"
        )

        if max_score < args.threshold:
            raise SystemExit(
                f"Match below threshold {args.threshold:.2f}; not clicking"
            )

        if not args.dry_run:
            click_at(
                center_x,
                center_y,
                args.ydotool_socket,
                repeat=2 if args.double_click else 1,
                next_delay_ms=args.double_click_delay,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
