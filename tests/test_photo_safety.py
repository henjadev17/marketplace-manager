"""Failure injection operates only on generated images and temporary databases."""
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import textwrap

import pytest

from app.data.database import Database


def snapshot(db, product_id):
    full = db.get_product(product_id)
    return full, {Path(p['copied_path']).name: Path(p['copied_path']).read_bytes()
                  for p in full['photos']}


def assert_snapshot(db, product_id, expected):
    assert snapshot(db, product_id) == expected


@pytest.fixture
def saved_product(db, product_data, source_photos):
    ids = [photo_id for photo_id, _ in source_photos]
    product_id, _ = db.create_product(product_data, ids)
    return product_id, ids


@pytest.mark.parametrize('failure', ['copy', 'rename', 'sql'])
def test_save_failure_preserves_old_files_and_rows(db, saved_product, source_photos, monkeypatch, failure):
    product_id, ids = saved_product
    before = snapshot(db, product_id)
    originals = {path: path.read_bytes() for _, path in source_photos}
    if failure == 'copy':
        real_copy = shutil.copy2
        def broken_copy(source, destination, *args, **kwargs):
            real_copy(source, destination, *args, **kwargs)
            raise OSError('simulated disk error')
        monkeypatch.setattr(shutil, 'copy2', broken_copy)
    elif failure == 'rename':
        real_rename = Path.rename
        def broken_rename(source, destination):
            if Path(destination).name == 'PROD-0001' and source.name != 'backup':
                raise OSError('simulated locked destination')
            return real_rename(source, destination)
        monkeypatch.setattr(Path, 'rename', broken_rename)
    else:
        with db.connection() as con:
            con.execute("""CREATE TRIGGER fail_photos BEFORE INSERT ON product_photos
                           BEGIN SELECT RAISE(ABORT, 'simulated SQL failure'); END""")
    with pytest.raises((OSError, sqlite3.DatabaseError)):
        db.sync_product_photos(product_id, ids[::-1])
    assert_snapshot(db, product_id, before)
    for path, content in originals.items():
        assert path.read_bytes() == content


class InterruptedSave(BaseException):
    """Bypass ordinary exception recovery to model an interrupted process."""


@pytest.mark.parametrize('step', ['backup', 'install'])
def test_reopen_restores_interrupted_save(db, saved_product, monkeypatch, step):
    product_id, ids = saved_product
    before = snapshot(db, product_id)
    real_rename = Path.rename
    def interrupt(source, destination):
        result = real_rename(source, destination)
        if ((step == 'backup' and source.name == 'PROD-0001') or
                (step == 'install' and Path(destination).name == 'PROD-0001')):
            raise InterruptedSave()
        return result
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'rename', interrupt)
        with pytest.raises(InterruptedSave):
            db.sync_product_photos(product_id, ids[::-1])
    assert_snapshot(Database(db.db_path), product_id, before)
    assert_snapshot(Database(db.db_path), product_id, before)


def test_registration_rejects_managed_copy(db, saved_product):
    product_id, _ = saved_product
    copied = Path(db.get_product(product_id)['photos'][0]['copied_path'])
    before = copied.read_bytes()
    with pytest.raises(ValueError, match='administrad'):
        db.register_photo_file(copied)
    assert copied.read_bytes() == before


def test_scan_rejects_managed_folder_and_skips_nested_media(db, saved_product, isolated_storage):
    media = isolated_storage / 'media'
    with pytest.raises(ValueError, match='administrad'):
        db.scan_folder(media, recursive=True)
    assert db.scan_folder(isolated_storage, recursive=True) == 0
    with db.connection() as con:
        assert con.execute('SELECT COUNT(*) FROM photos').fetchone()[0] == 3


def test_creation_rejects_previously_registered_managed_source(db, saved_product, product_data):
    product_id, _ = saved_product
    copied = Path(db.get_product(product_id)['photos'][0]['copied_path'])
    with db.connection() as con:
        photo_id = con.execute('INSERT INTO photos(original_path, filename) VALUES (?, ?)',
                               (str(copied), copied.name)).lastrowid
    with pytest.raises(ValueError, match='administrad'):
        db.create_product(product_data, [photo_id])
    assert copied.is_file()
    assert len(db.list_products()) == 1


def test_duplicate_photo_ids_rejected_before_modifying_saved_files(db, saved_product):
    product_id, ids = saved_product
    before = snapshot(db, product_id)
    with pytest.raises(ValueError):
        db.sync_product_photos(product_id, [ids[0], ids[0]])
    assert_snapshot(db, product_id, before)


