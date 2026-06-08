# Input Pilot Tray

This tray helper provides the main Input Pilot menu:

- `Hotkeys...` configures global shortcut mappings to paths or links.
- `Input Automations...` configures screenshot, pointer, keyboard, and
  condition-based automation chains.
- `Folder Templates...` configures folder-copy templates with trigger hotkeys.
- `Textreplacement...` configures typed trigger replacements.
- `Quit` closes the tray helper and unregisters the active shortcuts.

Start it manually:

```bash
./wayland-automation-tray.py --ydotool-socket /tmp/ydotool_socket
```

After running `./install.sh`, the launcher is also available as:

```bash
input-pilot
```

On KDE Wayland, global hotkeys are registered through KDE's own shortcut
system. Input Pilot does not listen for global key presses directly, because
Wayland blocks that for normal applications by design.

For mouse clicking, the helper expects an accessible `ydotoold` socket. The
included helper starts one at `/tmp/ydotool_socket`:

```bash
./start-ydotool-automation-service.sh
```
