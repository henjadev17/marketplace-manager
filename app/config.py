from pathlib import Path

APP_DATA = Path.home() / "Documents" / "MarketplaceManager"
DB_PATH = APP_DATA / "marketplace.db"
MEDIA_DIR = APP_DATA / "media"
THUMBNAIL_DIR = APP_DATA / "cache" / "thumbnails"
EXPORT_DIR = APP_DATA / "exports"

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
