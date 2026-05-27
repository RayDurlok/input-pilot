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

## Tray

Start the tray helper:

```bash
./wayland-automation-tray.py --ydotool-socket /tmp/ydotool_socket
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
