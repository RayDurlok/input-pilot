# Changelog

## Unreleased

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
