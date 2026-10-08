import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import input_pilot_dolphin_preview as preview

spec = importlib.util.spec_from_file_location(
    "suspend_listener", Path(__file__).resolve().parents[1] / "input-pilot-suspend-listener.py")
listener = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = listener
spec.loader.exec_module(listener)

ATSPI = SimpleNamespace(
    StateType=SimpleNamespace(SHOWING="showing", FOCUSED="focused", SELECTED="selected", MULTISELECTABLE="multi"),
    Role=SimpleNamespace(LIST="list", POPUP_MENU="menu", DIALOG="dialog", TREE="tree", PAGE_TAB_LIST="tabs", FILLER="filler", FRAME="frame"),
    Cache=SimpleNamespace(NONE=0),
)


class Node:
    def __init__(self, role, states=("showing",), children=(), selected=()):
        self.role, self.states, self.children, self.selected = role, states, children, selected

    def get_state_set(self):
        return SimpleNamespace(contains=lambda state: state in self.states)

    def get_role(self): return self.role
    def get_child_count(self): return len(self.children)
    def get_child_at_index(self, index): return self.children[index]
    def get_selection_iface(self): return self
    def get_n_selected_children(self): return len(self.selected)
    def get_selected_child(self, index): return self.selected[index]


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.item = Node("item", ("showing", "selected", "focused"))
        self.view = Node("list", ("showing", "multi"), selected=[self.item])

    def find(self, *children):
        return preview.find_single_selection(Node("frame", children=children), ATSPI)

    def test_single_selection(self):
        self.assertEqual(self.find(self.view), (self.view, self.item))

    def test_focused_viewport_identifies_active_split_pane(self):
        active = Node("filler", ("showing", "focused"), children=[self.view])
        other = Node("list", ("showing", "multi"), selected=[self.item, self.item])
        self.assertEqual(self.find(active, other), (self.view, self.item))

    def test_unrelated_focused_container_blocks(self):
        self.assertIsNone(self.find(self.view, Node("filler", ("showing", "focused"))))

    def test_zero_or_multiple_selected(self):
        for selected in ([], [self.item, self.item]):
            self.view.selected = selected
            self.assertIsNone(self.find(self.view))

    def test_editor_focus_overrides_dolphins_stale_item_focus(self):
        for role in ("text", "terminal", "button"):
            self.assertIsNone(self.find(self.view, Node(role, ("showing", "focused"))))

    def test_hidden_editor_does_not_block(self):
        self.assertIsNotNone(self.find(self.view, Node("text", ("focused",))))

    def test_menus_and_ambiguous_split_views(self):
        self.assertIsNone(self.find(self.view, Node("menu")))
        self.assertIsNone(self.find(self.view, self.view))

    def test_selected_item_must_also_be_current(self):
        self.item.states = ("showing", "selected")
        self.assertIsNone(self.find(self.view))


class WindowTitleTests(unittest.TestCase):
    def test_navigation_matches_live_title_instead_of_old_activation_caption(self):
        frame = Node("frame")
        frame.get_name = lambda: "Images — Dolphin"
        app = Node("application", children=[frame])
        app.get_process_id = lambda: 123
        app.set_cache_mask = Mock()
        desktop = Node("desktop", children=[app])
        self.assertIsNone(preview.find_window_frame(desktop, 123, "Downloads", ATSPI))
        self.assertIs(preview.find_window_frame(desktop, 123, "Images", ATSPI), frame)
        self.assertIsNone(preview.find_window_frame(desktop, 456, "Images", ATSPI))

    def test_duplicate_window_titles_fail_closed(self):
        frame = Node("frame")
        frame.get_name = lambda: "Images — Dolphin"
        app = Node("application", children=[frame, frame])
        app.get_process_id = lambda: 123
        app.set_cache_mask = Mock()
        self.assertIsNone(preview.find_window_frame(Node("desktop", children=[app]), 123, "Images", ATSPI))


