from pathlib import Path
from dataclasses import dataclass

APP_DATA = Path.home() / "Documents" / "MarketplaceManager"
DB_PATH = APP_DATA / "marketplace.db"
MEDIA_DIR = APP_DATA / "media"
THUMBNAIL_DIR = APP_DATA / "cache" / "thumbnails"
EXPORT_DIR = APP_DATA / "exports"


@dataclass(frozen=True)
class DataPaths:
    db_path: Path
    root: Path

    @classmethod
    def for_database(cls, db_path=None):
        path = Path(DB_PATH if db_path is None else db_path).resolve()
        root = path.parent if path.name.lower() == 'marketplace.db' else path.parent / (path.name + '.data')
        return cls(path, root)

    @property
    def media_dir(self):
        return self.root / 'media'

    @property
    def thumbnail_dir(self):
        return self.root / 'cache' / 'thumbnails'

    @property
    def export_dir(self):
        return self.root / 'exports'

    def ensure_directories(self):
        for path in (self.db_path.parent, self.media_dir, self.thumbnail_dir, self.export_dir):
            path.mkdir(parents=True, exist_ok=True)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

DEFAULT_TEMPLATE = """{NOMBRE_PRODUCTO}

{DESCRIPCION}

Precio: {PRECIO}

Método de entrega:
{METODO_ENTREGA}

Forma de pago:
{FORMA_PAGO}

Contacto:
{CONTACTO}"""


def ensure_app_dirs():
    APP_DATA.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
