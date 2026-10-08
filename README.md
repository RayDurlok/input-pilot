# Input Pilot

A small KDE Wayland tray app for desktop automation.

It maps global hotkeys to folders and links, runs visual click/drag/move
automations from screen templates, expands text snippets as you type, and drops
folder templates into Dolphin — all driven from a single tray icon.

## Requirements

- KDE Plasma on Wayland
- Python 3
- `ydotool` + `ydotoold`
- `wl-clipboard` (`wl-copy` / `wl-paste`)
- GTK 3 Python bindings + AppIndicator GTK 3
- Python OpenCV, NumPy, evdev
- KDE tools: `kreadconfig6`, `kbuildsycoca6`, `kscreen-doctor`

Tested on Fedora KDE. On Fedora the installer offers to pull the packages above
automatically; on other distributions install the equivalents first.

## Support

If you want to support my work:

[![Donate with PayPal](https://img.shields.io/badge/Donate-PayPal-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://www.paypal.com/donate/?hosted_button_id=V4HH8D9L36UPG)

## Quick Start

Install the latest release:

```bash
curl -L https://github.com/RayDurlok/input-pilot/releases/latest/download/input-pilot-linux.tar.gz -o input-pilot-linux.tar.gz
tar xzf input-pilot-linux.tar.gz
cd input-pilot
./install.sh
```

The installer checks dependencies, installs the `input-pilot` launcher into
`~/.local/bin`, and registers the autostart entry. Then start the tray:

```bash
input-pilot
```

Remove everything again with `./uninstall.sh`.

### Update

Update to the latest release with a single command:

```bash
input-pilot-update
```

It downloads the newest release, installs it over the current one, and restarts
the tray automatically. Your configuration is kept.

<details>
<summary>Manual update (without the launcher)</summary>

```bash
curl -L https://github.com/RayDurlok/input-pilot/releases/latest/download/input-pilot-linux.tar.gz -o input-pilot-linux.tar.gz
tar xzf input-pilot-linux.tar.gz
cd input-pilot
./update.sh
```

</details>

### One-time setup

Text Replacement reads keyboard events from `/dev/input`. Add yourself to the
`input` group once, then log out and back in:

```bash
sudo usermod -aG input "$USER"
```

Mouse/keyboard automation needs an accessible `ydotoold` socket. Configure the
persistent service once:

```bash
./install-ydotool-service.sh
```

`F12` is a global emergency stop and pause toggle while the tray runs. The first
press aborts any running template click or automation, releases held mouse
buttons, and **suspends the whole tool** — hotkeys, text replacement, input
automations, and folder templates all stop responding and the tray icon gets a
red strike. The suspend key is a master key: it always toggles suspend on and
off, independent of the suspended state. Press it again, or toggle `Pause /
suspend` in the tray menu, to resume.

The key defaults to `F12` and is configurable in **Settings…** — pick another
shortcut if `F12` clashes with an app (for example DaVinci Resolve grabbing it).


## Tray

Everything is configured from the tray menu:

- **Hotkeys…** — global shortcuts to folders and links
- **Input Automations…** — visual click/drag/move/type sequences
- **Folder Templates…** — drop template folders into Dolphin
- **Textreplacement…** — type-as-you-go text snippets
- **Settings…** — configure the suspend / master key (more options later)
- **Quick Look with Space (Dolphin)** — optional single-item preview (off by default)
- **Pause / suspend** — freeze every feature at once (same as the suspend key);
  the tray icon gets a red strike while suspended

While the tool is suspended the tray keyboard icon switches to a dimmed, red-
struck variant so you can see at a glance that nothing will fire.

The tray warms a small local template server so OpenCV stays loaded between
clicks. Template matching uses KWin's `ScreenShot2` API and verifies the last
known position with a small cached screenshot before falling back to a full
search, keeping repeated actions fast.

## Dolphin Quick Look

Enable **Quick Look with Space (Dolphin)** in the tray's right-click menu.
Select one image, video, audio file (including WAV and MP3), or PDF in Dolphin, then press and release Space to
preview it. Right/Down shows the next file, Left/Up the previous file, using a
snapshot of Dolphin's displayed order. The original Dolphin selection is kept.
Quick Look prepares its runtime while Space is held, then validates the selection
and opens on release. Another key or a focus change cancels the preparation.
Space or Escape closes the preview; audio and video have Play/Pause, a seek bar,
and elapsed/total time. Audio starts automatically and uses a dedicated audio
view without requiring the GTK video sink.
PDFs render in the preview window; use Page Up/Page Down or the page buttons to
move between PDF pages. Arrow keys continue to switch files, including for PDFs.
Use the scroll wheel over an image or PDF to zoom around the pointer. Drag with
the left mouse button to pan; double-click or press **Fit** to reset the view.
Images use their original resolution, and PDFs stay sharp while zooming. Opening
another file or PDF page resets the zoom to fit.
Folders and unsupported file types show basic information. The preference is
saved, and global pause also disables Quick Look and closes its preview.

The feature uses the existing keyboard listener and Qt's AT-SPI accessibility
bridge (enabled when you turn it on). It requires the `Atspi 2.0` Python GI
binding; video playback additionally needs GStreamer `playbin`, `gtksink`, and
codecs for the selected format. On Fedora these are provided by `at-spi2-core`,
`gstreamer1-plugins-base`, and `gstreamer1-plugins-good-gtk`, plus the relevant
codec packages. PDF preview requires the Poppler GI binding (`poppler-glib` on
Fedora). Image and PDF rendering require Python Cairo. Missing media support
produces a message in the preview.

Only local files and an unambiguous active Dolphin file view are supported.
No preview opens for zero/multiple selections, an active text field or menu,
or a split view where the active pane cannot be identified safely. Modified
Space shortcuts are ignored. Dolphin's native selection-mode shortcut still
receives Space; Quick Look leaves that mode when it previews an item. To avoid
the selection-mode flash, change Dolphin’s **Select Files and Folders** shortcut
from Space to Shift+Space in Dolphin’s shortcut settings. This is a separate
Dolphin preference; Input Pilot does not change it automatically. The
selected file URL and the navigation list are read through Dolphin's Copy
shortcut while Dolphin has focus, with clipboard save/restore protection.
Window painting is suspended while the navigation list is read, so the
temporary all-selection is not displayed. The original selection and painting
state are restored before the preview opens. Nothing is launched in the file's default app.

## Hotkeys

![Hotkeys editor](docs/hotkeys.png)

Map global shortcuts to a local path or a link. Each row has its own modifier
and key dropdown; `Add` / `Remove` manage the list and saving rejects duplicate
shortcuts. Supports modifiers (`Ctrl+Alt+Shift+2`), function keys, letters,
numbers, and navigation keys.

When a function-key target is a local folder, the key becomes context-aware: it
opens the folder normally, but if a Save/Open dialog is focused it pastes the
folder path into the dialog instead. `Shift+<key>` stays available as an
explicit file-dialog helper. The path is injected through the clipboard, so your
previous clipboard — including a copied file — is saved and restored with its
original MIME type.

## Input Automations

![Input Automations editor](docs/input-automations.png)

Build named automations from a list of nodes. The collapsible sidebar lists all
automations — click to switch, drag the `⠿` handle to reorder, and use the
toolbar to add, duplicate, or remove (with confirmation). Each automation can
have its own trigger hotkey.

Each node has an action and the fields it needs:

| Action | What it does |
| --- | --- |
| `Click` | Click a screenshot template, fixed X/Y, or the start position |
| `Drag` | Press at the source, release at the target (with interpolated `Steps`) |
| `Move mouse` | Hover to a target without clicking (smooth move optional) |
| `Input` | Send a key combo (`Ctrl+S`), paste text, or type text key-by-key |
| `If` | Block container that runs its indented children conditionally |

Targets can be **screenshot templates**, **fixed coordinates**, or the
**previous mouse position** captured when the run started. When a template
matches in several places, pick which one to use (`Best`, `Rightmost`,
`Middle`, `Leftmost`, `Topmost`, `Bottommost`). Click and Move nodes can enable
the mouse-pointer toggle to animate the cursor instead of jumping.

`If` nodes work like block coding. Conditions (`Previous node failed`,
`Previous node succeeded`, `Always`) decide whether the indented children run.
Drag-and-drop is block-aware — moving an `If` row carries its children. After a
block finishes it continues with the **Next node** by default, or jumps to a
chosen **Step** (useful for recovery loops, e.g. back to step 1 after reopening
a missing panel). A run stops automatically after 3 jumps.

Nodes reorder by dragging the `⠿` handle; clicking a row number opens a note
popover, shown as a tooltip on rows that have one.

Trigger an automation from the command line — the `Copy trigger command` button
copies the ready-to-run command:

```bash
input-pilot-mouse-sequence.py --id auto-123456789abc
```

IDs are stable across renames and reordering. `--name <name>` and `--index <n>`
also work; omitting all three defaults to index 1. Automations are stored in
`~/.config/wayland-automation/mousemove-sequence.json`.

## Text Replacement

![Text replacement editor](docs/text-replacement.png)

Type a trigger followed by space and it is replaced inline. Entries live in
`~/.config/wayland-automation/text-replacements.json`:

```json
[
  { "trigger": "hl.", "replacement": "Hello!", "enabled": true }
]
```

Replacements are inserted via clipboard paste (`wl-copy` + `Ctrl+V`), so every
Unicode character and special symbol works regardless of keyboard layout. The
original clipboard is restored afterwards with its MIME type preserved, so a
copied file (`text/uri-list`) stays pasteable rather than collapsing to plain
text. Use `{enter}` anywhere in a replacement to insert a Shift+Enter line
break.

Date snippets use `dd`, `mm`, `yy`, and `yyyy` tokens:

```json
[
  { "trigger": "dt.",  "date_format": "dd.mm.yyyy", "enabled": true },
  { "trigger": "dt_",  "date_format": "yyyy_mm_dd", "enabled": true },
  { "trigger": "rnr.", "date_format": "yyyymmdd",   "enabled": true }
]
```

All entries are editable in the `Textreplacement…` dialog. Any value made only
of date tokens and separators (`.` `-` `_` `/`) is stored as a date format.

## Folder Templates

![Folder templates editor](docs/folder-templates.png)

Map a hotkey to a template folder. Pressing it while Dolphin is active copies
that folder into the current Dolphin directory and prompts for a name. There are
no templates by default — add your own; `Ctrl+N` is a handy hotkey to assign.
Stored in `~/.config/wayland-automation/folder-templates.json`.

## Extras

Persistent ydotool service:

```bash
./install-ydotool-service.sh        # install + enable
./start-ydotool-automation-service.sh   # transient, run manually
```

Key detector — a focused window that logs key presses to
`~/.local/state/wayland-automation/`:

```bash
./detect-key.py
```

## Repository Layout

```text
wayland-automation-tray.py        Tray app and all configuration dialogs
input-pilot-mouse-sequence.py     Automation runner (CLI + triggers)
input-pilot-template-server.py    Warm OpenCV template-matching server
input-pilot-text-replacement.py   Type-as-you-go replacement engine
input-pilot-folder-template.py    Dolphin folder-template helper
wayland-click-image.py            Screen-template click/drag/move core
install.sh / uninstall.sh         Installer and uninstaller
```

## License

GPLv3.
