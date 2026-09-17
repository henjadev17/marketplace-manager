# Changelog

## Unreleased

- Make product deletion recoverable with a journaled temporary backup and SQLite commit marker; restore uncommitted deletes and finish committed cleanup after restart.
- Preserve unknown files and newly occupied product paths, and show deletion errors in the product list.

- Make product creation recoverable: verify staged photo copies, install without replacing existing folders, and commit product rows with a recovery marker.
- Recover interrupted creations on restart, preserving committed products and originals; add process-exit and failure-injection regression tests.

- Add one-step startup through Iniciar.cmd (Windows double click) and scripts/start.sh (Git Bash), sharing automatic environment creation and dependency installation when requirements change.

- Add optional internal condition ratings (1–10) and multiline notes to product creation and editing, preserving existing products during migration.
- Exclude internal condition and notes from public descriptions and XLSX exports; allow scrolling the expanded product editor.

- Rotate selected product photos left/right with pending thumbnail and full-size previews; save only managed copies through the recoverable photo journal.
- Preserve saved photo edits when reordering and normalize EXIF orientation when rotating.

- Delete templates and clear their product/settings references atomically, preserving saved product descriptions and protecting the last template.
- Select the default template when editing a product with a legacy missing template reference.

- Reserve product codes with a persistent SQLite counter, preventing reuse after deletion or failed creation and coordinating concurrent creates.
- Skip existing media files and folders without overwriting or removing them.

- Preserve intentionally empty delivery, payment and contact defaults after restart; import legacy values only when initializing missing defaults.

- Protect unsaved template edits with Save/Discard/Cancel when switching templates or leaving the editor; retain drafts after failed saves.
- Preserve template drafts when changing the default template and protect reloads triggered by toolbar actions.

- Preserve previous product photos during reordering and recover interrupted saves on startup using a filesystem journal and SQLite commit marker.
- Reject managed media as new source photos; preserve existing own-copy fallback when originals are unavailable.
- Add isolated failure-injection and abrupt-process-exit regression tests for photo saving and recovery.

- Add an Open photo folder action to the product photo manager for accessing saved images in Windows Explorer.

- Add isolated business regression tests and Windows CI.
- Add PowerShell setup, run, test, and build commands.
- Document architecture, data safety, and contribution workflow.
- Add project metadata and development dependency configuration.

## v0.9.2

- Stable responsive product form.
- Light, dark, and system appearance.
- Templates and default values.
- Product photo management, including copying, renaming, and reordering.
- Publishing/copy grid.
- XLSX export.
