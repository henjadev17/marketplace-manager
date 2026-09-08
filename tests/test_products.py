from pathlib import Path

import pytest


def test_product_codes_are_sequential_and_persisted(db, product_data):
    for expected in ("PROD-0001", "PROD-0002"):
        product_id, code = db.create_product(product_data, [])
        assert code == expected
        assert db.get_product(product_id)["product"]["code"] == expected


def test_creation_stores_template_and_final_description(db, product_data):
    template_id = db.create_template("Sale", "{NOMBRE_PRODUCTO}\n\n{DESCRIPCION}")
    data = dict(product_data, template_id=template_id, final_description="Monitor\n\nLine one\nLine two")
    product_id, _ = db.create_product(data, [])
    stored = db.get_product(product_id)["product"]
    for key, value in data.items():
        assert stored[key] == value


def test_images_are_copied_and_renamed(db, product_data, source_photos, isolated_storage):
    product_id, code = db.create_product(product_data, [p[0] for p in source_photos])
    photos = db.get_product(product_id)["photos"]
    for position, (photo, (photo_id, original)) in enumerate(zip(photos, source_photos), 1):
        copied = Path(photo["copied_path"])
        assert photo["id"] == photo_id
        assert photo["position"] == position
        assert copied == isolated_storage / "media" / code / f"{code}-{position:02d}{original.suffix.lower()}"
        assert copied != original
        assert copied.read_bytes() == original.read_bytes()


@pytest.mark.parametrize("missing_originals", [False, True])
def test_reorder_updates_positions_names_and_content(db, product_data, source_photos, missing_originals):
    ids = [p[0] for p in source_photos]
    expected = {photo_id: path.read_bytes() for photo_id, path in source_photos}
    product_id, code = db.create_product(product_data, ids)
    if missing_originals:
        for _, path in source_photos:
            path.unlink()  # Only synthetic test originals.
    ordered = [ids[2], ids[0], ids[1]]
    returned = db.sync_product_photos(product_id, ordered)
    photos = db.get_product(product_id)["photos"]
    assert [p["id"] for p in photos] == ordered
    assert [p["position"] for p in photos] == [1, 2, 3]
    assert returned == [p["copied_path"] for p in photos]
    for position, photo in enumerate(photos, 1):
        path = Path(photo["copied_path"])
        assert path.stem == f"{code}-{position:02d}"
        assert path.read_bytes() == expected[photo["id"]]
    assert len(list(Path(returned[0]).parent.iterdir())) == 3


def test_delete_preserves_originals_and_other_product_copies(db, product_data, source_photos, isolated_storage):
    ids = [p[0] for p in source_photos]
    originals = {path: path.read_bytes() for _, path in source_photos}
    product_id, code = db.create_product(product_data, ids)
    other_id, _ = db.create_product(product_data, ids)
    other_copies = {Path(p["copied_path"]): Path(p["copied_path"]).read_bytes()
                    for p in db.get_product(other_id)["photos"]}
    db.delete_product(product_id)
    db.delete_product(product_id)  # Repeated deletion is harmless.
    assert db.get_product(product_id) is None
    assert not (isolated_storage / "media" / code).exists()
    for path, content in {**originals, **other_copies}.items():
        assert path.read_bytes() == content
    with db.connection() as con:
        assert con.execute("SELECT COUNT(*) FROM photos").fetchone()[0] == 3
        assert con.execute("SELECT COUNT(*) FROM product_photos WHERE product_id = ?", (product_id,)).fetchone()[0] == 0


def test_failed_creation_removes_partial_copies_only(db, product_data, source_photos, isolated_storage):
    source_photos[-1][1].unlink()
    with pytest.raises(FileNotFoundError):
        db.create_product(product_data, [p[0] for p in source_photos])
    assert db.list_products() == []
    assert list((isolated_storage / "media").iterdir()) == []
    assert all(path.exists() for _, path in source_photos[:-1])
