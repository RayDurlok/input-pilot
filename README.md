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
