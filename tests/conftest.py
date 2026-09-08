"""Isolate home before test collection; give every test its own storage."""
from pathlib import Path
import tempfile

import pytest


def pytest_sessionstart(session):
    # app.config binds paths at import time, as does Database's default argument.
    session._test_home = tempfile.TemporaryDirectory(prefix="marketplace-tests-")
    session._home_patch = pytest.MonkeyPatch()
    home = Path(session._test_home.name)
    session._home_patch.setattr(Path, "home", classmethod(lambda cls: home))
    session._home_patch.setenv("USERPROFILE", str(home))
    session._home_patch.setenv("HOME", str(home))


def pytest_sessionfinish(session, exitstatus):
    session._home_patch.undo()
    session._test_home.cleanup()


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    from app import config
    from app.data import database

    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    root = home / "Documents" / "MarketplaceManager"
    paths = {
        "APP_DATA": root,
        "DB_PATH": root / "marketplace.db",
        "MEDIA_DIR": root / "media",
        "THUMBNAIL_DIR": root / "cache" / "thumbnails",
        "EXPORT_DIR": root / "exports",
    }
    for name, path in paths.items():
        monkeypatch.setattr(config, name, path)
    monkeypatch.setattr(database, "DB_PATH", paths["DB_PATH"])
    monkeypatch.setattr(database, "MEDIA_DIR", paths["MEDIA_DIR"])
    monkeypatch.setattr(database.Database.__init__, "__defaults__", (paths["DB_PATH"],))
    return root


@pytest.fixture
def db(isolated_storage):
    from app.data.database import Database
    return Database()


@pytest.fixture
def source_photos(tmp_path, db):
    from PIL import Image

    folder = tmp_path / "originals"
    folder.mkdir()
    paths = []
    for name, color in [("camera.JPG", "red"), ("detail.png", "blue"), ("side.jpg", "green")]:
        path = folder / name
        Image.new("RGB", (12, 8), color).save(path)
        paths.append(path)
    return [(db.register_photo_file(path), path) for path in paths]


@pytest.fixture
def product_data():
    return {"title": "Monitor", "price": 125.5, "description": "Line one\nLine two"}
