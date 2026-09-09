# Safe photo updates implementation plan

> Execute in this session with TDD and review checkpoints.

**Goal:** Preserve saved product photos and their database order after copy, rename,
SQL failures or an interrupted save; reject managed media as new originals.

**Approved design:** Prepare complete copies, retain the previous folder, update
files and SQLite, and remove the backup only after success. Restore on failure;
recover interrupted operations when opening the database. Preserve external
originals and the current UI. Product-code allocation is outside this change.

**Architecture:** A focused photo_storage service owns staging, a durable JSON
journal, directory swaps and idempotent recovery. SQLite records an operation ID
in the same transaction as the photo links. BEGIN IMMEDIATE serializes saves and
recovery; journal directories are scoped to the resolved database path. A missing
commit marker means restore the previous folder; a marker means keep new photos.

**Constraints:** Windows, Python >=3.11, existing dependencies only. All validation
uses temporary SQLite databases and synthetic files. Do not open production data.
No general backups, product-code changes, redesign, automatic push or merge.

## 1. Regression tests
- [x] Add tests/test_photo_safety.py: assert unchanged file bytes and photo rows
  after a partial copy, failed rename, SQL trigger failure and failed commit.
- [x] Interrupt before/after directory renames and SQL commit; reopen Database
  twice and assert the correct old/new files and order survive.
- [x] Verify rejection of media sources through registration, scanning and
  creation; preserve missing-original fallback for existing managed copies.
- [x] Run `.venv/Scripts/python.exe -m pytest tests/test_photo_safety.py` and
  confirm the missing safeguards fail before implementation.

## 2. Recoverable replacement
- [x] Create app/services/photo_storage.py. Journal contains version, code,
  whether an old folder existed and expected new filenames/hashes. Paths used for
  deletion are derived locally, validated inside media and reject linked folders.
- [x] Add photo_file_commits(operation_id TEXT PRIMARY KEY) to the additive schema.
  Integrate recover(con) at startup and before save under BEGIN IMMEDIATE.
- [x] In sync_product_photos validate IDs, prepare copies, publish the journal,
  rename old to backup, stage to final, update links and insert the marker in one
  SQL transaction. On exception roll back then recover; retain evidence if recovery
  fails. On successful commit cleanup must never roll back committed photos.
- [x] Keep cleanup retryable; refuse ambiguous/corrupt journals without deleting
  backups. Serialize product deletion with recovery so pending backups cannot
  resurrect a deleted product.

## 3. Source protection and completion
- [x] Reject new paths resolving beneath MEDIA_DIR. Skip managed descendants when
  scanning an external parent; explain direct selection of media in Spanish.
- [x] Update scan UI to show that validation error. Existing photo links may use
  their own saved copies when external originals are absent.
- [x] Run targeted tests, then `python -m compileall app` and all pytest tests.
- [x] Review failure windows, repeated recovery, path boundaries and compatibility.
- [x] Update README and CHANGELOG with behavior and operational limits.


## Execution results
- Initial regression run: 8 failures and 1 existing passing safeguard; failures
  reproduced lost/mismatched files, absent recovery and missing source validation.
- Implemented a focused filesystem journal service, additive SQLite commit table,
  recovery under a database write lock and source validation.
- Added actual subprocess exits during copy, directory swaps and immediately
  before/after SQL commit; repeated recovery and blocked cleanup are covered.
- Independent read-only review found no important issues in the recovery design.
- Added a headless Qt startup-message test (failed before handling was added,
  then passed) so blocked recovery explains why startup cannot continue.
- No production database or media was opened, moved or modified during development.
