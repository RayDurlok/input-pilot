# Input Pilot

Small KDE Wayland automation helpers for global shortcuts, tray actions, and
screen-template clicking.

## Shortcuts

Install or refresh the configured shortcuts:

```bash
./install-f1-downloads-shortcut.sh
./install-alt-f7-nextcloud-shortcut.sh
```

Current mappings:

- `F1` / `Help`: open `~/Downloads/`
- `Alt+F7`: open the configured browser link

The tray menu contains a configuration assistant where `F1` through `F11` can
be mapped to either local paths or links. It also supports modifier variants
such as `Alt+F7`, `Ctrl+F4`, `Meta+F2`, or `Shift+F9`.

Configured shortcuts are active while the tray helper is running. Choosing
`Beenden` in the tray menu unregisters them so the function keys return to
their normal application behavior.

When a plain function key target is a local folder, the normal key becomes
context-aware while the tray is running: `F1` opens `~/Downloads/`
normally, but if KWin reports that a common Save/Open dialog is focused, `F1`
pastes the folder path into that dialog and opens it there. `Shift+F1` remains
available as an explicit file-dialog helper. This helper needs `ydotoold` on
`/tmp/ydotool_socket` and the Wayland clipboard tools `wl-copy` / `wl-paste`.

## Tray

Start the tray helper:

```bash
./wayland-automation-tray.py --ydotool-socket /tmp/ydotool_socket
```

Install the tray autostart entry:

```bash
./install-tray-autostart.sh
```

The `Button-Template klicken` tray action searches the current screen for
`~/Desktop/buttonscreen.png` and double left-clicks the match center.
The tray warms a small local template server so OpenCV stays loaded between
clicks; this reduces the delay before the mouse starts moving.
For normal clicks, KWin reports the real cursor position once, then ydotool
moves relatively to the detected target and clicks immediately.
`F12` is registered as an emergency stop while the tray is running; it aborts a
running template click and releases mouse buttons if needed.

## Input Automations

The tray menu contains an `Input Automations...` editor for named input
automations. The editor has a collapsible sidebar listing all automations;
click an entry to switch, drag the `⠿` handle to reorder. The sidebar toolbar
provides buttons to add, remove (with confirmation), and duplicate the selected
automation. Each automation can have its own trigger hotkey. Hotkeys support
modifiers plus function keys, letters, numbers, and common navigation keys.

Each node has an action (`Click`, `Drag`, `Move mouse`, or `Input`) plus the
source/target fields needed for that action. Sources and targets can be
screenshot templates, fixed X/Y coordinates, or the previous mouse position
captured when the automation started. Input nodes can send key combos such as
`Ctrl+S` or type text strings. During a chain the pointer can continue from
step to step; after the automation finishes, it returns to the original
position. Nodes can be reordered by dragging the `⠿` handle on the left side
of each row; row numbers update automatically.

Automations are stored in:

```text
~/.config/wayland-automation/mousemove-sequence.json
```

For `Hover`, the wait time is used as the hover duration before the next node.
For `Drag`, the source field is where the mouse button is pressed and the
target field is where it is released. Drag nodes also expose `Steps`, which
controls how many interpolated mouse movements are used between source and
target. Enabling `Debug` on an automation shows desktop notifications for
helpful failures such as missing source or target screenshots.

## Folder Templates

The tray menu contains a `Folder Templates...` editor. Each entry has a name,
a trigger hotkey, and a template folder path. When the hotkey is pressed while
Dolphin is active, Input Pilot copies that template folder into the current
Dolphin directory and asks for the new folder name.

The default user configuration maps `Ctrl+N` to the first folder template.
Folder templates are stored in:

```text
~/.config/wayland-automation/folder-templates.json
```

## ydotool

Install and enable a persistent `ydotoold` service for Wayland mouse/keyboard
automation:

```bash
./install-ydotool-service.sh
```

Start an accessible transient `ydotoold` service manually:

```bash
./start-ydotool-automation-service.sh
```

## Key Detector

Open a small focused window that logs key presses:

```bash
./detect-key.py
```

Logs are written below:

```text
~/.local/state/wayland-automation/
```

## Text Replacement

The tray menu contains a `Textreplacement...` editor. Entries are stored as an
array in:

```text
~/.config/wayland-automation/text-replacements.json
```

Example:

```json
[
  {
    "trigger": "ct.",
    "replacement": "ChatGPT",
    "enabled": true
  }
]
```

Typing `ct.` followed by space replaces it with `ChatGPT `. On Wayland this
requires low-level read access to keyboard events in `/dev/input`.

Built-in dynamic replacements:

- `dt.` + space: current date as `dd.mm.yyyy`
- `dt_` + space: current date as `yyyy_mm_dd`
- `rnr.` + space: current date as `yyyymmdd`

Internally, `dt-` and `dt/` are accepted as aliases for `dt_` to handle
keyboard layouts that report the underscore key as shifted punctuation.
