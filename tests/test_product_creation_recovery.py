from pathlib import Path
import subprocess
import sys
import sqlite3
import textwrap

import pytest

from app.data.database import Database
from app.services.photo_storage import PhotoStorage


@pytest.mark.parametrize('step', ['copy', 'prepared', 'install', 'before_commit', 'commit'])
def test_killed_creation_recovers_on_restart(db, source_photos, isolated_storage, step):
    photo_id, source = source_photos[0]
    original = source.read_bytes()
    child = textwrap.dedent('''
        import os, sys, shutil, sqlite3
        from pathlib import Path
        root, step, photo_id = sys.argv[1:]
        root = Path(root)
        Path.home = classmethod(lambda cls: root.parent.parent)
        from app.data.database import Database
        from app.services.photo_storage import PhotoStorage
        db = Database(root / 'marketplace.db')
        if step == 'copy':
            real = shutil.copy2
            def copy(*args, **kwargs):
                real(*args, **kwargs)
                os._exit(73)
            shutil.copy2 = copy
        elif step == 'prepared':
            real = PhotoStorage.prepare
            def prepare(*args, **kwargs):
                real(*args, **kwargs)
                os._exit(73)
            PhotoStorage.prepare = prepare
        elif step == 'install':
            real = Path.rename
            def rename(path, target):
                result = real(path, target)
                if Path(target).name.startswith('PROD-'):
                    os._exit(73)
                return result
            Path.rename = rename
        elif step == 'before_commit':
            class Connection(sqlite3.Connection):
                def commit(self):
                    if self.execute('SELECT COUNT(*) FROM photo_file_commits').fetchone()[0]:
                        os._exit(73)
                    super().commit()
            connect = sqlite3.connect
            sqlite3.connect = lambda *a, **k: connect(*a, factory=Connection, **k)
        else:
            def stop_cleanup():
                os._exit(73)
            db._recover_photo_operations = stop_cleanup
        db.create_product({'title': 'Created', 'price': 10}, [int(photo_id)])
    ''')
    result = subprocess.run([sys.executable, '-c', child, str(isolated_storage), step, str(photo_id)],
                            cwd=Path(__file__).parents[1], capture_output=True, text=True, timeout=30)
    assert result.returncode == 73, result.stderr
    for _ in range(2):
        reopened = Database(db.db_path)
        products = reopened.list_products()
        if step == 'commit':
            assert len(products) == 1
            saved = Path(reopened.get_product(products[0]['id'])['photos'][0]['copied_path'])
            assert saved.read_bytes() == original
        else:
            assert products == []
            assert not (isolated_storage / 'media' / 'PROD-0001').exists()
        assert source.read_bytes() == original
        assert reopened.next_product_code() == 'PROD-0002'


def test_creation_copy_corruption_is_rejected(db, product_data, source_photos, isolated_storage, monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, 'copy2', lambda source, target: Path(target).write_bytes(b'broken'))
    with pytest.raises(OSError):
        db.create_product(product_data, [source_photos[0][0]])
    assert db.list_products() == []
    assert not (isolated_storage / 'media' / 'PROD-0001').exists()


def test_sql_failure_rolls_back_new_folder(db, product_data, source_photos, isolated_storage):
    photo_id, source = source_photos[0]
    original = source.read_bytes()
    with db.connection() as con:
        con.execute("""CREATE TRIGGER fail_new_product BEFORE INSERT ON product_photos
                       BEGIN SELECT RAISE(ABORT, 'injected SQL failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match='injected SQL failure'):
        db.create_product(product_data, [photo_id])
    assert Database(db.db_path).list_products() == []
    assert not (isolated_storage / 'media' / 'PROD-0001').exists()
    assert source.read_bytes() == original


def test_committed_creation_survives_cleanup_failure(db, product_data, source_photos, monkeypatch):
    def fail_cleanup():
        raise OSError('cleanup locked')
    monkeypatch.setattr(db, '_recover_photo_operations', fail_cleanup)
    photo_id, source = source_photos[0]
    product_id, _ = db.create_product(product_data, [photo_id])
    reopened = Database(db.db_path)
    saved = Path(reopened.get_product(product_id)['photos'][0]['copied_path'])
    assert saved.read_bytes() == source.read_bytes()


@pytest.mark.parametrize('with_file', [False, True])
def test_interrupted_collision_cleanup_never_removes_foreign_folder(db, isolated_storage, monkeypatch, with_file):
    storage = PhotoStorage(isolated_storage / 'media', db.db_path)
    with db.connection() as con:
        con.execute('BEGIN IMMEDIATE')
        operation, _ = storage.prepare('PROD-0001', [], create_only=True)
    foreign = isolated_storage / 'media' / 'PROD-0001'
    foreign.mkdir()
    if with_file:
        (foreign / 'keep.txt').write_text('keep')
    class Interrupted(BaseException):
        pass
    remove = storage._remove_tree
    def interrupt(path):
        remove(path)
        if Path(path) == operation / 'stage':
            raise Interrupted()
    with monkeypatch.context() as patch:
        patch.setattr(storage, '_remove_tree', interrupt)
        with pytest.raises(Interrupted), db.connection() as con:
            con.execute('BEGIN IMMEDIATE')
            storage.recover(con)
    Database(db.db_path)
    assert foreign.is_dir()
    if with_file:
        assert (foreign / 'keep.txt').read_text() == 'keep'


def test_interrupted_rollback_cleanup_preserves_new_foreign_folder(db, isolated_storage, monkeypatch):
    storage = PhotoStorage(isolated_storage / 'media', db.db_path)
    with db.connection() as con:
        con.execute('BEGIN IMMEDIATE')
        operation, _ = storage.prepare('PROD-0001', [], create_only=True)
        storage.install_new(operation, 'PROD-0001')
    final = isolated_storage / 'media' / 'PROD-0001'
    class Interrupted(BaseException):
        pass
    remove = storage._remove_tree
    def interrupt(path):
        remove(path)
        if Path(path) == operation / 'discard':
            final.mkdir()
            raise Interrupted()
    with monkeypatch.context() as patch:
        patch.setattr(storage, '_remove_tree', interrupt)
        with pytest.raises(Interrupted), db.connection() as con:
            con.execute('BEGIN IMMEDIATE')
            storage.recover(con)
    Database(db.db_path)
    assert final.is_dir()