@pytest.mark.parametrize('step', ['copy', 'backup', 'install', 'before_commit', 'after_commit'])
def test_process_exit_recovers_old_or_committed_order(db, saved_product, isolated_storage, step):
    product_id, ids = saved_product
    before = snapshot(db, product_id)
    # An actual process exit bypasses context managers/finally and SQLite.close.
    script = textwrap.dedent('''
        import os, sys, sqlite3, shutil
        from pathlib import Path
        home, db_path, step = sys.argv[1:]
        Path.home = classmethod(lambda cls: Path(home))
        from app.data.database import Database
        db = Database(Path(db_path))
        real_rename = Path.rename
        def rename(source, destination):
            result = real_rename(source, destination)
            if ((step == 'backup' and source.name == 'PROD-0001') or
                (step == 'install' and Path(destination).name == 'PROD-0001')):
                os._exit(77)
            return result
        Path.rename = rename
        real_copy = shutil.copy2
        def copy(source, destination, *args, **kwargs):
            result = real_copy(source, destination, *args, **kwargs)
            if step == 'copy':
                os._exit(77)
            return result
        shutil.copy2 = copy
        class Connection(sqlite3.Connection):
            def commit(self):
                marked = self.execute('SELECT COUNT(*) FROM photo_file_commits').fetchone()[0]
                if marked and step == 'before_commit':
                    os._exit(77)
                super().commit()
                if marked and step == 'after_commit':
                    os._exit(77)
        connect = sqlite3.connect
        sqlite3.connect = lambda *a, **k: connect(*a, factory=Connection, **k)
        db.sync_product_photos(1, [3, 2, 1])
    ''')
    result = subprocess.run([sys.executable, '-c', script, str(isolated_storage.parent.parent),
                             str(db.db_path), step], capture_output=True, text=True, timeout=20)
    assert result.returncode == 77, result.stderr
    reopened = Database(db.db_path)
    if step != 'after_commit':
        assert_snapshot(reopened, product_id, before)
    else:
        photos = reopened.get_product(product_id)['photos']
        assert [p['id'] for p in photos] == ids[::-1]
        assert [p['position'] for p in photos] == [1, 2, 3]
        assert Path(photos[0]['copied_path']).read_bytes() == before[1]['PROD-0001-03.jpg']
        assert Path(photos[2]['copied_path']).read_bytes() == before[1]['PROD-0001-01.jpg']
    after = snapshot(reopened, product_id)
    assert_snapshot(Database(db.db_path), product_id, after)


def test_commit_error_restores_files(db, saved_product, monkeypatch):
    product_id, ids = saved_product
    before = snapshot(db, product_id)
    class FailedCommit(sqlite3.Connection):
        def commit(self):
            if self.execute('SELECT COUNT(*) FROM photo_file_commits').fetchone()[0]:
                raise sqlite3.OperationalError('simulated commit failure')
            super().commit()
    connect = sqlite3.connect
    monkeypatch.setattr(sqlite3, 'connect', lambda *a, **k: connect(*a, factory=FailedCommit, **k))
    with pytest.raises(sqlite3.OperationalError):
        db.sync_product_photos(product_id, ids[::-1])
    assert_snapshot(db, product_id, before)


def test_blocked_backup_cleanup_preserves_committed_save(db, saved_product, monkeypatch):
    product_id, ids = saved_product
    rmtree = shutil.rmtree
    def blocked(path, *args, **kwargs):
        if Path(path).name == 'backup':
            raise PermissionError('backup locked')
        return rmtree(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(shutil, 'rmtree', blocked)
        db.sync_product_photos(product_id, ids[::-1])
    assert [p['id'] for p in db.get_product(product_id)['photos']] == ids[::-1]
    after = snapshot(db, product_id)
    assert_snapshot(Database(db.db_path), product_id, after)


def test_new_managed_photo_is_rejected_during_sync(db, saved_product):
    product_id, ids = saved_product
    before = snapshot(db, product_id)
    copied = Path(before[0]['photos'][0]['copied_path'])
    with db.connection() as con:
        new_id = con.execute('INSERT INTO photos(original_path, filename) VALUES (?, ?)',
                             (str(copied), copied.name)).lastrowid
    with pytest.raises(ValueError, match='administrad'):
        db.sync_product_photos(product_id, [*ids, new_id])
    assert_snapshot(db, product_id, before)


def test_legacy_managed_original_can_use_existing_own_copy(db, saved_product):
    product_id, ids = saved_product
    before = snapshot(db, product_id)
    for photo in before[0]['photos']:
        with db.connection() as con:
            con.execute('UPDATE photos SET original_path = ? WHERE id = ?',
                        (photo['copied_path'], photo['id']))
    db.sync_product_photos(product_id, ids[::-1])
    assert [p['id'] for p in db.get_product(product_id)['photos']] == ids[::-1]
    assert Path(db.get_product(product_id)['photos'][0]['copied_path']).read_bytes() == before[1]['PROD-0001-03.jpg']


def test_failed_restore_keeps_backup_for_next_start(db, saved_product, monkeypatch, isolated_storage):
    product_id, ids = saved_product
    before = snapshot(db, product_id)
    from app.services.photo_storage import PhotoRecoveryError
    with db.connection() as con:
        con.execute("""CREATE TRIGGER fail_photos BEFORE INSERT ON product_photos
                       BEGIN SELECT RAISE(ABORT, 'simulated SQL failure'); END""")
    rename = Path.rename
    def blocked_restore(source, destination):
        if source.name == 'backup':
            raise PermissionError('restore blocked')
        return rename(source, destination)
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'rename', blocked_restore)
        with pytest.raises(PhotoRecoveryError):
            db.sync_product_photos(product_id, ids[::-1])
    backups = list((isolated_storage / 'media').rglob('backup'))
    assert len(backups) == 1
    assert {p.name: p.read_bytes() for p in backups[0].iterdir()} == before[1]
    assert_snapshot(Database(db.db_path), product_id, before)
    assert_snapshot(Database(db.db_path), product_id, before)


