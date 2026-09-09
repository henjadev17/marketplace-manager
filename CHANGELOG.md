# Changelog

## Unreleased

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
