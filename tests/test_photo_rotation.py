import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PIL import Image, ImageOps
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog

from app.data.database import Database
from app.ui.photo_manager_dialog import ProductPhotosDialog


@pytest.fixture
def asymmetric_photo(tmp_path, db):
    path = tmp_path / 'colors.png'
    image = Image.new('RGB', (30, 20), 'red')
    image.paste('blue', (0, 0, 15, 20))
    image.save(path)
    return db.register_photo_file(path), path


@pytest.mark.parametrize('degrees', [90, 180, 270, -90])
def test_rotation_preserves_original_and_survives_reorder(db, product_data, asymmetric_photo, source_photos, degrees):
    photo_id, source = asymmetric_photo
    other_id = source_photos[0][0]
    original = source.read_bytes()
    product_id, _ = db.create_product(product_data, [photo_id, other_id])
    paths = db.sync_product_photos(product_id, [photo_id, other_id], rotations={photo_id: degrees})
    with Image.open(source) as image:
        expected = image.rotate(-degrees, expand=True)
    with Image.open(paths[0]) as actual:
        assert actual.size == expected.size
        assert actual.tobytes() == expected.tobytes()
    saved = Path(paths[0]).read_bytes()
    reopened = Database(db.db_path)
    reordered = reopened.sync_product_photos(product_id, [other_id, photo_id])
    assert Path(reordered[1]).read_bytes() == saved
    assert source.read_bytes() == original


def test_rotation_respects_exif_orientation(db, tmp_path, product_data):
    path = tmp_path / 'phone.jpg'
    image = Image.new('RGB', (30, 20), 'red')
    exif = Image.Exif()
    exif[274] = 6
    image.save(path, exif=exif)
    original = path.read_bytes()
    photo_id = db.register_photo_file(path)
    product_id, _ = db.create_product(product_data, [photo_id])
    saved = db.sync_product_photos(product_id, [photo_id], rotations={photo_id: 90})[0]
    with Image.open(saved) as result:
        assert ImageOps.exif_transpose(result).size == (30, 20)
        assert result.getexif().get(274, 1) == 1
    assert path.read_bytes() == original


def test_saved_rotations_accumulate_without_original(db, product_data, asymmetric_photo):
    photo_id, source = asymmetric_photo
    with Image.open(source) as image:
        expected = image.rotate(-180, expand=True)
    product_id, _ = db.create_product(product_data, [photo_id])
    db.sync_product_photos(product_id, [photo_id], rotations={photo_id: 90})
    source.unlink()
    saved = db.sync_product_photos(product_id, [photo_id], rotations={photo_id: 90})[0]
    with Image.open(saved) as actual:
        assert actual.size == expected.size
        assert actual.tobytes() == expected.tobytes()


@pytest.mark.parametrize('degrees', [45, '90', 1.5])
def test_invalid_rotation_preserves_saved_files(db, product_data, asymmetric_photo, degrees):
    photo_id, _ = asymmetric_photo
    product_id, _ = db.create_product(product_data, [photo_id])
    saved = Path(db.get_product(product_id)['photos'][0]['copied_path'])
    before = saved.read_bytes()
    with pytest.raises(ValueError, match='90'):
        db.sync_product_photos(product_id, [photo_id], rotations={photo_id: degrees})
    assert saved.read_bytes() == before


def test_rotation_rollback_restores_saved_photo(db, product_data, asymmetric_photo):
    photo_id, _ = asymmetric_photo
    product_id, _ = db.create_product(product_data, [photo_id])
    before = db.get_product(product_id)
    path = Path(before['photos'][0]['copied_path'])
    content = path.read_bytes()
    with db.connection() as con:
        con.execute('''CREATE TRIGGER fail_rotation BEFORE INSERT ON product_photos
                       BEGIN SELECT RAISE(ABORT, 'injected failure'); END''')
    with pytest.raises(Exception, match='injected failure'):
        db.sync_product_photos(product_id, [photo_id], rotations={photo_id: 90})
    assert Database(db.db_path).get_product(product_id) == before
    assert path.read_bytes() == content


def test_cancel_rotation_does_not_write_photos(db, product_data, asymmetric_photo):
    app = QApplication.instance() or QApplication([])
    photo_id, source = asymmetric_photo
    product_id, _ = db.create_product(product_data, [photo_id])
    saved = Path(db.get_product(product_id)['photos'][0]['copied_path'])
    original = saved.read_bytes()
    dialog = ProductPhotosDialog(db, product_id)
    try:
        dialog.list.setCurrentRow(0)
        dialog.rotate_selected(90)
        dialog.reject()
        assert saved.read_bytes() == original == source.read_bytes()
    finally:
        dialog.deleteLater()
        app.processEvents()


def test_dialog_saves_pending_rotation(db, product_data, asymmetric_photo, monkeypatch):
    app = QApplication.instance() or QApplication([])
    photo_id, _ = asymmetric_photo
    product_id, _ = db.create_product(product_data, [photo_id])
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: None)
    dialog = ProductPhotosDialog(db, product_id)
    try:
        dialog.list.setCurrentRow(0)
        dialog.rotate_selected(90)
        dialog.save()
        assert dialog.result() == QDialog.DialogCode.Accepted
        with Image.open(db.get_product(product_id)['photos'][0]['copied_path']) as image:
            assert image.size == (20, 30)
    finally:
        dialog.deleteLater()
        app.processEvents()
