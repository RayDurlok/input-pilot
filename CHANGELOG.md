# Changelog

## Unreleased

### Project packaging

- **Installer**: added `install.sh` as the main setup entry point. It checks
  runtime commands and Python modules, creates the `input-pilot` launcher in
  `~/.local/bin`, and installs desktop/autostart entries.
- **Dependency prompt**: when required Fedora dependencies are missing,
  `install.sh` now asks whether it should install the typical package set via
  `sudo dnf install`. On non-Fedora systems, it prints the missing requirements
  and asks the user to install equivalent packages manually.
- **Uninstaller**: added `uninstall.sh` to remove the launcher and desktop
  entries while keeping user configuration and logs.
- **README refresh**: installation now documents the tray launcher and
  persistent `ydotoold` setup instead of the older one-off shortcut helpers,
  and documents the `input` group requirement for Text Replacement.
- **Legacy helper cleanup**: removed old one-off F1/Alt+F7 shortcut installer
  scripts now that shortcuts are configured through the tray UI.

### Hotkeys dialog — editable shortcut list

- **Replaced fixed F1–F11 grid** with a scrollable list of rows; each row has
  one editable shortcut field plus a path/link target.
- **Shortcut recorder**: the Hotkeys dialog now uses the same `Record` flow as
  Input Automation key-combo nodes. Shortcuts can also be typed manually.
- **Flexible shortcuts**: multi-modifier combinations such as
  `Ctrl+Alt+Shift+2` are supported, along with function keys, letters, numbers,
  numpad digits, and common navigation keys. German-layout shifted number
  symbols such as `"` are normalized back to their number key for recording.
- **Aligned columns**: header labels now share the same fixed widths as the row
  controls so `Shortcut` and `Path or link` sit over the correct fields.
- **Add / Remove**: `Add` appends a new empty row; `Remove` (trash icon per
  row) asks for confirmation before deleting.
- **Duplicate detection**: clicking Save checks for duplicate shortcuts and
  shows a warning listing them — saving is blocked until duplicates are
  resolved.

### Text Replacement — raw input, date format editor, special characters

- **Clipboard-based paste**: replacement text is now inserted via `wl-copy` +
  `Ctrl+V` instead of `ydotool type`. This correctly handles all special
  characters regardless of keyboard layout (`:`, `/`, `+`, `°`, `^`, URLs, …).
- **Clipboard restore**: the original clipboard content is saved before each
  injection and restored 150 ms after the paste so the user's clipboard is not
  permanently overwritten.
- **`{enter}` token**: typing `{enter}` inside a replacement string sends
  Shift+Enter at that position (e.g. for multi-line text in chat apps).
- **`^` and `°` trigger detection**: `KEY_GRAVE` (physical caret key on German
  keyboards) is now tracked — `^` without Shift and `°` with Shift — so
  triggers like `^^.` or `°°.` are correctly detected in the buffer.
- **Editable date formats**: the previously read-only built-in date entries
  (`dt.`, `dt_`, `rnr.`) are now editable rows in the Textreplacement dialog.
  Any replacement value composed of `dd`, `mm`, `yy`/`yyyy` and separators is
  automatically treated as a date format and stored as `date_format` in JSON.
  Custom tokens supported: `dd` (day), `mm` (month), `yyyy` / `yy` (year).
- **No trailing space**: replacements no longer append an extra space after
  the substituted text.
- **Dialog buttons in one row**: Add / Remove / Cancel / Save are now all on
  a single button bar at the bottom; dialog labels translated to English.

### Input Automations — node cards, notes, CLI trigger

- **Node cards**: each node row now has a subtle background, rounded corners, and
  a thin border (`input-pilot-node-card` CSS class) to give visual weight to
  individual steps.
- **Per-node notes**: the row number is now a clickable button. Clicking it opens
  a small popover with a text area for freeform notes. Rows with a note highlight
  the number in the accent colour and show the note text as a tooltip. Notes are
  persisted with the automation.
- **CLI trigger flags**: `input-pilot-mouse-sequence.py` supports stable
  `--id <automation-id>` triggers plus backwards-compatible `--name` and
  `--index` lookup. Omitting all three defaults to index 1.
- **Copy trigger command**: a `Copy trigger command` button in the Trigger row
  copies the ready-to-run command to the clipboard.
