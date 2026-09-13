import logging
import os
import shutil
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.config import (
    DB_PATH,
    DEFAULT_TEMPLATE,
    IMAGE_EXTENSIONS,
    MEDIA_DIR,
    ensure_app_dirs,
)
from app.services.photo_storage import (
    PhotoRecoveryError, PhotoStorage, is_managed_source, validate_original,
)

logger = logging.getLogger(__name__)

SCHEMA = '''
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    file_size INTEGER NOT NULL DEFAULT 0,
    modified_ts REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    price REAL NOT NULL DEFAULT 0,
    description TEXT NOT NULL DEFAULT '',
    final_description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'DRAFT',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS product_photos (
    product_id INTEGER NOT NULL,
    photo_id INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 1,
    copied_path TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (product_id, photo_id),
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    FOREIGN KEY (photo_id) REFERENCES photos(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_photos_filename ON photos(filename);
CREATE INDEX IF NOT EXISTS idx_product_photos_photo ON product_photos(photo_id);

CREATE TABLE IF NOT EXISTS photo_file_commits (
    operation_id TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS product_code_sequence (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    next_value INTEGER NOT NULL CHECK (next_value > 0)
);
'''


class Database:
    def __init__(self, db_path: Path = DB_PATH):
        ensure_app_dirs()
        self.db_path = db_path
        with self.connection() as con:
            con.executescript(SCHEMA)
            self._migrate(con)
        self._recover_photo_operations()
        self._ensure_default_settings()

    @contextmanager
    def connection(self):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def _migrate(self, con):
        con.execute('''
            INSERT OR IGNORE INTO product_code_sequence(id, next_value)
            SELECT 1, COALESCE(MAX(CAST(SUBSTR(code, 6) AS INTEGER)), 0) + 1
            FROM products WHERE code LIKE 'PROD-%'
        ''')
        product_columns = {
            row["name"]
            for row in con.execute("PRAGMA table_info(products)").fetchall()
        }
        if "final_description" not in product_columns:
            con.execute(
                "ALTER TABLE products "
                "ADD COLUMN final_description TEXT NOT NULL DEFAULT ''"
            )
        if "template_id" not in product_columns:
            con.execute(
                "ALTER TABLE products "
                "ADD COLUMN template_id INTEGER"
            )

        pp_columns = {
            row["name"]
            for row in con.execute("PRAGMA table_info(product_photos)").fetchall()
        }
        if "copied_path" not in pp_columns:
            con.execute(
                "ALTER TABLE product_photos "
                "ADD COLUMN copied_path TEXT NOT NULL DEFAULT ''"
            )

    def _ensure_default_settings(self):
        defaults = {
            "description_template": DEFAULT_TEMPLATE,
            "delivery_method": "",
            "payment_method": "",
            "contact_number": "",
            "default_location": "",
            "default_category": "",
            "default_status": "DRAFT",
            # Legacy values seed missing settings only. An existing empty value
            # is intentional and must survive subsequent application starts.
            "default_delivery_method": self.get_setting("delivery_method", ""),
            "default_payment_method": self.get_setting("payment_method", ""),
            "default_contact_number": self.get_setting("contact_number", ""),
            "default_template_id": "",
            "last_template_id": "",
        }
        for key, value in defaults.items():
            if self.get_setting(key) is None:
                self.set_setting(key, value)

        if not self.list_templates():
            template_id = self.create_template(
                "General",
                self.get_setting("description_template", DEFAULT_TEMPLATE),
            )
            self.set_setting("default_template_id", template_id)
            self.set_setting("last_template_id", template_id)

    def get_setting(self, key, default=None):
        with self.connection() as con:
            row = con.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else default

    def set_setting(self, key, value):
        with self.connection() as con:
            con.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )

    def list_templates(self):
        with self.connection() as con:
            rows = con.execute(
                "SELECT * FROM templates ORDER BY name COLLATE NOCASE"
            ).fetchall()
            return [dict(row) for row in rows]

    def get_template(self, template_id):
        if not template_id:
            return None
        with self.connection() as con:
            row = con.execute(
                "SELECT * FROM templates WHERE id = ?",
                (int(template_id),),
            ).fetchone()
            return dict(row) if row else None

    def create_template(self, name, body):
        name = name.strip()
        if not name:
            raise ValueError("El nombre de la plantilla es obligatorio.")
        with self.connection() as con:
            cur = con.execute(
                "INSERT INTO templates(name, body) VALUES(?, ?)",
                (name, body),
            )
            return int(cur.lastrowid)

    def update_template(self, template_id, name, body):
        name = name.strip()
        if not name:
            raise ValueError("El nombre de la plantilla es obligatorio.")
        with self.connection() as con:
            con.execute(
                """
                UPDATE templates
                SET name = ?, body = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (name, body, int(template_id)),
            )

    def delete_template(self, template_id):
        template_id = int(template_id)
        with self.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            templates = con.execute(
                "SELECT id FROM templates ORDER BY name COLLATE NOCASE"
            ).fetchall()
            if template_id not in {row['id'] for row in templates}:
                return
            if len(templates) <= 1:
                raise ValueError("Debe existir al menos una plantilla.")
            fallback = next(row['id'] for row in templates if row['id'] != template_id)
            con.execute(
                "UPDATE products SET template_id = NULL WHERE template_id = ?",
                (template_id,),
            )
            con.execute("DELETE FROM templates WHERE id = ?", (template_id,))
            for key in ('default_template_id', 'last_template_id'):
                row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
                try:
                    references_deleted = row is not None and int(row['value']) == template_id
                except (TypeError, ValueError):
                    references_deleted = False
                if references_deleted:
                    con.execute("UPDATE settings SET value = ? WHERE key = ?",
                                (str(fallback), key))

    def get_default_template_id(self):
        value = self.get_setting("default_template_id", "")
        try:
            template_id = int(value)
        except (TypeError, ValueError):
            template_id = None
        if template_id and self.get_template(template_id):
            return template_id
        templates = self.list_templates()
        return templates[0]["id"] if templates else None

    def set_default_template_id(self, template_id):
        self.set_setting("default_template_id", int(template_id))

    def get_last_template_id(self):
        value = self.get_setting("last_template_id", "")
        try:
            template_id = int(value)
        except (TypeError, ValueError):
            template_id = None
        if template_id and self.get_template(template_id):
            return template_id
        return self.get_default_template_id()

    def set_last_template_id(self, template_id):
        self.set_setting("last_template_id", int(template_id))

    def get_defaults(self):
        return {
            "category": self.get_setting("default_category", ""),
            "location": self.get_setting("default_location", ""),
            "status": self.get_setting("default_status", "DRAFT"),
            "delivery_method": self.get_setting("default_delivery_method", ""),
            "payment_method": self.get_setting("default_payment_method", ""),
            "contact_number": self.get_setting("default_contact_number", ""),
        }

    def save_defaults(self, data):
        self.set_setting("default_category", data.get("category", ""))
        self.set_setting("default_location", data.get("location", ""))
        self.set_setting("default_status", data.get("status", "DRAFT"))
        self.set_setting("default_delivery_method", data.get("delivery_method", ""))
        self.set_setting("default_payment_method", data.get("payment_method", ""))
        self.set_setting("default_contact_number", data.get("contact_number", ""))

    def get_template_settings(self, template_id=None):
        if not template_id:
            template_id = self.get_last_template_id()
        template = self.get_template(template_id)
        if not template:
            template = {"id": None, "name": "General", "body": DEFAULT_TEMPLATE}
        defaults = self.get_defaults()
        return {
            "template_id": template.get("id"),
            "template_name": template.get("name", "General"),
            "template": template.get("body", DEFAULT_TEMPLATE),
            "delivery_method": defaults["delivery_method"],
            "payment_method": defaults["payment_method"],
            "contact_number": defaults["contact_number"],
        }

    def scan_folder(self, folder: Path, recursive=False):
        validate_original(folder, MEDIA_DIR)
        iterator = folder.rglob("*") if recursive else folder.iterdir()
        seen = 0
        with self.connection() as con:
            for path in iterator:
                if is_managed_source(path, MEDIA_DIR):
                    continue
                if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                seen += 1
                try:
                    stat = path.stat()
                except OSError:
                    continue
                con.execute(
                    '''
                    INSERT INTO photos(original_path, filename, file_size, modified_ts)
                    VALUES(?, ?, ?, ?)
                    ON CONFLICT(original_path) DO UPDATE SET
                        filename = excluded.filename,
                        file_size = excluded.file_size,
                        modified_ts = excluded.modified_ts
                    ''',
                    (str(path.resolve()), path.name, stat.st_size, stat.st_mtime),
                )
        return seen

    def list_photos(self, folder: Path, usage_filter="PENDING", search="", recursive=False):
        folder = folder.resolve()
        search_like = f"%{search.strip()}%"
        with self.connection() as con:
            rows = con.execute(
                '''
                SELECT p.*,
                    EXISTS(
                        SELECT 1 FROM product_photos pp WHERE pp.photo_id = p.id
                    ) AS is_used
                FROM photos p
                WHERE p.filename LIKE ?
                ORDER BY p.filename COLLATE NOCASE
                ''',
                (search_like,),
            ).fetchall()

        result = []
        for row in rows:
            path = Path(row["original_path"])
            if recursive:
                try:
                    path.relative_to(folder)
                except ValueError:
                    continue
            else:
                if path.parent != folder:
                    continue

            used = bool(row["is_used"])
            if usage_filter == "PENDING" and used:
                continue
            if usage_filter == "USED" and not used:
                continue
            result.append(dict(row))
        return result

    def next_product_code(self):
        """Preview the next available code without reserving it."""
        with self.connection() as con:
            return f"PROD-{self._next_product_number(con):04d}"

    def _next_product_number(self, con):
        row = con.execute('''
            SELECT MAX(
                (SELECT next_value FROM product_code_sequence WHERE id = 1),
                COALESCE(MAX(CAST(SUBSTR(code, 6) AS INTEGER)), 0) + 1
            ) AS n FROM products WHERE code LIKE 'PROD-%'
        ''').fetchone()
        number = int(row['n'])
        while os.path.lexists(MEDIA_DIR / f"PROD-{number:04d}"):
            number += 1
        return number

    def _reserve_product_code(self):
        # Commit the reservation before filesystem work; failed creates leave gaps.
        with self.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            number = self._next_product_number(con)
            con.execute(
                "UPDATE product_code_sequence SET next_value = ? WHERE id = 1",
                (number + 1,),
            )
        return f"PROD-{number:04d}"

    def _photo_rows_by_ids(self, con, photo_ids):
        placeholders = ",".join("?" for _ in photo_ids)
        rows = con.execute(
            f"SELECT * FROM photos WHERE id IN ({placeholders})",
            tuple(photo_ids),
        ).fetchall()
        by_id = {row["id"]: row for row in rows}
        return [by_id[photo_id] for photo_id in photo_ids if photo_id in by_id]

    def create_product(self, data, photo_ids):
        # Validate even legacy photo records before creating any managed files.
        with self.connection() as con:
            for photo in self._photo_rows_by_ids(con, photo_ids):
                validate_original(photo["original_path"], MEDIA_DIR)
        while True:
            code = self._reserve_product_code()
            product_dir = MEDIA_DIR / code
            try:
                product_dir.mkdir(parents=True, exist_ok=False)
            except FileExistsError:
                # Another process may have created the folder after reservation.
                continue
            break
        copied_files = []

        try:
            with self.connection() as con:
                photo_rows = self._photo_rows_by_ids(con, photo_ids)
                if len(photo_rows) != len(photo_ids):
                    raise RuntimeError("No se encontraron todas las fotos seleccionadas.")

                for position, row in enumerate(photo_rows, start=1):
                    source = Path(row["original_path"])
                    if not source.exists():
                        raise FileNotFoundError(f"No existe la imagen original:\n{source}")

                    ext = source.suffix.lower() or ".jpg"
                    destination = product_dir / f"{code}-{position:02d}{ext}"
                    shutil.copy2(source, destination)
                    copied_files.append(destination)

                cur = con.execute(
                    '''
                    INSERT INTO products(
                        code, title, price, description, final_description,
                        category, location, status, template_id
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        code,
                        data["title"],
                        data["price"],
                        data.get("description", ""),
                        data.get("final_description", ""),
                        data.get("category", ""),
                        data.get("location", ""),
                        data.get("status", "DRAFT"),
                        data.get("template_id"),
                    ),
                )
                product_id = cur.lastrowid

                for position, (row, copied_path) in enumerate(
                    zip(photo_rows, copied_files), start=1
                ):
                    con.execute(
                        '''
                        INSERT INTO product_photos(
                            product_id, photo_id, position, copied_path
                        )
                        VALUES(?, ?, ?, ?)
                        ''',
                        (
                            product_id,
                            row["id"],
                            position,
                            str(copied_path.resolve()),
                        ),
                    )

            return product_id, code

        except Exception:
            if product_dir.exists():
                shutil.rmtree(product_dir, ignore_errors=True)
            raise

    def register_photo_file(self, path: Path):
        path = Path(path).resolve()
        validate_original(path, MEDIA_DIR)

        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"No existe la imagen:\n{path}")

        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError(f"Formato no soportado: {path.suffix}")

        stat = path.stat()

        with self.connection() as con:
            con.execute(
                """
                INSERT INTO photos(original_path, filename, file_size, modified_ts)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(original_path) DO UPDATE SET
                    filename = excluded.filename,
                    file_size = excluded.file_size,
                    modified_ts = excluded.modified_ts
                """,
                (
                    str(path),
                    path.name,
                    stat.st_size,
                    stat.st_mtime,
                ),
            )

            row = con.execute(
                "SELECT id FROM photos WHERE original_path = ?",
                (str(path),),
            ).fetchone()

            return int(row["id"])

    def _recover_photo_operations(self):
        with self.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            PhotoStorage(MEDIA_DIR, self.db_path).recover(con)

    def sync_product_photos(self, product_id, ordered_photo_ids, rotations=None):
        """Save ordered photo copies, retaining the previous folder until commit."""
        if not ordered_photo_ids:
            raise ValueError("El producto debe conservar al menos una foto.")
        if len(set(ordered_photo_ids)) != len(ordered_photo_ids):
            raise ValueError("Una foto no puede repetirse en el mismo producto.")
        rotations = dict(rotations or {})
        if any(photo_id not in ordered_photo_ids or type(degrees) is not int or degrees % 90
               for photo_id, degrees in rotations.items()):
            raise ValueError("Los giros deben ser múltiplos de 90° para las fotos seleccionadas.")

        storage = PhotoStorage(MEDIA_DIR, self.db_path)
        try:
            with self.connection() as con:
                con.execute("BEGIN IMMEDIATE")
                storage.recover(con)
                product = con.execute("SELECT code FROM products WHERE id = ?",
                                      (product_id,)).fetchone()
                if not product:
                    raise ValueError("El producto no existe.")
                code = product["code"]
                final = storage.product_folder(code)
                old = {row["photo_id"]: row["copied_path"] for row in con.execute(
                    "SELECT photo_id, copied_path FROM product_photos WHERE product_id = ?",
                    (product_id,),
                )}
                rows = self._photo_rows_by_ids(con, ordered_photo_ids)
                if len(rows) != len(ordered_photo_ids):
                    raise ValueError("No se encontraron todas las fotos seleccionadas.")
                sources = []
                for row in rows:
                    source = Path(row["original_path"])
                    previous = old.get(row["id"])
                    if previous:
                        saved = Path(previous).resolve()
                        if saved.parent != final.resolve():
                            raise PhotoRecoveryError('La copia guardada no pertenece a este producto.')
                        # Keep saved edits when reordering or rotating again.
                        if saved.is_file():
                            sources.append((row['id'], saved))
                            continue
                    validate_original(source, MEDIA_DIR)
                    if not source.is_file():
                        raise FileNotFoundError(f"No existe la imagen original: {source}")
                    sources.append((row["id"], source))
                operation, staged = storage.prepare(code, sources, rotations=rotations)
                storage.install(operation, code)
                con.execute("DELETE FROM product_photos WHERE product_id = ?", (product_id,))
                for position, (photo_id, filename) in enumerate(staged, 1):
                    con.execute(
                        "INSERT INTO product_photos(product_id, photo_id, position, copied_path) "
                        "VALUES (?, ?, ?, ?)",
                        (product_id, photo_id, position, str((final / filename).resolve())),
                    )
                con.execute("INSERT INTO photo_file_commits(operation_id) VALUES (?)",
                            (operation.name,))
            # connection() has committed before cleanup. Recovery consults the
            # durable marker, including when commit outcome is uncertain.
        except Exception:
            try:
                self._recover_photo_operations()
            except Exception as recovery_error:
                raise PhotoRecoveryError(
                    "No se pudo restaurar la operación de fotos. Conserva las carpetas "
                    "de recuperación y vuelve a abrir la aplicación cuando los archivos "
                    "estén disponibles. " + str(recovery_error)
                ) from recovery_error
            raise

        try:
            self._recover_photo_operations()
        except (OSError, PhotoRecoveryError, sqlite3.Error):
            # The save is committed: never report it as rolled back or destroy
            # its recovery evidence just because backup cleanup is blocked.
            logger.exception("Fotos guardadas; limpieza de respaldo pendiente")
        return [str((final / filename).resolve()) for _, filename in staged]

    def update_product_status(self, product_id, status):
        allowed = {
            "DRAFT",
            "READY",
            "PUBLISHED",
            "SOLD",
            "ARCHIVED",
        }

        if status not in allowed:
            raise ValueError("Estado no válido.")

        with self.connection() as con:
            con.execute(
                """
                UPDATE products
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, product_id),
            )

    def list_products(self):
        with self.connection() as con:
            rows = con.execute(
                '''
                SELECT pr.*, COUNT(pp.photo_id) AS photo_count
                FROM products pr
                LEFT JOIN product_photos pp ON pp.product_id = pr.id
                GROUP BY pr.id
                ORDER BY pr.id DESC
                '''
            ).fetchall()
            return [dict(r) for r in rows]

    def get_product(self, product_id):
        with self.connection() as con:
            product = con.execute(
                "SELECT * FROM products WHERE id = ?", (product_id,)
            ).fetchone()
            if not product:
                return None
            photos = con.execute(
                '''
                SELECT p.*, pp.position, pp.copied_path
                FROM photos p
                JOIN product_photos pp ON pp.photo_id = p.id
                WHERE pp.product_id = ?
                ORDER BY pp.position
                ''',
                (product_id,),
            ).fetchall()
            return {
                "product": dict(product),
                "photos": [dict(r) for r in photos],
            }

    def update_product(self, product_id, data):
        with self.connection() as con:
            con.execute(
                '''
                UPDATE products SET
                    title = ?, price = ?, description = ?, final_description = ?,
                    category = ?, location = ?, status = ?, template_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                ''',
                (
                    data["title"],
                    data["price"],
                    data.get("description", ""),
                    data.get("final_description", ""),
                    data.get("category", ""),
                    data.get("location", ""),
                    data.get("status", "DRAFT"),
                    data.get("template_id"),
                    product_id,
                ),
            )

    def delete_product(self, product_id):
        with self.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            storage = PhotoStorage(MEDIA_DIR, self.db_path)
            storage.recover(con)
            product = con.execute("SELECT code FROM products WHERE id = ?", (product_id,)).fetchone()
            if not product:
                return
            product_dir = storage.product_folder(product["code"])
            con.execute("DELETE FROM products WHERE id = ?", (product_id,))
        if product_dir.exists():
            shutil.rmtree(product_dir, ignore_errors=True)

    def export_rows(self):
        result = []
        for product in reversed(self.list_products()):
            full = self.get_product(product["id"])
            row = dict(product)
            row["photos"] = [
                p["copied_path"] or p["original_path"]
                for p in full["photos"]
            ]
            result.append(row)
        return result
