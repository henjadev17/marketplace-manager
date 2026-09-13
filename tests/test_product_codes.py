from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import threading

import pytest

from app.data.database import Database


def test_deleted_last_code_is_not_reused_after_restart(db, product_data):
    product_id, code = db.create_product(product_data, [])
    assert code == 'PROD-0001'
    db.delete_product(product_id)
    reopened = Database(db.db_path)
    assert reopened.next_product_code() == 'PROD-0002'
    assert reopened.create_product(product_data, [])[1] == 'PROD-0002'


def test_failed_creation_consumes_code(db, product_data, source_photos):
    photo_id, source = source_photos[0]
    source.unlink()
    with pytest.raises(FileNotFoundError):
        db.create_product(product_data, [photo_id])
    assert Database(db.db_path).create_product(product_data, [])[1] == 'PROD-0002'


@pytest.mark.parametrize('entry_type', ['directory', 'file'])
def test_existing_media_entries_are_preserved_and_skipped(db, product_data, isolated_storage, entry_type):
    existing = isolated_storage / 'media' / 'PROD-0001'
    if entry_type == 'directory':
        existing.mkdir()
        sentinel = existing / 'keep.jpg'
    else:
        sentinel = existing
    sentinel.write_bytes(b'original content')
    assert db.next_product_code() == 'PROD-0002'
    assert db.create_product(product_data, [])[1] == 'PROD-0002'
    assert sentinel.read_bytes() == b'original content'


def test_preview_does_not_consume_a_number(db, product_data):
    assert [db.next_product_code() for _ in range(3)] == ['PROD-0001'] * 3
    assert db.create_product(product_data, [])[1] == 'PROD-0001'


def test_folder_created_after_reservation_is_preserved(db, product_data, isolated_storage, monkeypatch):
    mkdir = Path.mkdir
    occupied = isolated_storage / 'media' / 'PROD-0001'

    def racing_mkdir(path, *args, **kwargs):
        if path == occupied:
            mkdir(path)
            (path / 'keep.jpg').write_bytes(b'keep')
        return mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'mkdir', racing_mkdir)
    assert db.create_product(product_data, [])[1] == 'PROD-0002'
    assert (occupied / 'keep.jpg').read_bytes() == b'keep'


def test_migration_reserves_history_before_existing_product_is_deleted(db, product_data):
    with db.connection() as con:
        con.execute('DROP TABLE product_code_sequence')
        con.execute("INSERT INTO products(code, title) VALUES ('PROD-9999', 'Existing')")
    reopened = Database(db.db_path)
    with reopened.connection() as con:
        con.execute('DELETE FROM products')
    assert Database(db.db_path).create_product(product_data, [])[1] == 'PROD-10000'


def test_migration_starts_after_existing_highest_code(db, product_data):
    with db.connection() as con:
        con.execute("INSERT INTO products(code, title) VALUES ('PROD-0042', 'Existing')")
    reopened = Database(db.db_path)
    assert reopened.create_product(product_data, [])[1] == 'PROD-0043'
    with reopened.connection() as con:
        assert con.execute("SELECT title FROM products WHERE code = 'PROD-0042'").fetchone()[0] == 'Existing'


def test_concurrent_creation_uses_separate_folders(db, product_data, source_photos, monkeypatch):
    photo_id, source = source_photos[0]
    barrier = threading.Barrier(2)
    copy = shutil.copy2
    def simultaneous_copy(src, dst, *args, **kwargs):
        barrier.wait(timeout=10)
        return copy(src, dst, *args, **kwargs)
    monkeypatch.setattr(shutil, 'copy2', simultaneous_copy)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(db.create_product, product_data, [photo_id]) for _ in range(2)]
        created = [future.result(timeout=15) for future in futures]
    assert {code for _, code in created} == {'PROD-0001', 'PROD-0002'}
    for product_id, code in created:
        copied = Path(db.get_product(product_id)['photos'][0]['copied_path'])
        assert copied.parent.name == code
        assert copied.read_bytes() == source.read_bytes()
