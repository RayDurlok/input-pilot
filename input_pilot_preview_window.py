"""Quick Look for local images, audio, videos and PDFs, with file navigation."""

from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk


@dataclass
class ZoomView:
    width: float
    height: float
    upscale: bool = False
    zoom: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0

    def transform(self, width, height):
        fit = min(max(1, width - 16) / self.width, max(1, height - 16) / self.height)
        scale = (fit if self.upscale else min(1, fit)) * self.zoom
        limit_x = max(0, (self.width * scale - width) / 2)
        limit_y = max(0, (self.height * scale - height) / 2)
        self.offset_x = max(-limit_x, min(limit_x, self.offset_x))
        self.offset_y = max(-limit_y, min(limit_y, self.offset_y))
        return (scale, (width - self.width * scale) / 2 + self.offset_x,
                (height - self.height * scale) / 2 + self.offset_y)

    def zoom_at(self, steps, x, y, width, height):
        old_scale, old_x, old_y = self.transform(width, height)
        self.zoom = max(0.25, min(16, self.zoom * 1.2 ** max(-20, min(20, steps))))
        scale, _, _ = self.transform(width, height)
        self.offset_x = x - (x - old_x) * scale / old_scale - (width - self.width * scale) / 2
        self.offset_y = y - (y - old_y) * scale / old_scale - (height - self.height * scale) / 2
        self.transform(width, height)

    def reset(self):
        self.zoom = 1.0
        self.offset_x = self.offset_y = 0.0


class ZoomArea(Gtk.DrawingArea):
    """Shared image/PDF viewport; render at the current scale, not a cached thumbnail."""

    def __init__(self, width, height, render, upscale=False):
        super().__init__()
        self.view = ZoomView(width, height, upscale)
        self.render = render
        self.drag = None
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.add_events(Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK
                        | Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                        | Gdk.EventMask.POINTER_MOTION_MASK)
        self.connect("draw", self.on_draw)
        self.connect("scroll-event", self.on_scroll)
        self.connect("button-press-event", self.on_press)
        self.connect("button-release-event", self.on_release)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("grab-broken-event", self.on_release)

    def on_draw(self, widget, context):
        allocation = self.get_allocation()
        scale, x, y = self.view.transform(allocation.width, allocation.height)
        context.save()
        try:
            context.translate(x, y)
            context.scale(scale, scale)
            context.rectangle(0, 0, self.view.width, self.view.height)
            context.clip()
            self.render(context)
        finally:
            context.restore()
        return False

    def on_scroll(self, widget, event):
        if event.direction == Gdk.ScrollDirection.UP:
            steps = 1
        elif event.direction == Gdk.ScrollDirection.DOWN:
            steps = -1
        elif event.direction == Gdk.ScrollDirection.SMOOTH:
            ok, _dx, dy = event.get_scroll_deltas()
            if not ok or not dy:
                return False
            steps = -dy
        else:
            return False
        allocation = self.get_allocation()
        self.view.zoom_at(steps, event.x, event.y, allocation.width, allocation.height)
        self.drag = None
        self.queue_draw()
        return True

    def on_press(self, widget, event):
        if event.button != 1:
            return False
        if event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS:
            self.reset()
        else:
            self.drag = (event.x, event.y, self.view.offset_x, self.view.offset_y)
        return True

    def on_motion(self, widget, event):
        if self.drag is None:
            return False
        if not event.state & Gdk.ModifierType.BUTTON1_MASK:
            self.drag = None
            return False
        x, y, offset_x, offset_y = self.drag
        self.view.offset_x = offset_x + event.x - x
        self.view.offset_y = offset_y + event.y - y
        self.queue_draw()
        return True

    def on_release(self, widget, event):
        self.drag = None
        return False

    def reset(self, *_args):
        self.drag = None
        self.view.reset()
        self.queue_draw()


