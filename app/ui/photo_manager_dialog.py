import os
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.config import IMAGE_EXTENSIONS, MEDIA_DIR
from app.services.thumbnail_service import build_thumbnail
from app.ui.preview_dialog import ImagePreviewDialog
from app.ui.ui_helpers import set_button_role

ROLE_PHOTO_ID = Qt.UserRole
ROLE_SOURCE_PATH = Qt.UserRole + 1


class ProductPhotosDialog(QDialog):
    def __init__(self, db, product_id, parent=None):
        super().__init__(parent)

        self.db = db
        self.product_id = product_id

        full = self.db.get_product(product_id)
        if not full:
            raise ValueError("Producto no encontrado.")

        self.product = full["product"]

        self.setWindowTitle(
            f'Fotos — {self.product["code"]} — {self.product["title"]}'
        )
        self.resize(950, 700)

        layout = QVBoxLayout(self)

        info = QLabel(
            "La primera imagen es la principal. "
            "Arrastra las miniaturas para reordenar, o usa Subir/Bajar. "
            "Doble clic para ampliar."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        folder_row = QHBoxLayout()
        open_folder_btn = QPushButton("📂 Abrir carpeta de fotos")
        open_folder_btn.setToolTip("Abrir las fotos guardadas del producto en el Explorador de Windows")
        open_folder_btn.clicked.connect(self.open_photo_folder)
        folder_row.addWidget(open_folder_btn)
        folder_note = QLabel("Si cambias las fotos o su orden, guarda antes de subirlas a Marketplace.")
        folder_note.setWordWrap(True)
        folder_note.setProperty("role", "muted")
        folder_row.addWidget(folder_note, 1)
        layout.addLayout(folder_row)

        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setIconSize(QSize(160, 160))
        self.list.setGridSize(QSize(200, 220))
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Snap)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        self.list.itemDoubleClicked.connect(self.preview_item)

        layout.addWidget(self.list, 1)

        buttons = QHBoxLayout()

        add_btn = QPushButton("➕ Agregar fotos")
        add_btn.clicked.connect(self.add_photos)
        buttons.addWidget(add_btn)

        remove_btn = QPushButton("🗑 Quitar")
        set_button_role(remove_btn, "danger")
        remove_btn.clicked.connect(self.remove_selected)
        buttons.addWidget(remove_btn)

        up_btn = QPushButton("↑ Subir")
        up_btn.clicked.connect(lambda: self.move_current(-1))
        buttons.addWidget(up_btn)

        down_btn = QPushButton("↓ Bajar")
        down_btn.clicked.connect(lambda: self.move_current(1))
        buttons.addWidget(down_btn)

        buttons.addStretch()

        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)

        save_btn = QPushButton("Guardar orden y fotos")
        set_button_role(save_btn, "primary")
        save_btn.clicked.connect(self.save)
        buttons.addWidget(save_btn)

        layout.addLayout(buttons)

        self.load_existing(full["photos"])

    def open_photo_folder(self):
        folder = MEDIA_DIR / self.product["code"]
        if not folder.is_dir():
            QMessageBox.warning(
                self,
                "Carpeta no encontrada",
                f"No se encontró la carpeta de fotos guardadas del producto:\n{folder}",
            )
            return

        try:
            os.startfile(str(folder))
        except OSError as exc:
            QMessageBox.warning(
                self,
                "No se pudo abrir la carpeta",
                f"Abre esta ubicación manualmente:\n{folder}\n\n{exc}",
            )

    def load_existing(self, photos):
        for photo in photos:
            source_path = (
                photo.get("copied_path")
                or photo["original_path"]
            )

            self.add_item(
                int(photo["id"]),
                source_path,
                photo["filename"],
            )

    def add_item(self, photo_id, source_path, label):
        source = Path(source_path)

        item = QListWidgetItem(label)
        item.setData(ROLE_PHOTO_ID, int(photo_id))
        item.setData(ROLE_SOURCE_PATH, str(source))
        item.setToolTip(str(source))

        try:
            thumb_path = build_thumbnail(source)
            pix = QPixmap(str(thumb_path))

            if not pix.isNull():
                item.setIcon(QIcon(pix))
        except Exception:
            pass

        self.list.addItem(item)

    def photo_ids(self):
        return [
            int(self.list.item(i).data(ROLE_PHOTO_ID))
            for i in range(self.list.count())
        ]

    def add_photos(self):
        filter_text = "Imágenes (" + " ".join(
            f"*{ext}" for ext in sorted(IMAGE_EXTENSIONS)
        ) + ")"

        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            "Agregar imágenes",
            str(Path.home()),
            filter_text,
        )

        if not filenames:
            return

        existing = set(self.photo_ids())

        for filename in filenames:
            try:
                photo_id = self.db.register_photo_file(
                    Path(filename)
                )

                if photo_id in existing:
                    continue

                self.add_item(
                    photo_id,
                    filename,
                    Path(filename).name,
                )
                existing.add(photo_id)

            except Exception as exc:
                QMessageBox.warning(
                    self,
                    "No se pudo agregar",
                    str(exc),
                )

    def remove_selected(self):
        selected = list(self.list.selectedItems())

        for item in selected:
            self.list.takeItem(self.list.row(item))

    def move_current(self, direction):
        row = self.list.currentRow()

        if row < 0:
            return

        target = row + direction

        if target < 0 or target >= self.list.count():
            return

        item = self.list.takeItem(row)
        self.list.insertItem(target, item)
        self.list.setCurrentRow(target)

    def preview_item(self, item):
        source = Path(item.data(ROLE_SOURCE_PATH))

        if source.exists():
            ImagePreviewDialog(source, self).exec()

    def save(self):
        ordered_ids = self.photo_ids()

        if not ordered_ids:
            QMessageBox.warning(
                self,
                "Sin fotos",
                "El producto debe conservar al menos una foto.",
            )
            return

        try:
            self.db.sync_product_photos(
                self.product_id,
                ordered_ids,
            )

            QMessageBox.information(
                self,
                "Fotos actualizadas",
                "Las imágenes fueron copiadas y renombradas "
                "de nuevo según el orden actual.",
            )

            self.accept()

        except Exception as exc:
            QMessageBox.critical(
                self,
                "No se pudieron actualizar las fotos",
                str(exc),
            )
