from pathlib import Path
import subprocess
import sys
import textwrap
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest

from app.data.database import Database
from app.services.photo_storage import PhotoRecoveryError


@pytest.mark.parametrize('step', ['prepared', 'moved', 'before_commit', 'committed', 'cleanup'])
def test_killed_deletion_recovers(db, product_data, source_photos, isolated_storage, step):
    ids = [photo_id for photo_id, _ in source_photos]
    product_id, code = db.create_product(product_data, ids)
    before = db.get_product(product_id)
    originals = {path: path.read_bytes() for _, path in source_photos}
    copies = {Path(row['copied_path']): Path(row['copied_path']).read_bytes() for row in before['photos']}
    child = textwrap.dedent('''
        import os, sys, sqlite3
        from pathlib import Path
        root, product_id, step = sys.argv[1:]
        root = Path(root)
        Path.home = classmethod(lambda cls: root.parent.parent)
        from app.data.database import Database
        db = Database(root / 'marketplace.db')
        rename = Path.rename
        replace = Path.replace
        unlink = Path.unlink
        def move(path, target):
            result = rename(path, target)
            if step == 'moved' and Path(target).name == 'backup':
                os._exit(74)
            return result
        def publish(path, target):
            result = replace(path, target)
            if step == 'prepared' and Path(target).name == 'manifest.json':
                os._exit(74)
            return result
        def remove(path, *args, **kwargs):
            result = unlink(path, *args, **kwargs)
            if step == 'cleanup' and path.parent.name == 'backup':
                os._exit(74)
            return result
        Path.rename, Path.replace, Path.unlink = move, publish, remove
        class Connection(sqlite3.Connection):
            def commit(self):
                marked = self.execute('SELECT COUNT(*) FROM photo_file_commits').fetchone()[0]
                if marked and step == 'before_commit':
                    os._exit(74)
                super().commit()
                if marked and step == 'committed':
                    os._exit(74)
        connect = sqlite3.connect
        sqlite3.connect = lambda *a, **k: connect(*a, factory=Connection, **k)
        db.delete_product(int(product_id))
    ''')
    result = subprocess.run([sys.executable, '-c', child, str(isolated_storage), str(product_id), step],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 74, result.stderr
    for _ in range(2):
        reopened = Database(db.db_path)
        if step in ('committed', 'cleanup'):
            assert reopened.get_product(product_id) is None
            assert not (isolated_storage / 'media' / code).exists()
        else:
            assert reopened.get_product(product_id) == before
            assert all(path.read_bytes() == value for path, value in copies.items())
        assert all(path.read_bytes() == value for path, value in originals.items())


def test_delete_refuses_unknown_files(db, product_data, source_photos):
    product_id, _ = db.create_product(product_data, [source_photos[0][0]])
    before = db.get_product(product_id)
    sentinel = Path(before['photos'][0]['copied_path']).parent / 'personal.txt'
    sentinel.write_text('keep')
    with pytest.raises(PhotoRecoveryError):
        db.delete_product(product_id)
    assert db.get_product(product_id) == before
    assert sentinel.read_text() == 'keep'


def test_committed_cleanup_preserves_recreated_product_folder(db, product_data, source_photos, monkeypatch):
    product_id, _ = db.create_product(product_data, [source_photos[0][0]])
    final = Path(db.get_product(product_id)['photos'][0]['copied_path']).parent
    def locked():
        raise OSError('locked backup')
    monkeypatch.setattr(db, '_recover_photo_operations', locked)
    db.delete_product(product_id)
    final.mkdir()
    sentinel = final / 'new.txt'
    sentinel.write_text('keep')
    assert Database(db.db_path).get_product(product_id) is None
    assert sentinel.read_text() == 'keep'


def test_interrupted_restoration_is_repeatable(db, product_data, source_photos, monkeypatch):
    from app.services.photo_storage import PhotoStorage
    product_id, code = db.create_product(product_data, [source_photos[0][0]])
    before = db.get_product(product_id)
    path = Path(before['photos'][0]['copied_path'])
    storage = PhotoStorage(path.parent.parent, db.db_path)
    with db.connection() as con:
        con.execute('BEGIN IMMEDIATE')
        storage.prepare_delete(code, [str(path)])
    class Interrupted(BaseException):
        pass
    rename = Path.rename
    def interrupt(source, target):
        result = rename(source, target)
        if source.name == 'backup':
            raise Interrupted()
        return result
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'rename', interrupt)
        with pytest.raises(Interrupted):
            Database(db.db_path)
    assert Database(db.db_path).get_product(product_id) == before
    assert path.read_bytes() == source_photos[0][1].read_bytes()


def test_deletion_error_is_shown_in_product_list(db, product_data, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from app.ui.product_dialogs import ProductsDialog
    app = QApplication.instance() or QApplication([])
    db.create_product(product_data, [])
    dialog = ProductsDialog(db)
    messages = []
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: messages.append(args[-1]))
    def blocked(*args):
        raise PhotoRecoveryError('foreign file')
    monkeypatch.setattr(db, 'delete_product', blocked)
    try:
        dialog.table.selectRow(0)
        dialog.delete_selected()
        assert messages == ['foreign file']
        assert dialog.table.rowCount() == 1
    finally:
        dialog.deleteLater()
        app.processEvents()
