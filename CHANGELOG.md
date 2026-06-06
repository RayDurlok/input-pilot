# Changelog

## Unreleased

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