- **Stable automation IDs**: input automations now store an internal `id`.
  Copied trigger commands and KDE shortcut desktop entries use
  `input-pilot-mouse-sequence.py --id ...`, so commands keep working after an
  automation is renamed or reordered. `--name` and `--index` remain supported
  for backwards compatibility.
- **Desktop registration rename**: KDE GlobalAccel entries are now labelled
  `Run Input Pilot automation <name>` instead of
  `Run Input Pilot mousemove sequence <name>`.
- **If blocks**: added `If` nodes with `Previous node failed`,
  `Previous node succeeded`, and `Always` conditions. Child nodes are indented
  below the `If` row, and drag-and-drop keeps block structure intact.
- **Animate mouse**: normal click nodes now expose a compact mouse-icon toggle
  that animates the pointer to the click target before clicking.
- **Smooth move persistence**: `Move mouse` nodes now keep the mouse-icon
  smooth-move toggle after saving and use it for position and previous-position
  targets.
- **Input string paste**: `Input` text nodes now insert text via
  `wl-copy` + `Ctrl+V` and restore the previous clipboard, matching the more
  reliable Text Replacement input path.
- **Typed text fallback**: `Input` nodes also offer `Type string` for apps that
  need the older simulated keypress behavior instead of clipboard paste.
- **Move mouse replaces click-hover**: hover-style behavior now belongs to
  `Move mouse`; legacy `Click` + `Hover` nodes are loaded as move nodes.
- **KWin template cache**: template matching now reads KWin `ScreenShot2` raw
  pixel captures directly and caches verified template positions. Repeated
  clicks first check a small cached area before falling back to a full search.
- **Template match selection**: screenshot target nodes can choose which
  near-best match to use when the same template appears multiple times on
  screen: `Best`, `Rightmost`, `Middle`, `Leftmost`, `Topmost`, or
  `Bottommost`.
- **If jump recovery loops**: `If` nodes default to `Next node` after running
  their child nodes, or can jump to a configured step number. This supports
  recovery flows such as “if the previous screenshot was missing, click setup
  buttons, then restart at step 1”. A loop guard stops the run after 3 jumps.
- **F12 aborts input automations**: the emergency shortcut now stops running
  input automation sequences as well as template-click actions, and releases
  mouse buttons.
- **Faster failed template checks**: when the persistent template server reports
  `Match below threshold`, Input Pilot no longer repeats the same search through
  the slower fallback path.
- **Sequence lock fix**: a second trigger while an automation is already running
  no longer removes the active run's lock file.
- **Screenshot path fields**: source/target screenshot fields now display long
  paths as compact tail paths such as `.../Screenshots/FX/button.png`, keep the
  full path internally, and accept files dropped directly from Dolphin.
- **Window icon**: Input Pilot dialogs now use the local
  `InputPilotIconRounded.png` as their window icon while the tray keeps the
  simpler system keyboard icon.

### Known follow-ups

- Hotkeys dialog: manually typed unknown modifier tokens are currently
  normalized away (`Ctrl+Foo+2` becomes `Ctrl+2`) instead of being reported as
  invalid.
- Hotkeys dialog: rows with a target but an empty shortcut are silently skipped
  on save; this should become an explicit warning.

### Input Automations — UI overhaul

- **Sidebar**: replaced the automation combo-box with a collapsible sidebar
  list. Click to select, drag the `⠿` handle to reorder automations. Collapse
  with `‹` and expand with `›`.
- **Duplicate automation**: new button (copy icon) in the sidebar toolbar
  duplicates the current automation including all its nodes.
- **Confirm on delete**: removing an automation now shows a confirmation dialog
  (matching the existing node-delete dialog). Node-delete dialog text
  translated to English.
- **All UI labels in English**: buttons and labels that were previously in
  German (`Abbrechen`, `Speichern`, `Ausführen`, `Node hinzufügen`, …) are now
  in English throughout the dialog.
- **Drag-and-drop reorder (automations)**: sidebar rows support the same
  grip-handle DnD pattern used for nodes — blue drop indicator, opacity
  feedback on the dragged row, selection follows the moved item.

### Input automations — action model refactor (prior commit)

- Unified drag, move, click, and input nodes under a shared source/target
  position model supporting templates, fixed X/Y coordinates, and
  previous-mouse-position.
- Added `SequenceRunLock` to prevent concurrent automation runs.
- Structured sequence log written to
  `~/.local/state/wayland-automation/mouse-sequence.log`.
- Drag nodes expose a `Steps` field to control interpolated mouse movements.
