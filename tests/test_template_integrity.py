import sqlite3

import pytest

from app.data.database import Database


def test_sqlite_rejects_unknown_template_and_nulls_deleted_reference(db, product_data):
    template_id = db.create_template('Used', 'Body')
    product_id, _ = db.create_product(dict(product_data, template_id=template_id,
                                         final_description='Keep text'), [])
    with pytest.raises(sqlite3.IntegrityError), db.connection() as con:
        con.execute('UPDATE products SET template_id = 999999 WHERE id = ?', (product_id,))
    with db.connection() as con:
        con.execute('DELETE FROM templates WHERE id = ?', (template_id,))
    product = db.get_product(product_id)['product']
    assert product['template_id'] is None
    assert product['final_description'] == 'Keep text'


def make_legacy(db):
    # Build a pre-FK products table independently of the new migration.
    with sqlite3.connect(db.db_path) as con:
        con.execute('PRAGMA foreign_keys = OFF')
        schema = con.execute("SELECT sql FROM sqlite_master WHERE name = 'products'").fetchone()[0]
        schema = schema.replace('REFERENCES templates(id) ON DELETE SET NULL', '')
        con.execute('CREATE TABLE old_products ' + schema[schema.index('('):])
        con.execute('INSERT INTO old_products SELECT * FROM products')
        con.execute('DROP TABLE products')
        con.execute('ALTER TABLE old_products RENAME TO products')
        con.execute('CREATE UNIQUE INDEX legacy_product_id ON products(id)')
        con.execute('CREATE INDEX legacy_title ON products(title)')


def test_migration_preserves_rows_photos_and_cleans_only_orphan_template(db, product_data, source_photos):
    valid = db.get_default_template_id()
    product_id, _ = db.create_product(dict(product_data, template_id=valid,
                                         internal_notes='Private', condition_rating=8), [source_photos[0][0]])
    other_id, _ = db.create_product(dict(product_data, final_description='Saved\nText'), [])
    before = db.get_product(product_id)
    make_legacy(db)
    with sqlite3.connect(db.db_path) as con:
        con.execute('UPDATE products SET template_id = 999999 WHERE id = ?', (other_id,))
    reopened = Database(db.db_path)
    assert reopened.get_product(product_id) == before
    assert reopened.get_product(other_id)['product']['template_id'] is None
    assert reopened.get_product(other_id)['product']['final_description'] == 'Saved\nText'
    assert Database(db.db_path).get_product(product_id) == before
    with reopened.connection() as con:
        assert con.execute('PRAGMA foreign_key_check').fetchall() == []
        assert con.execute("SELECT 1 FROM sqlite_master WHERE name = 'legacy_title'").fetchone()


def test_failed_migration_rolls_back_schema_and_data(db, product_data, monkeypatch):
    product_id, _ = db.create_product(product_data, [])
    make_legacy(db)
    before = db.get_product(product_id)
    original = Database._migrate
    def fail(self, con):
        original(self, con)
        raise RuntimeError('interrupted migration')
    with monkeypatch.context() as patch:
        patch.setattr(Database, '_migrate', fail)
        with pytest.raises(RuntimeError, match='interrupted migration'):
            Database(db.db_path)
    with sqlite3.connect(db.db_path) as con:
        assert con.execute('PRAGMA foreign_key_list(products)').fetchall() == []
    assert Database(db.db_path).get_product(product_id) == before


def test_migration_preserves_autoincrement_checks_and_triggers(db, product_data):
    db.create_product(product_data, [])
    make_legacy(db)
    with sqlite3.connect(db.db_path) as con:
        con.execute("UPDATE sqlite_sequence SET seq = 100 WHERE name = 'products'")
        con.execute('CREATE TABLE audit (product_id INTEGER)')
        con.execute('''CREATE TRIGGER product_audit AFTER INSERT ON products
                       BEGIN INSERT INTO audit VALUES (NEW.id); END''')
    reopened = Database(db.db_path)
    product_id, _ = reopened.create_product(product_data, [])
    assert product_id == 101
    with reopened.connection() as con:
        assert con.execute('SELECT product_id FROM audit').fetchone()[0] == 101
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('UPDATE products SET condition_rating = 99')
