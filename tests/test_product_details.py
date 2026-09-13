import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox
from app.ui.product_dialogs import ProductEditDialog
from app.ui.main_window import MainWindow

from app.data.database import Database
from app.services.export_service import export_products
from openpyxl import load_workbook


def test_internal_details_survive_creation_update_restart(db, product_data):
    data = dict(product_data, condition_rating=8, internal_notes='Mancha\nEsquina izquierda')
    product_id, _ = db.create_product(data, [])
    product = Database(db.db_path).get_product(product_id)['product']
    assert product['condition_rating'] == 8
    assert product['internal_notes'] == data['internal_notes']
    db.update_product(product_id, dict(data, condition_rating=None, internal_notes=''))
    product = Database(db.db_path).get_product(product_id)['product']
    assert product['condition_rating'] is None
    assert product['internal_notes'] == ''


@pytest.mark.parametrize('rating', [0, 11, -1, 1.5, True, '8'])
def test_invalid_condition_is_rejected_on_create_and_update(db, product_data, rating):
    product_id, _ = db.create_product(product_data, [])
    data = dict(product_data, condition_rating=rating)
    with pytest.raises(ValueError):
        db.create_product(data, [])
    with pytest.raises(ValueError):
        db.update_product(product_id, data)


def test_legacy_migration_preserves_product_and_sets_empty_details(db, product_data):
    product_id, _ = db.create_product(product_data, [])
    with db.connection() as con:
        columns = {row['name'] for row in con.execute('PRAGMA table_info(products)')}
        for column in ('condition_rating', 'internal_notes'):
            if column in columns:
                con.execute(f'ALTER TABLE products DROP COLUMN {column}')
    product = Database(db.db_path).get_product(product_id)['product']
    assert product['title'] == product_data['title']
    assert product['condition_rating'] is None
    assert product['internal_notes'] == ''


def test_export_excludes_internal_details(db, product_data, tmp_path):
    db.create_product(dict(product_data, condition_rating=8,
                           internal_notes='PRIVATE_SENTINEL', final_description='Public text'), [])
    rows = db.export_rows()
    assert 'internal_notes' not in rows[0]
    assert 'condition_rating' not in rows[0]
    output = export_products(rows, tmp_path / 'export.xlsx')
    workbook = load_workbook(output)
    try:
        values = str(list(workbook.active.values))
        assert 'PRIVATE_SENTINEL' not in values
        assert 'Public text' in values
    finally:
        workbook.close()


def test_legacy_update_preserves_internal_details(db, product_data):
    product_id, _ = db.create_product(dict(product_data, condition_rating=1, internal_notes='Keep'), [])
    db.update_product(product_id, product_data)
    product = db.get_product(product_id)['product']
    assert product['condition_rating'] == 1
    assert product['internal_notes'] == 'Keep'


def test_editor_loads_and_saves_internal_fields(db, product_data):
    app = QApplication.instance() or QApplication([])
    product_id, _ = db.create_product(dict(product_data, condition_rating=10,
                                         internal_notes='Private old', final_description='Public'), [])
    dialog = ProductEditDialog(db, product_id)
    try:
        assert dialog.condition.currentData() == 10
        assert dialog.internal_notes.toPlainText() == 'Private old'
        dialog.condition.setCurrentIndex(7)
        dialog.internal_notes.setPlainText('Private new\nDent')
        dialog.regenerate()
        assert 'Private' not in dialog.final_description.toPlainText()
        public = dialog.final_description.toPlainText()
        dialog.save()
        product = db.get_product(product_id)['product']
        assert product['condition_rating'] == 7
        assert product['internal_notes'] == 'Private new\nDent'
        assert product['final_description'] == public
    finally:
        dialog.deleteLater()
        app.processEvents()


def test_creation_form_saves_and_resets_private_fields(db, source_photos, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: None)
    window = MainWindow()
    try:
        monkeypatch.setattr(window, 'selected_photo_ids', lambda: [source_photos[0][0]])
        window.title_input.setText('Monitor')
        window.condition_input.setCurrentIndex(9)
        window.internal_notes_input.setPlainText('PRIVATE_SENTINEL')
        window.update_final_preview()
        assert 'PRIVATE_SENTINEL' not in window.final_preview.toPlainText()
        window.create_product()
        product = db.list_products()[0]
        assert product['condition_rating'] == 9
        assert product['internal_notes'] == 'PRIVATE_SENTINEL'
        assert 'PRIVATE_SENTINEL' not in product['final_description']
        assert window.condition_input.currentData() is None
        assert window.internal_notes_input.toPlainText() == ''
    finally:
        window.deleteLater()
        app.processEvents()
