# Input Pilot

Small KDE Wayland automation helpers for global shortcuts, tray actions, and
screen-template clicking.

## Install

Input Pilot is currently built for Fedora KDE on Wayland. Clone the repository
and run:

```bash
./install.sh
```

The installer checks required commands and Python modules, installs the
`input-pilot` launcher into `~/.local/bin`, and refreshes the desktop and
autostart entries. If Fedora packages are missing, the installer prints the
missing commands/modules and asks whether it should install the typical package
set with `sudo dnf install`.

On non-Fedora distributions, `./install.sh` still checks the required commands
and Python modules, but it does not try to install packages automatically.
Install equivalent packages for your distribution, then rerun the installer.
Input Pilot expects KDE Wayland, GTK 3 Python bindings, AppIndicator GTK 3,
`ydotool`, `wl-clipboard`, Python OpenCV/NumPy/evdev, KScreen tools, and KDE
tools such as `kreadconfig6` and `kbuildsycoca6`.

Text Replacement reads keyboard events from `/dev/input`. Add your user to the
`input` group once, then log out and back in so the new group is active:

```bash
sudo usermod -aG input "$USER"
```

Verify after logging in again:

```bash
groups
```

The output should include `input`.

Input automation needs an accessible `ydotoold` socket. Configure the
persistent service once:

```bash
./install-ydotool-service.sh
```

After installation, start Input Pilot with:

```bash
input-pilot
```

Remove the launcher and desktop entries with:

```bash
./uninstall.sh
```

## Shortcuts

The tray menu contains a `Hotkeys...` editor where shortcuts can be mapped to
local paths or links. Shortcuts can be typed manually or captured with the
`Record` button. Multi-modifier shortcuts such as `Ctrl+Alt+Shift+2` are
supported, along with function keys, letters, numbers, and common navigation
keys. Saving checks for duplicate shortcuts before applying the new mapping.

Configured shortcuts are active while the tray helper is running. Choosing
`Beenden` in the tray menu unregisters them so the function keys return to
their normal application behavior.

When a plain function key target is a local folder, the normal key becomes
context-aware while the tray is running: it opens the folder normally, but if
KWin reports that a common Save/Open dialog is focused, the shortcut pastes the
folder path into that dialog and opens it there. The corresponding
`Shift+<function key>` shortcut remains available as an explicit file-dialog
helper. This helper needs `ydotoold` on `/tmp/ydotool_socket` and the Wayland
clipboard tools `wl-copy` / `wl-paste`.

## Tray

Start the tray helper:

```bash
./wayland-automation-tray.py --ydotool-socket /tmp/ydotool_socket
```

Install the tray autostart entry:

```bash
./install-tray-autostart.sh
```

The installer runs this automatically.

The tray warms a small local template server so OpenCV stays loaded between
template clicks. Template matching uses KWin's `ScreenShot2` API when
available; repeated clicks on the same template first verify the last known
position with a small cached-area screenshot before falling back to a full
search. This keeps repeated screenshot actions fast without blindly clicking
stale coordinates.
`F12` is registered as an emergency stop while the tray is running; it aborts
running template clicks and input automations, and releases mouse buttons if
needed.

## Input Automations

The tray menu contains an `Input Automations...` editor for named input
automations. The editor has a collapsible sidebar listing all automations;
click an entry to switch, drag the `⠿` handle to reorder. The sidebar toolbar
provides buttons to add, remove (with confirmation), and duplicate the selected
automation. Each automation can have its own trigger hotkey. Hotkeys support
modifiers plus function keys, letters, numbers, and common navigation keys.

Each node has an action (`Click`, `Drag`, `Move mouse`, `Input`, or `If`) plus
the source/target fields needed for that action. Sources and targets can be
screenshot templates, fixed X/Y coordinates, or the previous mouse position
captured when the automation started. Input nodes can send key combos such as
`Ctrl+S` or type text strings. Click nodes can optionally enable the mouse-icon
toggle to animate the pointer to the target before clicking. Screenshot targets
can choose which near-best match to use (`Best`, `Rightmost`, `Middle`,
`Leftmost`, `Topmost`, `Bottommost`) when identical UI elements appear more
than once on screen. During a chain the pointer can continue from step to step;
after the automation finishes, it returns to the original position. Nodes can be
reordered by dragging the `⠿` handle on the left side of each row; row numbers
update automatically. Clicking a row number opens a note popover — notes are
stored with the automation and shown as a tooltip on rows that have one.

`If` nodes act like block-coding containers. Conditions such as `Previous node
failed`, `Previous node succeeded`, and `Always` control whether the indented
child nodes below the `If` row run. Drag-and-drop is block-aware: moving an
`If` row moves its children with it, and dropping nodes into a block applies the
correct indentation. After an `If` block runs, the default continuation is
`Next node`; it can optionally jump to another step, which is useful for
recovery loops such as returning to step 1 after opening a missing panel. A run
stops automatically when it reaches 3 jumps.

Each automation can be triggered from the command line. The `Copy trigger
command` button in the Trigger row copies the ready-to-use command:

```bash
input-pilot-mouse-sequence.py --id auto-123456789abc
```

Automation IDs are generated automatically and stay stable when an automation is
renamed or reordered. The runner also accepts `--name <name>` and
`--index <n>` for backwards compatibility. `--id`, `--name`, and `--index` are
mutually exclusive; omitting all three defaults to index 1.

Automations are stored in:

```text
~/.config/wayland-automation/mousemove-sequence.json
```

Use `Move mouse` for hover-style pointer movement without clicking. For `Drag`,
the source field is where the mouse button is pressed and the target field is
where it is released. Drag nodes also expose `Steps`, which controls how many
interpolated mouse movements are used between source and target. Enabling
`Debug` on an automation shows desktop notifications for helpful failures such
as missing source or target screenshots.

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

Typing `ct.` followed by space replaces it with `ChatGPT`. On Wayland this
requires low-level read access to keyboard events in `/dev/input`, usually by
being a member of the `input` group.

Replacement text is inserted via clipboard paste (`wl-copy` + `Ctrl+V`) so all
Unicode characters and special symbols work correctly regardless of the active
keyboard layout. The original clipboard content is restored after each
injection.

Use `{enter}` anywhere in a replacement string to send Shift+Enter at that
position (useful for line breaks in chat applications).

Date format replacements use `dd`, `mm`, `yy`, and `yyyy` tokens:

```json
[
  { "trigger": "dt.", "date_format": "dd.mm.yyyy", "enabled": true },
  { "trigger": "dt_", "date_format": "yyyy_mm_dd", "enabled": true },
  { "trigger": "rnr.", "date_format": "yyyymmdd",  "enabled": true }
]
```

These entries are editable in the `Textreplacement...` dialog. Any replacement
value that consists only of `dd`/`mm`/`yy`/`yyyy` tokens and separator
characters (`.` `-` `_` `/`) is automatically stored as a date format.

Internally, `dt-` and `dt/` are accepted as aliases for `dt_` to handle
keyboard layouts that report the underscore key as shifted punctuation.
