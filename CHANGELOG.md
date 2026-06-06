# Changelog

## Unreleased

### Hotkeys dialog — editable shortcut list

- **Replaced fixed F1–F11 grid** with a scrollable list of rows; each row has
  its own Modifier dropdown (same options as before: `—`, Alt, Ctrl, Meta,
  Shift, Ctrl+Alt, …) plus a Key dropdown covering F1–F12, A–Z, 0–9, and
  navigation keys.
- **Add / Remove**: `Add` appends a new empty row; `Remove` (trash icon per
  row) asks for confirmation before deleting.
- **Duplicate detection**: clicking Save checks for duplicate shortcuts and
  shows a warning listing them — saving is blocked until duplicates are
  resolved.
- **Known regression**: the new dialog causes the tray icon to disappear from
  the KDE system tray ~10–15 s after startup. Root cause not yet identified;
  the old fixed-grid dialog does not trigger this. Tracked for a follow-up fix.

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
- **`--name` CLI flag**: `input-pilot-mouse-sequence.py` now accepts
  `--name <automation-name>` (case-insensitive) as an alternative to `--index`.
  The two flags are mutually exclusive; omitting both defaults to index 1.
- **Copy trigger command**: a `Copy trigger command` button in the Trigger row
  copies the ready-to-run command (`input-pilot-mouse-sequence.py --name "…"`)
  to the clipboard.
- **Desktop registration rename**: KDE GlobalAccel entries are now labelled
  `Run Input Pilot automation <name>` instead of
  `Run Input Pilot mousemove sequence <name>`.

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
