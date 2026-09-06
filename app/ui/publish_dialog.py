import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.ui.product_dialogs import ProductEditDialog
from app.ui.ui_helpers import configure_table, set_button_role, style_status_item


STATUS_LABELS = {
    "DRAFT": "Borrador",
    "READY": "Listo",
    "PUBLISHED": "Publicado",
    "SOLD": "Vendido",
    "ARCHIVED": "Archivado",
}


class PublishDialog(QDialog):
    """
    Lista operativa para publicar manualmente en Marketplace.

    - Cada fila es un producto.
    - Todas las columnas importantes están visibles.
    - Doble clic en una celda copia ese dato.
    - Los botones inferiores copian el dato completo del producto seleccionado.
    """

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.rows = []
        self.current_full = None

        self.setWindowTitle("Lista para publicar / copiar")
        self.resize(1500, 820)

        root = QVBoxLayout(self)

        title = QLabel("Lista de productos para publicar")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        info = QLabel(
            "Selecciona una fila y usa los botones inferiores. "
            "También puedes hacer doble clic sobre una celda para copiar exactamente ese dato."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        filters = QHBoxLayout()

        filters.addWidget(QLabel("Buscar:"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Código, título, categoría...")
        self.search.textChanged.connect(self.refresh)
        filters.addWidget(self.search, 1)

        filters.addWidget(QLabel("Estado:"))
        self.status_filter = QComboBox()
        self.status_filter.addItem("Todos", "ALL")
        self.status_filter.addItem("Borrador", "DRAFT")
        self.status_filter.addItem("Listo", "READY")
        self.status_filter.addItem("Publicado", "PUBLISHED")
        self.status_filter.addItem("Vendido", "SOLD")
        self.status_filter.addItem("Archivado", "ARCHIVED")
        self.status_filter.currentIndexChanged.connect(self.refresh)
        filters.addWidget(self.status_filter)

        refresh_btn = QPushButton("Actualizar")
        refresh_btn.clicked.connect(self.refresh)
        filters.addWidget(refresh_btn)

        root.addLayout(filters)

        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(
            [
                "Código",
                "Título",
                "Precio",
                "Descripción final",
                "Categoría",
                "Ubicación",
                "Fotos",
                "Estado",
                "Carpeta fotos",
            ]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        configure_table(self.table)
        self.table.setWordWrap(False)
        self.table.itemSelectionChanged.connect(self.load_selected)
        self.table.cellDoubleClicked.connect(self.copy_cell)

        root.addWidget(self.table, 1)

        helper = QLabel(
            "Tip: la columna «Descripción final» se muestra resumida para que la lista sea compacta. "
            "Al copiar se usa el texto completo con todos sus saltos de línea."
        )
        helper.setWordWrap(True)
        helper.setProperty("role", "muted")
        root.addWidget(helper)

        buttons = QHBoxLayout()

        self.copy_title_btn = QPushButton("Copiar título")
        self.copy_title_btn.clicked.connect(lambda: self.copy_field("title"))
        buttons.addWidget(self.copy_title_btn)

        self.copy_price_btn = QPushButton("Copiar precio")
        self.copy_price_btn.clicked.connect(lambda: self.copy_field("price"))
        buttons.addWidget(self.copy_price_btn)

        self.copy_description_btn = QPushButton("Copiar descripción")
        self.copy_description_btn.clicked.connect(
            lambda: self.copy_field("description")
        )
        buttons.addWidget(self.copy_description_btn)

        self.copy_category_btn = QPushButton("Copiar categoría")
        self.copy_category_btn.clicked.connect(lambda: self.copy_field("category"))
        buttons.addWidget(self.copy_category_btn)

        self.copy_location_btn = QPushButton("Copiar ubicación")
        self.copy_location_btn.clicked.connect(lambda: self.copy_field("location"))
        buttons.addWidget(self.copy_location_btn)

        self.copy_photos_btn = QPushButton("Copiar rutas de fotos")
        self.copy_photos_btn.clicked.connect(lambda: self.copy_field("photos"))
        buttons.addWidget(self.copy_photos_btn)

        open_folder_btn = QPushButton("📂 Abrir fotos")
        open_folder_btn.clicked.connect(self.open_photo_folder)
        buttons.addWidget(open_folder_btn)

        edit_btn = QPushButton("✏ Editar")
        edit_btn.clicked.connect(self.edit_current)
        buttons.addWidget(edit_btn)

        ready_btn = QPushButton("✓ Listo")
        set_button_role(ready_btn, "success")
        ready_btn.clicked.connect(
            lambda: self.mark_status("READY")
        )
        buttons.addWidget(ready_btn)

        published_btn = QPushButton("🌐 Publicado")
        set_button_role(published_btn, "primary")
        published_btn.clicked.connect(
            lambda: self.mark_status("PUBLISHED")
        )
        buttons.addWidget(published_btn)

        sold_btn = QPushButton("💰 Vendido")
        set_button_role(sold_btn, "warning")
        sold_btn.clicked.connect(
            lambda: self.mark_status("SOLD")
        )
        buttons.addWidget(sold_btn)

        next_btn = QPushButton("Siguiente →")
        next_btn.clicked.connect(self.select_next)
        buttons.addWidget(next_btn)

        buttons.addStretch()

        copy_all_btn = QPushButton("📋 Copiar todo")
        set_button_role(copy_all_btn, "primary")
        copy_all_btn.clicked.connect(self.copy_all)
        buttons.addWidget(copy_all_btn)

        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)

        root.addLayout(buttons)

        self.feedback = QLabel("")
        self.feedback.setProperty("role", "muted")
        root.addWidget(self.feedback)

        self.refresh()

    def _product_photo_paths(self, product_id):
        full = self.db.get_product(product_id)
        if not full:
            return []
        return [
            photo.get("copied_path") or photo["original_path"]
            for photo in full["photos"]
        ]

    def refresh(self):
        selected_id = self.current_product_id()

        query = self.search.text().strip().lower()
        status = self.status_filter.currentData()

        products = self.db.list_products()

        if query:
            products = [
                product for product in products
                if query in product["code"].lower()
                or query in product["title"].lower()
                or query in product.get("category", "").lower()
                or query in product.get("location", "").lower()
            ]

        if status != "ALL":
            products = [
                product for product in products
                if product.get("status") == status
            ]

        self.rows = products
        self.table.setRowCount(len(products))

        for row_index, product in enumerate(products):
            full = self.db.get_product(product["id"])
            photos = full["photos"] if full else []

            full_description = (
                product.get("final_description")
                or product.get("description", "")
            )
            compact_description = " ".join(full_description.splitlines())
            if len(compact_description) > 100:
                compact_description = compact_description[:97] + "..."

            photo_paths = [
                photo.get("copied_path") or photo["original_path"]
                for photo in photos
            ]
            photo_folder = (
                str(Path(photo_paths[0]).parent)
                if photo_paths
                else ""
            )

            values = [
                product["code"],
                product["title"],
                f'S/ {product["price"]:.2f}',
                compact_description,
                product.get("category", ""),
                product.get("location", ""),
                str(len(photo_paths)),
                STATUS_LABELS.get(product.get("status"), product.get("status", "")),
                photo_folder,
            ]

            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, product["id"])

                if col == 7:
                    style_status_item(item, product.get("status", "DRAFT"))

                # Tooltips preserve full content for long fields.
                if col == 3:
                    item.setToolTip(full_description)
                elif col == 8:
                    item.setToolTip(photo_folder)

                self.table.setItem(row_index, col, item)

        self.table.resizeColumnsToContents()

        # Sensible widths for the work grid.
        widths = {
            0: 100,
            1: 250,
            2: 100,
            3: 380,
            4: 150,
            5: 150,
            6: 70,
            7: 110,
            8: 300,
        }
        for col, width in widths.items():
            self.table.setColumnWidth(col, width)

        if products:
            target_row = 0

            if selected_id:
                for index, product in enumerate(products):
                    if product["id"] == selected_id:
                        target_row = index
                        break

            self.table.selectRow(target_row)
        else:
            self.current_full = None
            self.feedback.setText("No hay productos con esos filtros.")

    def current_product_id(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.rows):
            return None
        return self.rows[row]["id"]

    def load_selected(self):
        product_id = self.current_product_id()
        self.current_full = (
            self.db.get_product(product_id)
            if product_id
            else None
        )

        if self.current_full:
            p = self.current_full["product"]
            self.feedback.setText(
                f'Seleccionado: {p["code"]} — {p["title"]}'
            )

    def _values_for_current(self):
        if not self.current_full:
            return None

        product = self.current_full["product"]
        photos = self.current_full["photos"]

        photo_paths = [
            photo.get("copied_path") or photo["original_path"]
            for photo in photos
        ]

        return {
            "code": product["code"],
            "title": product["title"],
            "price": f'S/ {product["price"]:.2f}',
            "description": (
                product.get("final_description")
                or product.get("description", "")
            ),
            "category": product.get("category", ""),
            "location": product.get("location", ""),
            "photos": "\n".join(photo_paths),
            "status": STATUS_LABELS.get(
                product.get("status"),
                product.get("status", ""),
            ),
            "folder": (
                str(Path(photo_paths[0]).parent)
                if photo_paths
                else ""
            ),
        }

    def copy_text(self, text, label="Dato"):
        QApplication.clipboard().setText(text or "")
        self.feedback.setText(f"✓ {label} copiado al portapapeles.")

    def copy_field(self, field):
        values = self._values_for_current()
        if not values:
            QMessageBox.information(
                self,
                "Sin producto",
                "Selecciona primero un producto de la lista.",
            )
            return

        labels = {
            "title": "Título",
            "price": "Precio",
            "description": "Descripción",
            "category": "Categoría",
            "location": "Ubicación",
            "photos": "Rutas de fotos",
        }
        self.copy_text(values[field], labels[field])

    def copy_cell(self, row, col):
        if row < 0 or row >= len(self.rows):
            return

        product_id = self.rows[row]["id"]
        full = self.db.get_product(product_id)
        if not full:
            return

        product = full["product"]
        photos = full["photos"]
        photo_paths = [
            photo.get("copied_path") or photo["original_path"]
            for photo in photos
        ]

        cell_values = {
            0: product["code"],
            1: product["title"],
            2: f'S/ {product["price"]:.2f}',
            3: (
                product.get("final_description")
                or product.get("description", "")
            ),
            4: product.get("category", ""),
            5: product.get("location", ""),
            6: "\n".join(photo_paths),
            7: STATUS_LABELS.get(
                product.get("status"),
                product.get("status", ""),
            ),
            8: str(Path(photo_paths[0]).parent) if photo_paths else "",
        }

        labels = {
            0: "Código",
            1: "Título",
            2: "Precio",
            3: "Descripción",
            4: "Categoría",
            5: "Ubicación",
            6: "Rutas de fotos",
            7: "Estado",
            8: "Carpeta de fotos",
        }

        self.copy_text(cell_values.get(col, ""), labels.get(col, "Dato"))

    def open_photo_folder(self):
        values = self._values_for_current()
        if not values:
            return

        folder = values["folder"]
        if not folder:
            QMessageBox.information(
                self,
                "Sin fotos",
                "Este producto no tiene una carpeta de fotos disponible.",
            )
            return

        path = Path(folder)
        if not path.exists():
            QMessageBox.warning(
                self,
                "Carpeta no encontrada",
                f"No existe:\n{path}",
            )
            return

        os.startfile(str(path))

    def edit_current(self):
        product_id = self.current_product_id()

        if not product_id:
            return

        dialog = ProductEditDialog(
            self.db,
            product_id,
            self,
        )

        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def mark_status(self, status):
        product_id = self.current_product_id()

        if not product_id:
            QMessageBox.information(
                self,
                "Sin producto",
                "Selecciona primero un producto.",
            )
            return

        row_before = self.table.currentRow()

        self.db.update_product_status(
            product_id,
            status,
        )

        self.refresh()

        # Si el filtro actual eliminó la fila, continuamos desde
        # la posición que ocupaba.
        if self.table.rowCount() > 0:
            target = min(
                max(row_before, 0),
                self.table.rowCount() - 1,
            )
            self.table.selectRow(target)

        label = STATUS_LABELS.get(status, status)
        self.feedback.setText(
            f"✓ Estado actualizado a {label}."
        )

    def select_next(self):
        if self.table.rowCount() == 0:
            return

        current = self.table.currentRow()
        target = current + 1

        if target >= self.table.rowCount():
            target = 0

        self.table.selectRow(target)

        item = self.table.item(target, 0)

        if item:
            self.table.scrollToItem(
                item,
                QAbstractItemView.PositionAtCenter,
            )

    def copy_all(self):
        values = self._values_for_current()
        if not values:
            return

        content = (
            f'Código: {values["code"]}\n'
            f'Título: {values["title"]}\n'
            f'Precio: {values["price"]}\n\n'
            f'Descripción:\n{values["description"]}\n\n'
            f'Categoría: {values["category"]}\n'
            f'Ubicación: {values["location"]}\n'
            f'Estado: {values["status"]}\n\n'
            f'Fotos:\n{values["photos"]}'
        )

        self.copy_text(content, "Todos los datos")
