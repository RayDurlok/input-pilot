"""Preview one selected Dolphin item after a plain Space key release.

The physical key remains available to Dolphin. Its selection-mode shortcut is
allowed to settle before we leave that mode and show a preview. Never infer a
selection from the current item: Dolphin can focus an unselected item.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
import subprocess
import sys
import time
import runpy
from pathlib import Path
from urllib.parse import urlparse, unquote

SETTINGS_FILE = Path.home() / ".config/wayland-automation/settings.json"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
ACTIVE_WINDOW_FILE = STATE_DIR / "wayland-automation/active-window.json"
PAUSE_FILE = STATE_DIR / "wayland-automation/paused"
SETTING = "dolphin_quick_look"


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def eligible_window() -> dict:
    if PAUSE_FILE.exists() or read_json(SETTINGS_FILE).get(SETTING) is not True:
        return {}
    window = read_json(ACTIVE_WINDOW_FILE)
    classes = {str(window.get(key, "")).lower() for key in ("resource_class", "resource_name")}
    if not classes.intersection({"dolphin", "org.kde.dolphin"}):
        return {}
    if window.get("is_file_dialog") or "dialog" in str(window.get("window_type", "")):
        return {}
    if not isinstance(window.get("window_pid"), int) or window["window_pid"] <= 0:
        return {}
    return window


def enable_accessibility() -> None:
    """Enable Qt's accessibility bridge, without enabling a screen reader."""
    import gi

    gi.require_version("Atspi", "2.0")
    from gi.repository import Gio, GLib

    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    bus.call_sync(
        "org.a11y.Bus", "/org/a11y/bus", "org.freedesktop.DBus.Properties", "Set",
        GLib.Variant("(ssv)", ("org.a11y.Status", "IsEnabled", GLib.Variant("b", True))),
        None, Gio.DBusCallFlags.NONE, 1000, None,
    )


def find_window_frame(desktop, pid, window_title, atspi):
    """Match the live D-Bus title, not KWin's last window-activation snapshot.

    Navigating folders or switching tabs changes Dolphin's title without
    activating another window. Qt's accessible name adds the application name
    to QWidget.windowTitle on Plasma.
    """
    titles = {window_title, f"{window_title} — Dolphin"}
    frames = []
    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        if app is None or app.get_process_id() != pid:
            continue
        app.set_cache_mask(atspi.Cache.NONE)
        for j in range(app.get_child_count()):
            frame = app.get_child_at_index(j)
            if (frame.get_role() == atspi.Role.FRAME
                    and frame.get_name() in titles
                    and frame.get_state_set().contains(atspi.StateType.SHOWING)):
                frames.append(frame)
    return frames[0] if len(frames) == 1 else None


def find_single_selection(frame, atspi):
    """Fail closed for editors, menus, ambiguous split views or missing data.

    Dolphin marks its current list item focused even when an editor has focus.
    Inspect the rest of the visible window as well, rather than trusting that
    list-item flag on its own. Do not enumerate thousands of file children.
    """
    views = []
    focused_containers = []
    stack = [(frame, ())]
    visited = 0
    while stack:
        obj, ancestors = stack.pop()
        visited += 1
        if visited > 600:
            return None
        state = obj.get_state_set()
        if not state.contains(atspi.StateType.SHOWING):
            continue
        role = obj.get_role()
        if role in (atspi.Role.POPUP_MENU, atspi.Role.DIALOG):
            return None
        if role == atspi.Role.LIST and state.contains(atspi.StateType.MULTISELECTABLE):
            views.append((obj, ancestors))
            continue
        if state.contains(atspi.StateType.FOCUSED):
            # Qt reports focus on the graphics viewport around the file list.
            # It also identifies the active pane when Dolphin uses split view.
            if role != atspi.Role.FILLER:
                return None
            focused_containers.append(obj)
        # Places, tab bars and other lists are never file views.
        if role in (atspi.Role.LIST, atspi.Role.TREE, atspi.Role.PAGE_TAB_LIST):
            continue
        stack.extend((obj.get_child_at_index(i), (*ancestors, obj))
                     for i in range(obj.get_child_count()))

    if focused_containers:
        views = [(view, ancestors) for view, ancestors in views
                 if all(container in ancestors for container in focused_containers)]
    if len(views) != 1:
        return None
    view = views[0][0]
    selection = view.get_selection_iface()
    if selection is None or selection.get_n_selected_children() != 1:
        return None
    item = selection.get_selected_child(0)
    if item is None:
        return None
    state = item.get_state_set()
    if not state.contains(atspi.StateType.SELECTED) or not state.contains(atspi.StateType.FOCUSED):
        return None
    return view, item


def local_path(uri: str | None) -> Path | None:
    if uri is None:
        return None
    parsed = urlparse(uri)
    if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
        return None
    return Path(unquote(parsed.path))