class EligibilityTests(unittest.TestCase):
    def test_disabled_by_default_and_respects_pause_and_window_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.multiple(preview, SETTINGS_FILE=root / "settings", PAUSE_FILE=root / "pause",
                                ACTIVE_WINDOW_FILE=root / "window"):
                window = {"resource_class": "org.kde.dolphin", "window_pid": 123}
                preview.ACTIVE_WINDOW_FILE.write_text(json.dumps(window))
                self.assertEqual(preview.eligible_window(), {})
                preview.SETTINGS_FILE.write_text(json.dumps({preview.SETTING: True}))
                self.assertEqual(preview.eligible_window(), window)
                preview.PAUSE_FILE.touch()
                self.assertEqual(preview.eligible_window(), {})
                preview.PAUSE_FILE.unlink()
                window.update(resource_class="editor", caption="Dolphin")
                preview.ACTIVE_WINDOW_FILE.write_text(json.dumps(window))
                self.assertEqual(preview.eligible_window(), {})


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # Deliberately not alphabetic: the Dolphin view determines the order.
        self.paths = [Path(self.tmp.name) / name for name in ("b.png", "z.pdf", "a.webm")]
        for path in self.paths:
            path.touch()
        self.valid = Mock(return_value=True)
        self.navigator = preview.FilePreviewNavigator(self.paths, 0, self.valid)

    def test_navigation_uses_dolphin_order(self):
        for direction, expected in ((1, 1), (1, 2), (-1, 1), (-1, 0)):
            self.assertEqual(self.navigator.step(direction), self.paths[expected])

    def test_boundaries_do_not_wrap(self):
        self.assertIsNone(self.navigator.step(-1))
        self.navigator.index = 2
        self.assertIsNone(self.navigator.step(1))

    def test_changed_source_blocks_navigation(self):
        self.valid.return_value = False
        self.assertIsNone(self.navigator.step(1))
        self.assertEqual(self.navigator.index, 0)

    def test_removed_files_are_skipped(self):
        self.paths[1].unlink()
        self.assertEqual(self.navigator.step(1), self.paths[2])
        self.assertEqual(self.navigator.step(-1), self.paths[0])

    def test_snapshot_restores_original_selection_even_on_read_error(self):
        items = [Node("item") for _ in self.paths]
        items[1].get_index_in_parent = lambda: 1
        view = Node("list", children=items, selected=[items[1]])
        view.clear_cache = Mock()
        view.select_all = lambda: setattr(view, "selected", items[:]) or True
        view.clear_selection = lambda: setattr(view, "selected", []) or True
        view.select_child = lambda i: view.selected.append(items[i]) or True
        uris = [path.as_uri() for path in self.paths]
        with patch.object(preview, "selected_uris", return_value=uris):
            result = preview.snapshot_navigation(view, items[1], uris[1], Mock(), self.valid)
            self.assertEqual(result, (self.paths, 1))
            self.assertEqual(view.selected, [items[1]])
        with patch.object(preview, "selected_uris", side_effect=OSError("Read failed")):
            with self.assertRaises(OSError):
                preview.snapshot_navigation(view, items[1], uris[1], Mock(), self.valid)
            self.assertEqual(view.selected, [items[1]])
        with patch.object(preview, "selected_uris", return_value=uris[:1]):
            result = preview.snapshot_navigation(view, items[1], uris[1], Mock(), self.valid)
            self.assertEqual(result, ([self.paths[1]], 0))
            self.assertEqual(view.selected, [items[1]])
        def lose_focus(*_args):
            self.valid.return_value = False
            return None
        with patch.object(preview, "selected_uris", side_effect=lose_focus):
            preview.snapshot_navigation(view, items[1], uris[1], Mock(), self.valid)
            self.assertEqual(view.selected, [items[1]])


class ClipboardTests(unittest.TestCase):
    def test_waits_for_new_uri_offer_and_restores_saved_clipboard(self):
        clipboard = {"save_clipboard": Mock(return_value=("text/plain", b"saved")),
                     "restore_clipboard": Mock()}
        events = []
        reads = 0
        def run(command, **kwargs):
            nonlocal reads
            if "--list-types" in command:
                return SimpleNamespace(returncode=0, stdout=b"text/plain")
            if command[0] == "wl-copy":
                events.append("marker")
                return SimpleNamespace(returncode=0)
            reads += 1
            return SimpleNamespace(returncode=1 if reads == 1 else 0,
                                   stdout="" if reads == 1 else "file:///tmp/new.png\r\n")
        def copy():
            events.append("copy")
            return (True,)
        with patch.object(preview.runpy, "run_path", return_value=clipboard), \
             patch.object(preview.subprocess, "run", side_effect=run), \
             patch.object(preview.time, "sleep"):
            self.assertEqual(preview.selected_uri(copy, lambda: True), "file:///tmp/new.png")
        self.assertEqual(events, ["marker", "copy"])
        self.assertEqual(reads, 2)
        clipboard["restore_clipboard"].assert_called_once_with(("text/plain", b"saved"))


