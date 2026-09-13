import os
import sqlite3

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from app.data.database import Database
from app.ui.product_dialogs import ProductEditDialog


def test_delete_clears_product_reference_and_persists_settings(db, product_data):
    fallback = db.get_default_template_id()
    removed = db.create_template('Removed', 'Body')
    product_id, _ = db.create_product(dict(product_data, template_id=removed,
                                         final_description='Saved\n\nDescription'), [])
    before = db.get_product(product_id)['product']
    db.set_default_template_id(removed)
    db.set_last_template_id(removed)
    db.delete_template(removed)
    reopened = Database(db.db_path)
    assert reopened.get_product(product_id)['product'] == dict(before, template_id=None)
    assert reopened.get_setting('default_template_id') == str(fallback)
    assert reopened.get_setting('last_template_id') == str(fallback)


def test_delete_failure_rolls_back_all_changes(db, product_data):
    removed = db.create_template('Removed', 'Body')
    product_id, _ = db.create_product(dict(product_data, template_id=removed), [])
    db.set_default_template_id(removed)
    db.set_last_template_id(removed)
    with db.connection() as con:
        con.execute('''CREATE TRIGGER fail_setting BEFORE UPDATE ON settings
                       BEGIN SELECT RAISE(ABORT, 'injected failure'); END''')
    with pytest.raises(sqlite3.IntegrityError, match='injected failure'):
        db.delete_template(removed)
    assert db.get_template(removed) is not None
    assert db.get_product(product_id)['product']['template_id'] == removed
    assert db.get_setting('default_template_id') == str(removed)
    assert db.get_setting('last_template_id') == str(removed)


def test_deleting_other_template_preserves_valid_preferences(db):
    default = db.get_default_template_id()
    last = db.create_template('Last', 'Body')
    removed = db.create_template('Removed', 'Body')
    db.set_last_template_id(last)
    db.delete_template(removed)
    assert db.get_setting('default_template_id') == str(default)
    assert db.get_setting('last_template_id') == str(last)


def test_editor_uses_default_for_legacy_missing_template(db, product_data):
    app = QApplication.instance() or QApplication([])
    default = db.create_template('ZZ default', 'Default body')
    db.set_default_template_id(default)
    product_id, _ = db.create_product(dict(product_data, template_id=999999,
                                         final_description='Saved text'), [])
    dialog = ProductEditDialog(db, product_id)
    try:
        assert dialog.template.currentData() == default
        assert db.get_product(product_id)['product']['final_description'] == 'Saved text'
    finally:
        dialog.deleteLater()
        app.processEvents()
