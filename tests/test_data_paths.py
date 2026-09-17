from pathlib import Path
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PIL import Image

from app.data.database import Database


def test_custom_database_does_not_create_default_directories(tmp_path, isolated_storage):
    db = Database(tmp_path / 'custom' / 'marketplace.db')
    assert db.db_path.is_file()
    assert not isolated_storage.exists()
    assert db.paths.media_dir == tmp_path / 'custom' / 'media'


def test_databases_in_same_directory_have_independent_files(tmp_path, isolated_storage, product_data):
    source = tmp_path / 'original.png'
    Image.new('RGB', (12, 8), 'red').save(source)
    first = Database(tmp_path / 'one.db')
    second = Database(tmp_path / 'two.db')
    first_id, code1 = first.create_product(product_data, [first.register_photo_file(source)])
    second_id, code2 = second.create_product(product_data, [second.register_photo_file(source)])
    assert code1 == code2 == 'PROD-0001'
    a = Path(first.get_product(first_id)['photos'][0]['copied_path'])
    b = Path(second.get_product(second_id)['photos'][0]['copied_path'])
    assert a != b
    first.delete_product(first_id)
    assert b.read_bytes() == source.read_bytes()
    assert Database(second.db_path).get_product(second_id) is not None
    assert not isolated_storage.exists()


def test_default_paths_remain_compatible(db, isolated_storage):
    assert db.db_path == isolated_storage / 'marketplace.db'
    assert db.paths.media_dir == isolated_storage / 'media'
    assert db.paths.thumbnail_dir == isolated_storage / 'cache' / 'thumbnails'
    assert db.paths.export_dir == isolated_storage / 'exports'


def test_custom_ui_uses_own_cache_folder_and_export(tmp_path, isolated_storage, product_data, monkeypatch):
    from PySide6.QtWidgets import QApplication, QFileDialog
    from app.ui.photo_manager_dialog import ProductPhotosDialog
    from app.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    source = tmp_path / 'source.png'
    Image.new('RGB', (20, 10), 'blue').save(source)
    db = Database(tmp_path / 'alternative.db')
    product_id, code = db.create_product(product_data, [db.register_photo_file(source)])
    opened = []
    monkeypatch.setattr(os, 'startfile', lambda path: opened.append(Path(path)), raising=False)
    suggested = []
    def save_dialog(*args):
        suggested.append(Path(args[2]))
        return '', ''
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', save_dialog)
    photos = ProductPhotosDialog(db, product_id)
    window = MainWindow(db=db)
    try:
        photos.open_photo_folder()
        window.export_xlsx()
        assert opened == [db.paths.media_dir / code]
        assert suggested == [db.paths.export_dir / 'marketplace.xlsx']
        assert list(db.paths.thumbnail_dir.glob('*.jpg'))
        assert not isolated_storage.exists()
    finally:
        photos.deleteLater()
        window.deleteLater()
        app.processEvents()


def test_custom_recovery_does_not_recover_another_database(tmp_path, product_data):
    first = Database(tmp_path / 'one.db')
    second = Database(tmp_path / 'two.db')
    product_id, code = first.create_product(product_data, [])
    storage = first.photo_storage
    with first.connection() as con:
        con.execute('BEGIN IMMEDIATE')
        operation = storage.prepare_delete(code, [])
    assert not storage.product_folder(code).exists()
    Database(second.db_path)
    assert operation.exists()
    assert not storage.product_folder(code).exists()
    assert Database(first.db_path).get_product(product_id) is not None
    assert storage.product_folder(code).is_dir()