class ZoomTests(unittest.TestCase):
    def test_pointer_stays_over_same_content_when_zooming(self):
        from input_pilot_preview_window import ZoomView

        view = ZoomView(1800, 1200, zoom=2)
        scale, x, y = view.transform(900, 650)
        anchor = ((620 - x) / scale, (220 - y) / scale)
        view.zoom_at(1, 620, 220, 900, 650)
        scale, x, y = view.transform(900, 650)
        self.assertAlmostEqual((620 - x) / scale, anchor[0])
        self.assertAlmostEqual((220 - y) / scale, anchor[1])
        view.zoom_at(-1, 620, 220, 900, 650)
        self.assertAlmostEqual(view.zoom, 2)
        self.assertAlmostEqual(view.offset_x, 0)
        self.assertAlmostEqual(view.offset_y, 0)

    def test_limits_and_reset_keep_content_visible(self):
        from input_pilot_preview_window import ZoomView

        view = ZoomView(1800, 1200)
        for _ in range(20):
            view.zoom_at(20, 0, 0, 900, 650)
        self.assertEqual(view.zoom, 16)
        view.offset_x, view.offset_y = 1e6, -1e6
        scale, x, y = view.transform(900, 650)
        self.assertLessEqual(x, 0)
        self.assertGreaterEqual(y + 1200 * scale, 650)
        for _ in range(20):
            view.zoom_at(-20, 0, 0, 900, 650)
        self.assertEqual(view.zoom, 0.25)
        self.assertEqual((view.offset_x, view.offset_y), (0, 0))
        view.reset()
        self.assertEqual(view.zoom, 1)

    def test_wheel_and_touchpad_directions(self):
        from input_pilot_preview_window import ZoomArea, Gdk

        area = SimpleNamespace(view=Mock(), drag=object(), queue_draw=Mock(),
                               get_allocation=lambda: SimpleNamespace(width=900, height=650))
        for direction, steps in ((Gdk.ScrollDirection.UP, 1), (Gdk.ScrollDirection.DOWN, -1),
                                 (Gdk.ScrollDirection.SMOOTH, -0.3)):
            event = SimpleNamespace(direction=direction, x=400, y=300,
                                    get_scroll_deltas=lambda: (True, 0, 0.3))
            self.assertTrue(ZoomArea.on_scroll(area, None, event))
            area.view.zoom_at.assert_called_with(steps, 400, 300, 900, 650)
        self.assertIsNone(area.drag)


class PreviewKeyTests(unittest.TestCase):
    def test_file_arrows_and_pdf_page_keys_are_separate(self):
        from input_pilot_preview_window import PreviewWindow, Gdk

        window = SimpleNamespace(change_file=Mock(), change_pdf_page=Mock(), pdf=object())
        for key, direction in ((Gdk.KEY_Right, 1), (Gdk.KEY_Down, 1),
                               (Gdk.KEY_Left, -1), (Gdk.KEY_Up, -1)):
            self.assertTrue(PreviewWindow.on_key(window, None, SimpleNamespace(keyval=key, state=0)))
            window.change_file.assert_called_with(direction)
        window.change_pdf_page.assert_not_called()
        for key, direction in ((Gdk.KEY_Page_Down, 1), (Gdk.KEY_Page_Up, -1)):
            self.assertTrue(PreviewWindow.on_key(window, None, SimpleNamespace(keyval=key, state=0)))
            window.change_pdf_page.assert_called_with(direction)


class KeyboardTests(unittest.TestCase):
    def setUp(self):
        self.subject = listener.SuspendListener(None)
        self.subject.shortcut = listener.Shortcut(frozenset(), "F12")
        self.subject.refresh_settings = Mock()
        self.window = {"window_pid": 123}

    def test_one_preview_on_release_and_no_repeat_launches(self):
        with patch.object(listener, "eligible_window", return_value=self.window), patch.object(listener.subprocess, "Popen") as spawn:
            self.subject.handle_key(listener.ecodes.KEY_SPACE, 1)
            self.subject.handle_key(listener.ecodes.KEY_SPACE, 2)
            spawn.assert_not_called()
            self.subject.handle_key(listener.ecodes.KEY_SPACE, 0)
            spawn.assert_called_once()
            self.subject.handle_key(listener.ecodes.KEY_SPACE, 0)
            spawn.assert_called_once()

    def test_modifier_or_window_change_cancels(self):
        with patch.object(listener, "eligible_window", return_value=self.window) as window, patch.object(listener.subprocess, "Popen") as spawn:
            self.subject.handle_key(listener.ecodes.KEY_SPACE, 1)
            self.subject.handle_key(listener.ecodes.KEY_LEFTCTRL, 1)
            self.subject.handle_key(listener.ecodes.KEY_LEFTCTRL, 0)
            self.subject.handle_key(listener.ecodes.KEY_SPACE, 0)
            spawn.assert_not_called()
            self.subject.handle_key(listener.ecodes.KEY_SPACE, 1)
            window.return_value = {}
            self.subject.handle_key(listener.ecodes.KEY_SPACE, 0)
            spawn.assert_not_called()

    def test_space_master_key_has_priority(self):
        self.subject.shortcut = listener.Shortcut(frozenset(), "Space")
        with patch.object(listener, "run_abort_toggle") as suspend, patch.object(listener.subprocess, "Popen") as spawn:
            self.subject.handle_key(listener.ecodes.KEY_SPACE, 1)
            self.subject.handle_key(listener.ecodes.KEY_SPACE, 0)
            suspend.assert_called_once()
            spawn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
