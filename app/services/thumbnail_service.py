import hashlib
from pathlib import Path
from PIL import Image, ImageOps
from PySide6.QtCore import QObject, QRunnable, Signal
from app.config import THUMBNAIL_DIR

THUMB_SIZE = (180, 180)

def thumbnail_cache_path(source: Path):
    try:
        stat = source.stat()
        seed = f"{source.resolve()}|{stat.st_mtime_ns}|{stat.st_size}"
    except OSError:
        seed = str(source)
    digest = hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()
    return THUMBNAIL_DIR / f"{digest}.jpg"

def build_thumbnail(source: Path):
    dest = thumbnail_cache_path(source)
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", THUMB_SIZE, "white")
        x = (THUMB_SIZE[0] - img.width) // 2
        y = (THUMB_SIZE[1] - img.height) // 2
        canvas.paste(img, (x, y))
        canvas.save(dest, "JPEG", quality=82, optimize=True)
    return dest

class ThumbnailSignals(QObject):
    ready = Signal(str, str)

class ThumbnailTask(QRunnable):
    def __init__(self, source_path):
        super().__init__()
        self.source_path = Path(source_path)
        self.signals = ThumbnailSignals()

    def run(self):
        try:
            dest = build_thumbnail(self.source_path)
            self.signals.ready.emit(str(self.source_path), str(dest))
        except Exception:
            pass
