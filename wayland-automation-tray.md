# Wayland Automation Tray

This tray helper is intentionally small:

- `Downloads öffnen` opens `/home/jakob/Downloads/`
- `Button-Template klicken` runs `wayland-click-image.py` with the configured
  template image
- `ydotool prüfen` checks whether the ydotool socket is reachable
- `Beenden` closes the tray helper

Start it manually:

```bash
/usr/bin/python3 /home/jakob/Apps/WaylandAutomation/wayland-automation-tray.py
```

Use a custom template:

```bash
/usr/bin/python3 /home/jakob/Apps/WaylandAutomation/wayland-automation-tray.py \
  --template /home/jakob/Pictures/button-templates/my-button.png
```

On KDE Wayland, global hotkeys should still be registered through KDE's own
shortcut system. The tray app does not listen for global key presses directly,
because Wayland blocks that for normal applications by design.

For mouse clicking, the helper expects an accessible `ydotoold` socket. The
included helper starts one at `/tmp/ydotool_socket`:

```bash
/home/jakob/Apps/WaylandAutomation/start-ydotool-automation-service.sh
```
