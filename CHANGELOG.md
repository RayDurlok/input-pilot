# Changelog

## Unreleased

### Optional Dolphin Quick Look

- Faster startup by reducing copy-shortcut delays and redundant accessibility
  scans. Clipboard results are validated after reading to reject selection or
  focus changes during publication.
- Preload the preview runtime on Space key-down and open only on confirmed
  release. Cancel on other keys or focus changes; remove the fixed startup sleep.
- Added the persistent, default-off **Quick Look with Space (Dolphin)** tray
  toggle. Space previews one selected local image or video; Space/Escape closes
  the preview. Videos include playback and seeking controls; folders and other
  file types show basic information.
- Ignores multiple selections, text input, modifier combinations, and ambiguous
  views. Respects global pause and checks the active window again before acting.
- Reads Dolphin's live window title so previews keep working after folder or
  tab navigation without having to switch away from Dolphin and back.
- Right/Down and Left/Up browse the next/previous files in Dolphin's displayed
  order, preserving the original selection. Switching files stops old playback.
- Added PDF rendering with page buttons and Page Up/Page Down navigation.
- Images and PDFs support pointer-centered scroll-wheel zoom, dragging to pan,
  and double-click or Fit to reset. Images retain their original resolution.
- Waits for a fresh Wayland clipboard offer, preventing old copied file paths
  from being mistaken for the selected file or the navigation list.

### One-command self-update

- **`input-pilot-update`**: a new launcher (and `update.sh`) updates Input Pilot
  to the latest release in place — it downloads the release tarball, installs it
  over the current copy, and restarts the tray. It refuses to run on a git
  checkout unless `--force`, so a developer install is never clobbered.

### Text replacement — word-boundary triggers

- **Triggers only fire as standalone tokens**: a trigger such as `ig` no longer
  fires at the end of a longer word like `fertig`. The match now requires a word
  boundary before the trigger, not just a trailing space.

### Settings window

- **New `Settings…` tray entry** with a small dialog, designed to grow as more
  options are added.
- **Configurable suspend / master key**: the global suspend key (default `F12`)
  can now be rebound from Settings using the same key recorder as the other
  shortcut fields. Useful when an app such as DaVinci Resolve grabs `F12`. The
  KDE global shortcut is re-registered immediately and the tray menu label
  updates to the chosen key.

### Global pause / suspend

- **The suspend key is now a pause toggle**: besides aborting a running template
  click or automation and releasing held mouse buttons, the suspend key (default
  `F12`) now toggles a global suspend for the whole tool. While suspended, hotkey
  path/link targets, text replacements, input automations, and the Dolphin
  folder-template helper all stop responding. Press it again to resume — it works
  as a master key independent of the suspended state.
- **Shared state file**: the suspend state lives in
  `~/.local/state/wayland-automation/paused`. The F12 shortcut and the tray menu
  both toggle it through `abort-click-template.sh`, and every entry-point script
  checks it before acting, so the state is a single source of truth.
- **Tray menu toggle**: a `Pause / suspend` check item in the tray menu mirrors
  the F12 state (label flips to `Resume`).
- **Crossed-out tray icon**: the tray keeps its keyboard icon for the active
  state and renders a dimmed, red-struck copy of it for the suspended state
  (drawn at startup into `~/.local/state/wayland-automation/icons`). The
  indicator also switches to the attention state so KDE keeps it visible while
  suspended. Falls back to a themed pause icon if rendering is unavailable.

### Clipboard preservation — copied files survive paste

- **MIME-type-aware save/restore**: the clipboard is now saved and restored with
  its real MIME type around every clipboard-based paste — the context-aware
  hotkey file-dialog path injection, Text Replacement, the Input automation paste
  node, and the Dolphin folder-template helper. Previously the clipboard was read
  and rewritten as plain text, so a copied file — which lives in `text/uri-list`
  plus the KDE cut/copy marker — collapsed to plain text and could no longer be
  pasted in the file manager afterwards.
- **Richest type kept**: the save step lists the offered types via
  `wl-paste --list-types` and keeps the most meaningful one (`text/uri-list`,
  then images, then any other payload, then text), restoring it with
  `wl-copy --type <mime>`. wl-copy re-adds the text aliases automatically, so
  copied files survive the round-trip while plain text restores byte-exact. A
  cut (move) file is restored as a copy, which is the safe outcome.

### File-dialog detection

- **`blob` caption marker**: windows whose caption or class contains `blob` are
  now recognised as file dialogs, so the context-aware hotkey path-paste also
  fires for them.

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
