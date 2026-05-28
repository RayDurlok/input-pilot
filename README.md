# Wayland Automation

Small KDE Wayland automation helpers for global shortcuts, tray actions, and
screen-template clicking.

## Shortcuts

Install or refresh the configured shortcuts:

```bash
./install-f1-downloads-shortcut.sh
./install-alt-f7-nextcloud-shortcut.sh
```

Current mappings:

- `F1` / `Help`: open `/home/jakob/Downloads/`
- `Alt+F7`: open `https://nextcloud.jackandjake.at/apps/files/files`

The tray menu contains a configuration assistant where `F1` through `F11` can
be mapped to either local paths or links. It also supports modifier variants
such as `Alt+F7`, `Ctrl+F4`, `Meta+F2`, or `Shift+F9`.

Configured shortcuts are active while the tray helper is running. Choosing
`Beenden` in the tray menu unregisters them so the function keys return to
their normal application behavior.

When a plain function key target is a local folder, the tray also registers a
file-dialog helper shortcut. For example, if `F1` points to `/home/jakob/Downloads/`,
`Shift+F1` can be used inside common Save/Open dialogs to jump to that folder.
It works by focusing the dialog location field, pasting the folder path, and
pressing Enter. This helper needs `ydotoold` on `/tmp/ydotool_socket` and the
Wayland clipboard tools `wl-copy` / `wl-paste`.

## Tray

Start the tray helper:

```bash
./wayland-automation-tray.py --ydotool-socket /tmp/ydotool_socket
```

Install the tray autostart entry:

```bash
./install-tray-autostart.sh
```

## ydotool

Start an accessible `ydotoold` service for Wayland mouse/keyboard automation:

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