class FilePreviewNavigator:
    """Browse a snapshot of Dolphin's order without changing its selection."""

    def __init__(self, paths, index, source_valid):
        self.paths = paths
        self.index = index
        self.source_valid = source_valid

    def step(self, direction: int) -> Path | None:
        if not self.source_valid():
            return None
        index = self.index + direction
        while 0 <= index < len(self.paths):
            path = self.paths[index]
            if path is not None and path.exists():
                self.index = index
                return path
            index += direction
        return None


@contextmanager
def paused_window_updates(get_updates, set_updates):
    """Keep the original selection on screen during the URI-list snapshot."""
    enabled = get_updates()
    try:
        if enabled:
            set_updates(False)
        yield
    finally:
        # Restore painting even if copying or restoring the selection fails.
        if enabled:
            set_updates(True)


def snapshot_navigation(view, item, initial_uri, copy_action, source_valid):
    """Read Dolphin's ordered URI list while it still owns keyboard focus.

    Wayland denies clipboard changes from background windows. Copying on each
    arrow press can therefore return stale clipboard data. Select all only for
    this initial read, and restore the original single selection immediately.
    Validate count and the original URI's index instead of guessing paths from
    accessibility labels (which is unsafe for search results/hidden extensions).
    """
    single = ([local_path(initial_uri)], 0)
    count = view.get_child_count()
    index = item.get_index_in_parent()
    if count < 2 or not 0 <= index < count or not source_valid():
        return single
    selection = view.get_selection_iface()
    if selection.get_n_selected_children() != 1 or selection.get_selected_child(0) != item:
        return single
    try:
        if not selection.select_all():
            return single

        def all_selected():
            view.clear_cache()
            return (source_valid() and view.get_child_count() == count
                    and selection.get_n_selected_children() == count)

        uris = selected_uris(copy_action, all_selected)
        if uris is None or len(uris) != count or uris[index] != initial_uri or not all_selected():
            return single
        return [local_path(uri) for uri in uris], index
    finally:
        # Also restore after a focus switch. Only undo the all-selection we
        # created, never a different selection the user made in the meantime.
        if (view.get_child_count() == count and view.get_child_at_index(index) == item
                and selection.get_n_selected_children() == count):
            selection.clear_selection()
            selection.select_child(index)


