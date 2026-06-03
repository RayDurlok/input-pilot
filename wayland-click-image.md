# Wayland Button Automation

This is a KDE Wayland friendly replacement for the common X11
`screenshot -> find image -> click` workflow.

## Install once

Run this in a normal terminal so `sudo` can ask for your password:

```bash
sudo dnf install -y ydotool python3-opencv
```

Start the `ydotool` daemon before using the click script:

```bash
sudo ydotoold
```

Keep that terminal open while testing. Later you can turn it into a service if
you use it often.

## Create a button template

Use Spectacle to screenshot only the button you want to click, then save the
small image somewhere stable, for example:

```bash
mkdir -p "$HOME/Pictures/button-templates"
```

Example target:

```text
$HOME/Pictures/button-templates/resolve-render.png
```

Small, tight crops work best. Avoid including animated parts or changing text.

## Test without clicking

```bash
python3 scripts/wayland-click-image.py \
  "$HOME/Pictures/button-templates/resolve-render.png" \
  --dry-run \
  --debug-image /tmp/wayland-click-debug.png
```

If the match is good, run it for real:

```bash
python3 scripts/wayland-click-image.py \
  "$HOME/Pictures/button-templates/resolve-render.png"
```

If it does not find the button, try a lower threshold:

```bash
python3 scripts/wayland-click-image.py \
  "$HOME/Pictures/button-templates/resolve-render.png" \
  --threshold 0.75
```

## Bind to F1 in KDE

Open:

```text
System Settings -> Keyboard -> Shortcuts -> Add Command
```

Command example:

```bash
./wayland-click-image.py ~/Pictures/button-templates/resolve-render.png
```

Then assign `F1` or a safer combo like `Meta+F1`.