def test_corrupt_copy_never_replaces_old_photos(db, saved_product, monkeypatch):
    product_id, ids = saved_product
    before = snapshot(db, product_id)
    def corrupt(source, destination, *args, **kwargs):
        Path(destination).write_bytes(b'incomplete')
    monkeypatch.setattr(shutil, 'copy2', corrupt)
    with pytest.raises(OSError):
        db.sync_product_photos(product_id, ids[::-1])
    assert_snapshot(db, product_id, before)


def test_no_old_folder_restores_absence_after_failed_save(db, saved_product):
    product_id, ids = saved_product
    before = db.get_product(product_id)
    folder = Path(before['photos'][0]['copied_path']).parent
    shutil.rmtree(folder)
    with db.connection() as con:
        con.execute("""CREATE TRIGGER fail_photos BEFORE INSERT ON product_photos
                       BEGIN SELECT RAISE(ABORT, 'simulated SQL failure'); END""")
    with pytest.raises(sqlite3.DatabaseError):
        db.sync_product_photos(product_id, ids[::-1])
    assert not folder.exists()
    assert db.get_product(product_id) == before


def test_corrupt_journal_stops_recovery_without_deleting_backup(db, saved_product, monkeypatch, isolated_storage):
    product_id, ids = saved_product
    before = snapshot(db, product_id)
    from app.services.photo_storage import PhotoRecoveryError
    rename = Path.rename
    def interrupt(source, destination):
        result = rename(source, destination)
        if source.name == 'PROD-0001':
            raise InterruptedSave()
        return result
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'rename', interrupt)
        with pytest.raises(InterruptedSave):
            db.sync_product_photos(product_id, ids[::-1])
    manifest = next((isolated_storage / 'media').rglob('manifest.json'))
    original = manifest.read_text(encoding='utf-8')
    manifest.write_text('{invalid', encoding='utf-8')
    with pytest.raises(PhotoRecoveryError):
        Database(db.db_path)
    backup = manifest.parent / 'backup'
    assert {p.name: p.read_bytes() for p in backup.iterdir()} == before[1]
    manifest.write_text(original, encoding='utf-8')
    assert_snapshot(Database(db.db_path), product_id, before)


def test_invalid_code_never_touches_outside_media(db, saved_product, tmp_path):
    product_id, ids = saved_product
    external = tmp_path / 'external'
    external.mkdir()
    sentinel = external / 'keep.jpg'
    sentinel.write_bytes(b'keep original')
    with db.connection() as con:
        con.execute('UPDATE products SET code = ? WHERE id = ?', (str(external), product_id))
    from app.services.photo_storage import PhotoRecoveryError
    with pytest.raises(PhotoRecoveryError):
        db.sync_product_photos(product_id, ids[::-1])
    assert sentinel.read_bytes() == b'keep original'


@pytest.mark.parametrize('restore_step', ['discard', 'restore'])
def test_recovery_itself_can_be_interrupted_and_retried(db, saved_product, monkeypatch, restore_step):
    product_id, ids = saved_product
    before = snapshot(db, product_id)
    rename = Path.rename
    def stop_save(source, destination):
        result = rename(source, destination)
        if Path(destination).name == 'PROD-0001':
            raise InterruptedSave()
        return result
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'rename', stop_save)
        with pytest.raises(InterruptedSave):
            db.sync_product_photos(product_id, ids[::-1])
    def stop_recovery(source, destination):
        result = rename(source, destination)
        if ((restore_step == 'discard' and Path(destination).name == 'discard') or
                (restore_step == 'restore' and source.name == 'backup')):
            raise InterruptedSave()
        return result
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'rename', stop_recovery)
        with pytest.raises(InterruptedSave):
            Database(db.db_path)
    assert_snapshot(Database(db.db_path), product_id, before)
