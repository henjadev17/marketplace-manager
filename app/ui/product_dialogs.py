from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QPlainTextEdit,
    QVBoxLayout,
)

from app.services.template_service import render_template
from app.ui.photo_manager_dialog import ProductPhotosDialog
from app.ui.ui_helpers import configure_table, set_button_role, style_status_item

STATUSES = [
    ("DRAFT", "Borrador"),
    ("READY", "Listo"),
    ("PUBLISHED", "Publicado"),
    ("SOLD", "Vendido"),
    ("ARCHIVED", "Archivado"),
]


class ProductEditDialog(QDialog):
    def __init__(self, db, product_id, parent=None):
        super().__init__(parent)
        self.db = db
        self.product_id = product_id
        self.setWindowTitle("Editar producto")
        self.resize(720, 760)

        full = db.get_product(product_id)
        product = full["product"]

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        form.addRow("Código:", QLabel(product["code"]))

        self.template = QComboBox()
        for template in self.db.list_templates():
            self.template.addItem(template["name"], template["id"])
        selected_template_id = product.get("template_id") or self.db.get_default_template_id()
        self.template.setCurrentIndex(max(self.template.findData(selected_template_id), 0))
        form.addRow("Plantilla:", self.template)

        self.title = QLineEdit(product["title"])
        form.addRow("Título:", self.title)

        self.price = QDoubleSpinBox()
        self.price.setMaximum(99_999_999)
        self.price.setDecimals(2)
        self.price.setPrefix("S/ ")
        self.price.setValue(product["price"])
        form.addRow("Precio:", self.price)

        self.category = QLineEdit(product["category"])
        form.addRow("Categoría:", self.category)

        self.location = QLineEdit(product["location"])
        form.addRow("Ubicación:", self.location)

        self.status = QComboBox()
        for value, label in STATUSES:
            self.status.addItem(label, value)
        self.status.setCurrentIndex(max(self.status.findData(product["status"]), 0))
        form.addRow("Estado:", self.status)

        self.description = QPlainTextEdit()
        self.description.setPlainText(product["description"])
        self.description.setMaximumHeight(150)
        form.addRow("Descripción específica:", self.description)

        self.final_description = QPlainTextEdit()
        self.final_description.setPlainText(product.get("final_description", ""))
        self.final_description.setMinimumHeight(230)
        form.addRow("Descripción final:", self.final_description)

        regenerate = QPushButton("Regenerar usando la plantilla actual")
        regenerate.clicked.connect(self.regenerate)
        form.addRow("", regenerate)

        photo_row = QHBoxLayout()

        self.photo_count_label = QLabel(
            f'{len(full["photos"])} fotos asociadas'
        )
        photo_row.addWidget(self.photo_count_label)

        manage_photos_btn = QPushButton("Administrar fotos")
        manage_photos_btn.clicked.connect(self.manage_photos)
        photo_row.addWidget(manage_photos_btn)

        form.addRow("Fotos:", photo_row)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("Guardar cambios")
        save.clicked.connect(self.save)
        set_button_role(save, "primary")
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def manage_photos(self):
        dialog = ProductPhotosDialog(
            self.db,
            self.product_id,
            self,
        )

        if dialog.exec() == QDialog.Accepted:
            full = self.db.get_product(self.product_id)

            if full:
                self.photo_count_label.setText(
                    f'{len(full["photos"])} fotos asociadas'
                )

    def regenerate(self):
        settings = self.db.get_template_settings(self.template.currentData())
        self.final_description.setPlainText(
            render_template(
                settings["template"],
                self.title.text(),
                self.description.toPlainText(),
                self.price.value(),
                settings["delivery_method"],
                settings["payment_method"],
                settings["contact_number"],
            )
        )

    def save(self):
        if not self.title.text().strip():
            QMessageBox.warning(self, "Falta título", "El título es obligatorio.")
            return

        self.db.update_product(
            self.product_id,
            {
                "title": self.title.text().strip(),
                "price": self.price.value(),
                "category": self.category.text().strip(),
                "location": self.location.text().strip(),
                "status": self.status.currentData(),
                "description": self.description.toPlainText(),
                "final_description": self.final_description.toPlainText(),
                "template_id": self.template.currentData(),
            },
        )
        self.accept()


class ProductsDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Productos")
        self.resize(1000, 620)

        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Código", "Título", "Precio", "Estado", "Fotos", "Actualizado"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        configure_table(self.table)
        self.table.doubleClicked.connect(self.edit_selected)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        edit = QPushButton("Editar")
        edit.clicked.connect(self.edit_selected)
        buttons.addWidget(edit)
        delete = QPushButton("Eliminar")
        delete.clicked.connect(self.delete_selected)
        set_button_role(delete, "danger")
        buttons.addWidget(delete)
        close = QPushButton("Cerrar")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self.refresh()

    def refresh(self):
        rows = self.db.list_products()
        self.table.setRowCount(len(rows))
        self.product_ids = []

        for r, product in enumerate(rows):
            self.product_ids.append(product["id"])
            values = [
                product["code"],
                product["title"],
                f'S/ {product["price"]:.2f}',
                product["status"],
                str(product["photo_count"]),
                product["updated_at"],
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if c == 3:
                    style_status_item(item, product["status"])
                self.table.setItem(r, c, item)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def current_product_id(self):
        row = self.table.currentRow()
        return None if row < 0 else self.product_ids[row]

    def edit_selected(self):
        product_id = self.current_product_id()
        if not product_id:
            return
        dialog = ProductEditDialog(self.db, product_id, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def delete_selected(self):
        product_id = self.current_product_id()
        if not product_id:
            return
        answer = QMessageBox.question(
            self,
            "Eliminar producto",
            "Se eliminará el producto y las COPIAS de sus imágenes gestionadas por la app.\n"
            "Las fotos originales NO se eliminarán.\n\n¿Continuar?",
        )
        if answer == QMessageBox.Yes:
            self.db.delete_product(product_id)
            self.refresh()