class PreviewWindow(Gtk.Window):
    def __init__(self, path: Path, navigate=None):
        super().__init__(title=f"{path.name} — Input Pilot Preview")
        self.set_wmclass("input-pilot-preview", "InputPilotPreview")
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_default_size(900, 650)
        self.set_border_width(12)
        self.navigate = navigate
        self.player = None
        self.timeline_timer = None
        self.video_handler = None
        self.pdf = None
        self.video_bus = None
        self.playing = False
        self.closed = False
        self.connect("destroy", self.on_destroy)
        self.connect("key-press-event", self.on_key)

        self.header = Gtk.HeaderBar(title=path.name, subtitle="Arrow keys: previous/next file · Space/Esc: close")
        self.header.set_show_close_button(True)
        self.set_titlebar(self.header)
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(self.content)
        self.load_path(path)
        self.show_all()
        self.present()
        GLib.timeout_add(200, self.check_enabled)

    def load_path(self, path: Path):
        self.stop_media()
        for child in self.content.get_children():
            child.destroy()
        self.path = path
        self.pdf = None
        self.pixbuf = None
        self.header.set_title(path.name)
        self.header.set_subtitle("Arrow keys: previous/next file · Space/Esc: close")
        self.set_title(f"{path.name} — Input Pilot Preview")
        mime, _ = Gio.content_type_guess(str(path), None)
        if path.is_dir():
            self.show_info(path, "Folder")
        elif mime and mime.startswith("image/"):
            try:
                gi.require_foreign("cairo")
                self.pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(path)).apply_embedded_orientation()
                self.image_area = ZoomArea(self.pixbuf.get_width(), self.pixbuf.get_height(), self.draw_image)
                self.content.pack_start(self.image_area, True, True, 0)
                self.add_zoom_controls(self.image_area)
            except (ImportError, GLib.Error):
                self.show_info(path, "This image format cannot be previewed.")
        elif mime == "application/pdf" or path.suffix.lower() == ".pdf":
            try:
                self.show_pdf(path)
            except (ValueError, ImportError, RuntimeError, GLib.Error) as exc:
                self.pdf = None
                self.show_info(path, f"PDF preview unavailable: {exc}")
        elif (mime and mime.startswith(("video/", "audio/"))) or path.suffix.lower() in {".wav", ".mp3"}:
            audio_only = bool(mime and mime.startswith("audio/")) or path.suffix.lower() in {".wav", ".mp3"}
            try:
                self.show_video(path, audio_only=audio_only)
            except (ValueError, ImportError, RuntimeError, GLib.Error) as exc:
                self.stop_media()
                self.show_info(path, f"{'Audio' if audio_only else 'Video'} preview unavailable: {exc}")
        else:
            self.show_info(path, "No preview available for this file type.")
        self.content.show_all()

    def show_info(self, path, message):
        icon = Gtk.Image.new_from_icon_name("folder" if path.is_dir() else "text-x-generic",
                                           Gtk.IconSize.DIALOG)
        self.content.pack_start(icon, True, False, 0)
        label = Gtk.Label(label=message)
        label.set_line_wrap(True)
        self.content.pack_start(label, False, False, 0)
        if path.is_file():
            self.content.pack_start(Gtk.Label(label=GLib.format_size(path.stat().st_size)), False, False, 0)

    def draw_image(self, context):
        Gdk.cairo_set_source_pixbuf(context, self.pixbuf, 0, 0)
        context.paint()

    def add_zoom_controls(self, area):
        controls = Gtk.Box(spacing=10)
        controls.pack_start(Gtk.Label(label="Scroll: zoom · Drag: pan · Double-click: fit"), True, True, 0)
        fit = Gtk.Button(label="Fit")
        fit.connect("clicked", area.reset)
        controls.pack_end(fit, False, False, 0)
        self.content.pack_start(controls, False, False, 0)

    def show_video(self, path, audio_only=False):
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst

        self.gst = Gst
        Gst.init(None)
        player = Gst.ElementFactory.make("playbin", None)
        if player is None:
            raise RuntimeError("install GStreamer playbin")
        self.player = player
        if audio_only:
            # GstPlayFlags: disable VIDEO (1) and VIS (8). Audio playback must
            # not depend on the GTK video sink or wait for a video frame.
            player.set_property("flags", int(player.get_property("flags")) & ~(1 | 8))
            icon = Gtk.Image.new_from_icon_name("audio-x-generic", Gtk.IconSize.DIALOG)
            icon.set_pixel_size(96)
            self.content.pack_start(icon, True, True, 0)
            self.content.pack_start(Gtk.Label(label="Audio preview"), False, False, 0)
        else:
            sink = Gst.ElementFactory.make("gtksink", None)
            if sink is None:
                raise RuntimeError("install the GStreamer GTK video sink")
            player.set_property("video-sink", sink)
            self.content.pack_start(sink.get_property("widget"), True, True, 0)
        player.set_property("uri", path.as_uri())
        controls = Gtk.Box(spacing=8)
        self.play_button = Gtk.Button(label="Pause")
        self.play_button.connect("clicked", self.toggle_play)
        controls.pack_start(self.play_button, False, False, 0)
        self.timeline = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 0.1)
        self.timeline.set_draw_value(False)
        self.timeline.connect("change-value", self.seek)
        controls.pack_start(self.timeline, True, True, 0)
        self.time_label = Gtk.Label(label="0:00 / —")
        controls.pack_end(self.time_label, False, False, 0)
        self.content.pack_start(controls, False, False, 0)
        self.video_bus = player.get_bus()
        self.video_bus.add_signal_watch()
        self.video_handler = self.video_bus.connect("message", self.on_video_message)
        self.playing = True
        if player.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError("GStreamer could not start playback")
        self.timeline_timer = GLib.timeout_add(250, self.update_timeline)

    def toggle_play(self, _button):
        self.playing = not self.playing
        self.player.set_state(self.gst.State.PLAYING if self.playing else self.gst.State.PAUSED)
        self.play_button.set_label("Pause" if self.playing else "Play")

    def seek(self, _scale, _scroll, value):
        ok, duration = self.player.query_duration(self.gst.Format.TIME)
        if ok:
            self.player.seek_simple(self.gst.Format.TIME, self.gst.SeekFlags.FLUSH | self.gst.SeekFlags.KEY_UNIT,
                                    int(duration * value / 100))
        return False

    def update_timeline(self):
        if self.player is None:
            return False
        ok, duration = self.player.query_duration(self.gst.Format.TIME)
        pos_ok, position = self.player.query_position(self.gst.Format.TIME)
        if ok and pos_ok and duration > 0:
            self.timeline.set_value(position / duration * 100)
            def timestamp(value):
                seconds = max(0, int(value / self.gst.SECOND))
                return f"{seconds // 60}:{seconds % 60:02d}"
            self.time_label.set_text(f"{timestamp(position)} / {timestamp(duration)}")
        return True

    def on_video_message(self, bus, message):
        if self.player is None or bus != self.video_bus:
            return
        if message.type == self.gst.MessageType.ERROR:
            error, _ = message.parse_error()
            self.player.set_state(self.gst.State.NULL)
            label = Gtk.Label(label=f"Cannot play this file: {error.message}")
            label.set_line_wrap(True)
            self.content.pack_start(label, False, False, 0)
            label.show()
            self.play_button.set_sensitive(False)
        elif message.type == self.gst.MessageType.EOS:
            self.player.set_state(self.gst.State.PAUSED)
            self.player.seek_simple(self.gst.Format.TIME, self.gst.SeekFlags.FLUSH, 0)
            self.playing = False
            self.play_button.set_label("Play")

    def show_pdf(self, path):
        gi.require_version("Poppler", "0.18")
        gi.require_foreign("cairo")
        from gi.repository import Poppler

        self.pdf = Poppler.Document.new_from_file(path.as_uri(), None)
        if self.pdf.get_n_pages() < 1:
            raise RuntimeError("This PDF has no pages")
        self.pdf_page = 0
        width, height = self.pdf.get_page(0).get_size()
        self.pdf_area = ZoomArea(width, height, self.draw_pdf, upscale=True)
        self.content.pack_start(self.pdf_area, True, True, 0)
        self.add_zoom_controls(self.pdf_area)
        controls = Gtk.Box(spacing=10)
        self.pdf_previous = Gtk.Button(label="Previous page")
        self.pdf_previous.connect("clicked", lambda _button: self.change_pdf_page(-1))
        self.pdf_next = Gtk.Button(label="Next page")
        self.pdf_next.connect("clicked", lambda _button: self.change_pdf_page(1))
        self.pdf_status = Gtk.Label()
        controls.pack_start(self.pdf_previous, False, False, 0)
        controls.pack_start(self.pdf_status, True, True, 0)
        controls.pack_start(self.pdf_next, False, False, 0)
        self.content.pack_start(controls, False, False, 0)
        self.update_pdf_controls()

    def draw_pdf(self, context):
        if self.pdf is None:
            return False
        page = self.pdf.get_page(self.pdf_page)
        width, height = page.get_size()
        context.set_source_rgb(1, 1, 1)
        context.rectangle(0, 0, width, height)
        context.fill()
        page.render(context)

    def update_pdf_controls(self):
        count = self.pdf.get_n_pages()
        self.pdf_status.set_text(f"Page {self.pdf_page + 1} / {count} · PgUp/PgDn")
        self.pdf_previous.set_sensitive(self.pdf_page > 0)
        self.pdf_next.set_sensitive(self.pdf_page + 1 < count)

    def change_pdf_page(self, direction):
        if self.pdf is None:
            return
        page = self.pdf_page + direction
        if 0 <= page < self.pdf.get_n_pages():
            self.pdf_page = page
            self.pdf_area.view.width, self.pdf_area.view.height = self.pdf.get_page(page).get_size()
            self.pdf_area.reset()
            self.update_pdf_controls()
            self.pdf_area.queue_draw()

    def change_file(self, direction):
        if self.navigate is None:
            return
        try:
            path = self.navigate(direction)
            if path is not None:
                self.load_path(path)
        except (OSError, RuntimeError, GLib.Error) as exc:
            self.header.set_subtitle(f"Cannot switch file: {exc}")

    def on_key(self, _widget, event):
        if event.keyval in (Gdk.KEY_space, Gdk.KEY_Escape):
            self.destroy()
            return True
        if event.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK
                          | Gdk.ModifierType.SUPER_MASK | Gdk.ModifierType.SHIFT_MASK):
            return False
        if event.keyval in (Gdk.KEY_Right, Gdk.KEY_Down):
            self.change_file(1)
            return True
        if event.keyval in (Gdk.KEY_Left, Gdk.KEY_Up):
            self.change_file(-1)
            return True
        if self.pdf is not None and event.keyval in (Gdk.KEY_Page_Down, Gdk.KEY_Page_Up):
            self.change_pdf_page(1 if event.keyval == Gdk.KEY_Page_Down else -1)
            return True
        return False

    def check_enabled(self):
        from input_pilot_dolphin_preview import PAUSE_FILE, SETTINGS_FILE, SETTING, read_json

        if self.closed:
            return False
        if PAUSE_FILE.exists() or read_json(SETTINGS_FILE).get(SETTING) is not True:
            self.destroy()
            return False
        return True

    def stop_media(self):
        if self.timeline_timer is not None:
            GLib.source_remove(self.timeline_timer)
            self.timeline_timer = None
        if self.video_bus is not None:
            if self.video_handler is not None:
                self.video_bus.disconnect(self.video_handler)
            self.video_bus.remove_signal_watch()
            self.video_bus = None
            self.video_handler = None
        if self.player is not None:
            self.player.set_state(self.gst.State.NULL)
            self.player = None

    def on_destroy(self, _widget):
        self.closed = True
        self.stop_media()
        Gtk.main_quit()


def show_preview(path: Path, navigate=None):
    GLib.set_prgname("input-pilot-preview")
    GLib.set_application_name("Input Pilot Preview")
    if not path.exists():
        return
    PreviewWindow(path, navigate=navigate)
    Gtk.main()
