#!/usr/bin/env python3
"""Persistent template-click helper for Input Pilot."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from argparse import Namespace
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
CLICK_SCRIPT = SCRIPT_DIR / "wayland-click-image.py"
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/input-pilot-{os.getuid()}"))
SOCKET_PATH = RUNTIME_DIR / "input-pilot-template.sock"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
LOG_FILE = STATE_DIR / "wayland-automation/template-server.log"


def load_click_module():
    spec = importlib.util.spec_from_file_location("input_pilot_click_image", CLICK_SCRIPT)
    if not spec or not spec.loader:
        raise SystemExit(f"Could not load click script: {CLICK_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def socket_path() -> Path:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    return SOCKET_PATH


def log(message: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {message}\n")


def send_request(payload: dict, timeout: float = 8) -> dict:
    path = socket_path()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(path))
        client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        chunks = []
        while True:
            chunk = client.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    if not chunks:
        raise RuntimeError("template server returned no response")
    return json.loads(b"".join(chunks).decode("utf-8"))


def ping_server() -> bool:
    try:
        response = send_request({"action": "ping"}, timeout=1)
    except (OSError, RuntimeError, json.JSONDecodeError):
        return False
    return bool(response.get("ok"))


def ensure_server() -> None:
    if ping_server():
        return

    path = socket_path()
    if path.exists():
        path.unlink(missing_ok=True)

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_handle = LOG_FILE.open("a", encoding="utf-8")
    subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--server"],
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=log_handle,
        start_new_session=True,
    )

    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        if ping_server():
            return
        time.sleep(0.05)
    raise SystemExit("Input Pilot template server did not start")


def request_args_from_payload(payload: dict) -> Namespace:
    return Namespace(
        template=str(payload["template"]),
        threshold=float(payload.get("threshold", 0.82)),
        delay=float(payload.get("delay", 0.0)),
        dry_run=bool(payload.get("dry_run", False)),
        move_only=bool(payload.get("move_only", False)),
        double_click=bool(payload.get("double_click", False)),
        double_click_delay=int(payload.get("double_click_delay", 35)),
        debug_image=payload.get("debug_image"),
        ydotool_socket=payload.get("ydotool_socket"),
        coordinate_mode=payload.get("coordinate_mode", "global"),
        screen_scope=payload.get("screen_scope", "primary"),
    )


def handle_request(payload: dict, click_module, cv2) -> dict:
    action = payload.get("action")
    if action == "ping":
        return {"ok": True}
    if action == "stop":
        return {"ok": True, "stop": True}
    if action != "click":
        return {"ok": False, "error": f"unknown action: {action}"}

    started = time.monotonic()
    result = click_module.run_template_action(request_args_from_payload(payload), cv2=cv2)
    elapsed = time.monotonic() - started
    return {
        "ok": True,
        "summary": result.summary(),
        "cursor": result.cursor_summary(),
        "elapsed": elapsed,
    }


def serve() -> int:
    path = socket_path()
    if path.exists():
        try:
            path.unlink()
        except OSError as exc:
            raise SystemExit(f"Could not remove stale socket {path}: {exc}") from exc

    click_module = load_click_module()
    cv2 = click_module.import_cv2()
    outputs = click_module.read_screen_outputs()
    primary = click_module.primary_output(outputs)
    if primary:
        with tempfile.TemporaryDirectory(prefix="input-pilot-kwin-probe-") as tmp_dir:
            probe = Path(tmp_dir) / "probe.png"
            if click_module.capture_area_with_kwin(probe, primary):
                image = cv2.imread(str(probe), cv2.IMREAD_COLOR)
                if image is None:
                    click_module.KWIN_CAPTURE_USABLE = False
    log(f"template server started kwin_capture={click_module.KWIN_CAPTURE_USABLE}")

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(path))
        path.chmod(0o600)
        server.listen(4)
        while True:
            connection, _address = server.accept()
            with connection:
                raw = connection.recv(65536)
                if not raw:
                    continue
                try:
                    payload = json.loads(raw.decode("utf-8").strip())
                    response = handle_request(payload, click_module, cv2)
                except BaseException as exc:  # noqa: BLE001 - keep server alive
                    response = {"ok": False, "error": str(exc)}
                    log(f"request failed: {exc}")
                connection.sendall(json.dumps(response).encode("utf-8") + b"\n")
                if response.get("stop"):
                    break
    path.unlink(missing_ok=True)
    log("template server stopped")
    return 0


def fallback_click(args: argparse.Namespace) -> int:
    command = [str(CLICK_SCRIPT), str(args.template)]
    if args.dry_run:
        command.append("--dry-run")
    if args.move_only:
        command.append("--move-only")
    if args.double_click:
        command.append("--double-click")
    command.extend(["--double-click-delay", str(args.double_click_delay)])
    if args.ydotool_socket:
        command.extend(["--ydotool-socket", args.ydotool_socket])
    command.extend(["--screen-scope", args.screen_scope])
    command.extend(["--coordinate-mode", args.coordinate_mode])
    return subprocess.run(command, check=False).returncode


def client(args: argparse.Namespace) -> int:
    if args.warmup:
        ensure_server()
        return 0
    if args.stop:
        if ping_server():
            send_request({"action": "stop"}, timeout=1)
        return 0

    ensure_server()
    payload = {
        "action": "click",
        "template": str(args.template),
        "threshold": args.threshold,
        "delay": args.delay,
        "dry_run": args.dry_run,
        "move_only": args.move_only,
        "double_click": args.double_click,
        "double_click_delay": args.double_click_delay,
        "ydotool_socket": args.ydotool_socket,
        "coordinate_mode": args.coordinate_mode,
        "screen_scope": args.screen_scope,
    }
    try:
        response = send_request(payload)
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        log(f"server request failed, falling back: {exc}")
        return fallback_click(args)

    if not response.get("ok"):
        log(f"server returned error, falling back: {response.get('error')}")
        return fallback_click(args)
    print(response.get("summary", ""))
    if response.get("cursor"):
        print(response["cursor"])
    if "elapsed" in response:
        print(f"server_elapsed={response['elapsed']:.3f}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Input Pilot persistent template helper")
    parser.add_argument("template", nargs="?", help="Path to the button/template image")
    parser.add_argument("--server", action="store_true", help="Run the persistent server")
    parser.add_argument("--warmup", action="store_true", help="Start the server and exit")
    parser.add_argument("--stop", action="store_true", help="Stop the server and exit")
    parser.add_argument("--threshold", type=float, default=0.82)
    parser.add_argument("--delay", type=float, default=0.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--move-only", action="store_true")
    parser.add_argument("--double-click", action="store_true")
    parser.add_argument("--double-click-delay", type=int, default=35)
    parser.add_argument("--ydotool-socket")
    parser.add_argument("--coordinate-mode", choices=("output-local", "global"), default="global")
    parser.add_argument("--screen-scope", choices=("primary", "all"), default="primary")
    args = parser.parse_args()
    if not args.server and not args.warmup and not args.stop and not args.template:
        parser.error("template is required unless --server, --warmup, or --stop is used")
    return args


def main() -> int:
    args = parse_args()
    if args.server:
        return serve()
    return client(args)


if __name__ == "__main__":
    raise SystemExit(main())