def preview_selection(expected: dict) -> bool:
    import gi

    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi, Gio, GLib

    Atspi.set_timeout(300, 700)
    if not expected or eligible_window() != expected:
        return False
    service = f"org.kde.dolphin-{expected['window_pid']}"
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def call(path, interface, method, parameters=None):
        return bus.call_sync(service, path, interface, method, parameters, None,
                             Gio.DBusCallFlags.NONE, 500, None).unpack()

    # Enumerate window paths: Dolphin may have several windows in one process.
    import xml.etree.ElementTree as ET

    xml = call("/dolphin", "org.freedesktop.DBus.Introspectable", "Introspect")[0]
    paths = ["/dolphin/" + node.attrib["name"] for node in ET.fromstring(xml).findall("node")]
    active = [path for path in paths if path.rsplit("/", 1)[-1].startswith("Dolphin_")
              and call(path, "org.kde.dolphin.MainWindow", "isActiveWindow")[0]]
    if len(active) != 1:
        return False
    path = active[0]

    def current_title():
        return call(path, "org.freedesktop.DBus.Properties", "Get",
                    GLib.Variant("(ss)", ("org.qtproject.Qt.QWidget", "windowTitle")))[0]

    window_title = current_title()
    frame = find_window_frame(Atspi.get_desktop(0), expected["window_pid"], window_title, Atspi)
    if frame is None:
        return False
    target = find_single_selection(frame, Atspi)
    if target is None:
        return False

    def context_valid():
        return (eligible_window() == expected
                and call(path, "org.kde.dolphin.MainWindow", "isActiveWindow")[0]
                and current_title() == window_title)

    def still_valid():
        frame.clear_cache()
        target[0].clear_cache()
        target[1].clear_cache()
        return context_valid() and find_single_selection(frame, Atspi) == target

    # The full selection scan above is fresh; only the window context needs
    # rechecking before querying/leaving selection mode. Clipboard reads below
    # validate the selection again immediately around the copy operation.
    if not context_valid():
        return False
    action_path = path + "/actions/toggle_selection_mode"
    checked = call(action_path, "org.freedesktop.DBus.Properties", "Get",
                   GLib.Variant("(ss)", ("org.qtproject.Qt.QAction", "checked")))[0]
    if checked:
        call(path, "org.kde.KMainWindow", "activateAction",
             GLib.Variant("(s)", ("toggle_selection_mode",)))
    # Leave Dolphin's native selection mode before displaying the preview.
    if call(action_path, "org.freedesktop.DBus.Properties", "Get",
            GLib.Variant("(ss)", ("org.qtproject.Qt.QAction", "checked")))[0]:
        return False
    def copy_action():
        # Qt/Wayland may acknowledge activateAction(edit_copy) without publishing
        # a fresh clipboard offer. A real shortcut provides the input serial
        # required for clipboard ownership. The source must still own focus.
        if not context_valid():
            return (False,)
        env = dict(os.environ)
        env.setdefault("YDOTOOL_SOCKET", "/tmp/ydotool_socket")
        result = subprocess.run(["ydotool", "key", "--key-delay=1", "29:1", "46:1", "46:0", "29:0"],
                                env=env, timeout=1, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return (result.returncode == 0,)

    uri = selected_uri(copy_action, still_valid)
    if uri is None:
        return False
    file_path = local_path(uri)
    if file_path is None:
        return False
    from input_pilot_preview_window import show_preview

    def source_valid():
        # Never change Dolphin's background selection if the user has switched
        # to another application or another Dolphin tab since opening Quick Look.
        window = read_json(ACTIVE_WINDOW_FILE)
        target[0].clear_cache()
        return (not PAUSE_FILE.exists()
                and read_json(SETTINGS_FILE).get(SETTING) is True
                and window.get("window_pid") == os.getpid()
                and current_title() == window_title
                and target[0].get_state_set().contains(Atspi.StateType.SHOWING))

    def get_updates():
        return call(path, "org.freedesktop.DBus.Properties", "Get",
                    GLib.Variant("(ss)", ("org.qtproject.Qt.QWidget", "updatesEnabled")))[0]

    def set_updates(enabled):
        call(path, "org.freedesktop.DBus.Properties", "Set",
             GLib.Variant("(ssv)", ("org.qtproject.Qt.QWidget", "updatesEnabled",
                                    GLib.Variant("b", enabled))))

    with paused_window_updates(get_updates, set_updates):
        paths, index = snapshot_navigation(target[0], target[1], uri, copy_action, context_valid)
    if not still_valid():
        return False
    navigator = FilePreviewNavigator(paths, index, source_valid)
    show_preview(file_path, navigate=navigator.step)
    return True


def selected_uri(copy_action, still_valid) -> str | None:
    uris = selected_uris(copy_action, still_valid)
    return uris[0] if uris is not None and len(uris) == 1 else None


def selected_uris(copy_action, still_valid) -> list[str] | None:
    """Use Dolphin's URI list, preserving the clipboard with the existing helper."""
    clipboard = runpy.run_path(str(Path(__file__).with_name("input-pilot-folder-template.py")))
    saved = clipboard["save_clipboard"]()
    # A nonempty clipboard we cannot snapshot must not be overwritten.
    if saved is None:
        listing = subprocess.run(["wl-paste", "--list-types"], capture_output=True, timeout=1)
        if listing.returncode == 0 and listing.stdout.strip():
            return None
    try:
        if not still_valid():
            return None
        # Clipboard publication is asynchronous on Wayland. Clear the old URI
        # offer with a private marker so an immediate read cannot silently
        # return the previously copied file while Dolphin's new offer is pending.
        subprocess.run(["wl-copy", "--type", "application/x-input-pilot-preview"],
                       input=b"pending", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=True, timeout=1)
        if not still_valid() or not copy_action()[0]:
            return None
        deadline = time.monotonic() + 0.8
        while time.monotonic() < deadline:
            result = subprocess.run(["wl-paste", "--no-newline", "--type", "text/uri-list"],
                                    capture_output=True, text=True, timeout=1)
            # Validate the result after the read, including focus/selection
            # changes during clipboard publication. No extra full-window scan
            # is needed in the caller for this same result.
            if not still_valid():
                return None
            if result.returncode == 0:
                return [line for line in result.stdout.splitlines() if line and not line.startswith("#")]
            time.sleep(0.02)
        return None
    finally:
        if saved is not None:
            clipboard["restore_clipboard"](saved)
        else:
            subprocess.run(["wl-copy", "--clear"], timeout=1, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window", required=True)
    parser.add_argument("--wait-for-release", action="store_true",
                        help="Prepare imports on key-down; preview only after confirmation on stdin")
    args = parser.parse_args()
    try:
        if args.wait_for_release:
            # Warm the UI and accessibility connection without inspecting or
            # changing Dolphin's selection. EOF/cancellation never opens a UI.
            import gi
            gi.require_version("Atspi", "2.0")
            from gi.repository import Atspi
            import input_pilot_preview_window

            Atspi.get_desktop(0)
            if sys.stdin.readline() != "preview\n":
                return 0
        # Live D-Bus/accessibility queries validate Dolphin's settled state;
        # no fixed sleep is needed before beginning those round trips.
        preview_selection(json.loads(args.window))
    except Exception as exc:
        # Accessibility may disappear as a window closes; never guess a target.
        log = STATE_DIR / "wayland-automation/dolphin-preview.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
