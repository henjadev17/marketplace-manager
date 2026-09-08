import sqlite3

from app.data.database import Database


def test_legacy_migration_preserves_data_and_is_idempotent(tmp_path):
    path = tmp_path / "legacy.db"
    # Independent historical schema lacking all three migrated columns.
    with sqlite3.connect(path) as con:
        con.executescript("""
            CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
            INSERT INTO settings VALUES ('description_template', 'Legacy template');
            INSERT INTO settings VALUES ('delivery_method', 'Pickup');
            INSERT INTO settings VALUES ('payment_method', 'Cash');
            INSERT INTO settings VALUES ('contact_number', '123');
            CREATE TABLE products (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL, price REAL NOT NULL DEFAULT 0,
                description TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '',
                location TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'DRAFT',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO products (id, code, title, price, description, category, location, status)
                VALUES (7, 'PROD-0042', 'Monitor', 99.5, 'Keep me', 'Tech', 'Lima', 'SOLD');
            CREATE TABLE photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT, original_path TEXT NOT NULL UNIQUE,
                filename TEXT NOT NULL, file_size INTEGER NOT NULL DEFAULT 0,
                modified_ts REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE product_photos (
                product_id INTEGER NOT NULL, photo_id INTEGER NOT NULL,
                position INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (product_id, photo_id),
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
                FOREIGN KEY (photo_id) REFERENCES photos(id) ON DELETE CASCADE
            );
        """)
        con.execute("INSERT INTO photos (id, original_path, filename) VALUES (9, ?, 'original.jpg')",
                    (str(tmp_path / "original.jpg"),))
        con.execute("INSERT INTO product_photos VALUES (7, 9, 2)")
        con.row_factory = sqlite3.Row
        original = dict(con.execute("SELECT * FROM products").fetchone())
    migrated = Database(path)
    full = migrated.get_product(7)
    for key, value in original.items():
        assert full["product"][key] == value
    assert full["product"]["final_description"] == ""
    assert full["product"]["template_id"] is None
    assert full["photos"][0]["id"] == 9
    assert full["photos"][0]["position"] == 2
    assert full["photos"][0]["copied_path"] == ""
    assert migrated.next_product_code() == "PROD-0043"
    settings = migrated.get_template_settings()
    assert settings["template"] == "Legacy template"
    assert settings["delivery_method"] == "Pickup"
    assert settings["payment_method"] == "Cash"
    assert settings["contact_number"] == "123"
    reopened = Database(path)
    assert reopened.get_product(7) == full
    assert reopened.get_template_settings() == settings
    assert len(reopened.list_templates()) == 1
    with reopened.connection() as con:
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
