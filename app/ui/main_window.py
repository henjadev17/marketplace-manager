from pathlib import Path

from PySide6.QtCore import Qt, QSize, QThreadPool
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QSplitter, QPlainTextEdit,
    QVBoxLayout, QWidget,
)

from app.config import EXPORT_DIR
from app.data.database import Database
from app.services.export_service import export_products
from app.services.thumbnail_service import ThumbnailTask
from app.services.template_service import render_template
from app.ui.preview_dialog import ImagePreviewDialog
from app.ui.product_dialogs import ProductsDialog, STATUSES
from app.ui.publish_dialog import PublishDialog
from app.ui.template_manager_dialog import TemplateManagerDialog
from app.ui.defaults_dialog import DefaultsDialog
from app.ui.theme import ThemeManager
from app.ui.ui_helpers import set_button_role

ROLE_PHOTO_ID = Qt.UserRole
ROLE_PATH = Qt.UserRole + 1

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Marketplace Manager v0.9.2")
        self.resize(1400, 850)
        self.setMinimumSize(1100, 720)

        self.db = Database()
        self.theme_manager = ThemeManager(QApplication.instance(), self.db)
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(4)
        self.item_by_path = {}

        self.gallery_rows = []
        self.gallery_loaded = 0
        self.gallery_batch_size = 200

        last_folder = self.db.get_setting("last_folder", "")
        self.current_folder = Path(last_folder) if last_folder else None

        self._build_ui()
        self.load_templates()
        self.apply_defaults()

        if self.current_folder and self.current_folder.exists():
            self.folder_label.setText(str(self.current_folder))
            self.scan_and_refresh(scan=False)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 12)
        root.setSpacing(12)

        top_bar = QFrame()
        top_bar.setObjectName("TopBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 12, 16, 12)
        top_layout.setSpacing(8)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)

        title = QLabel("Marketplace Manager")
        title.setObjectName("PageTitle")
        title_box.addWidget(title)

        subtitle = QLabel("Organiza productos, fotos y publicaciones desde un solo lugar")
        subtitle.setObjectName("PageSubtitle")
        title_box.addWidget(subtitle)

        top_layout.addLayout(title_box)
        top_layout.addStretch()

        appearance_label = QLabel("Apariencia")
        appearance_label.setProperty("role", "muted")
        top_layout.addWidget(appearance_label)

        self.appearance_combo = QComboBox()
        self.appearance_combo.addItem("Sistema", "system")
        self.appearance_combo.addItem("Claro", "light")
        self.appearance_combo.addItem("Oscuro", "dark")
        appearance_index = self.appearance_combo.findData(
            self.theme_manager.mode
        )
        self.appearance_combo.setCurrentIndex(max(appearance_index, 0))
        self.appearance_combo.currentIndexChanged.connect(
            self.appearance_changed
        )
        top_layout.addWidget(self.appearance_combo)

        template_btn = QPushButton("📝 Plantillas")
        template_btn.clicked.connect(self.manage_templates)
        set_button_role(template_btn, "ghost")
        top_layout.addWidget(template_btn)

        defaults_btn = QPushButton("⚙ Valores")
        defaults_btn.clicked.connect(self.edit_defaults)
        set_button_role(defaults_btn, "ghost")
        top_layout.addWidget(defaults_btn)

        products_btn = QPushButton("📦 Productos")
        products_btn.clicked.connect(self.show_products)
        set_button_role(products_btn, "ghost")
        top_layout.addWidget(products_btn)

        publish_btn = QPushButton("📋 Publicar / Copiar")
        publish_btn.clicked.connect(self.show_publish)
        set_button_role(publish_btn, "primary")
        top_layout.addWidget(publish_btn)

        export_btn = QPushButton("📊 Exportar XLSX")
        export_btn.clicked.connect(self.export_xlsx)
        top_layout.addWidget(export_btn)

        root.addWidget(top_bar)

        source_card = QFrame()
        source_card.setObjectName("ToolCard")
        source_row = QHBoxLayout(source_card)
        source_row.setContentsMargins(12, 10, 12, 10)
        choose_btn = QPushButton("📁 Elegir carpeta")
        choose_btn.clicked.connect(self.choose_folder)
        source_row.addWidget(choose_btn)

        self.folder_label = QLabel("Ninguna carpeta seleccionada")
        self.folder_label.setObjectName("PathLabel")
        self.folder_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        source_row.addWidget(self.folder_label, 1)

        self.recursive = QCheckBox("Subcarpetas")
        source_row.addWidget(self.recursive)

        scan_btn = QPushButton("🔄 Escanear")
        scan_btn.clicked.connect(lambda: self.scan_and_refresh(scan=True))
        source_row.addWidget(scan_btn)
        root.addWidget(source_card)

        filter_card = QFrame()
        filter_card.setObjectName("ToolCard")
        filters = QHBoxLayout(filter_card)
        filters.setContentsMargins(12, 10, 12, 10)
        filters.addWidget(QLabel("Mostrar:"))

        self.filter_combo = QComboBox()
        self.filter_combo.addItem("Pendientes", "PENDING")
        self.filter_combo.addItem("Todas", "ALL")
        self.filter_combo.addItem("Usadas", "USED")
        self.filter_combo.currentIndexChanged.connect(self.refresh_gallery)
        filters.addWidget(self.filter_combo)

        filters.addWidget(QLabel("Ordenar:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Nombre A-Z", "NAME_ASC")
        self.sort_combo.addItem("Nombre Z-A", "NAME_DESC")
        self.sort_combo.addItem("Más recientes", "NEWEST")
        self.sort_combo.addItem("Más antiguas", "OLDEST")
        self.sort_combo.currentIndexChanged.connect(self.refresh_gallery)
        filters.addWidget(self.sort_combo)

        filters.addWidget(QLabel("Buscar:"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Nombre de archivo...")
        self.search.textChanged.connect(self.refresh_gallery)
        filters.addWidget(self.search, 1)

        select_all = QPushButton("Seleccionar visibles")
        select_all.clicked.connect(self.select_all_visible)
        filters.addWidget(select_all)

        clear_selection = QPushButton("Limpiar selección")
        clear_selection.clicked.connect(self.clear_selection)
        filters.addWidget(clear_selection)
        root.addWidget(filter_card)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        left = QFrame()
        left.setObjectName("GalleryCard")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(10, 10, 10, 10)

        self.photo_list = QListWidget()
        self.photo_list.setViewMode(QListWidget.IconMode)
        self.photo_list.setIconSize(QSize(180, 180))
        self.photo_list.setGridSize(QSize(210, 235))
        self.photo_list.setResizeMode(QListWidget.Adjust)
        self.photo_list.setMovement(QListWidget.Static)
        self.photo_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.photo_list.setSpacing(8)
        self.photo_list.itemSelectionChanged.connect(self.update_selection_label)
        self.photo_list.itemDoubleClicked.connect(self.preview_item)
        self.photo_list.verticalScrollBar().valueChanged.connect(
            self.maybe_load_more
        )
        left_layout.addWidget(self.photo_list, 1)

        self.gallery_label = QLabel("0 imágenes")
        self.gallery_label.setProperty("role", "muted")
        left_layout.addWidget(self.gallery_label)
        splitter.addWidget(left)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QScrollArea.NoFrame)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right_scroll.setMinimumWidth(500)

        right = QFrame()
        right.setObjectName("EditorCard")
        right.setMinimumWidth(480)

        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(12)

        right_scroll.setWidget(right)

        box = QGroupBox("Crear producto con las fotos seleccionadas")
        form = QFormLayout(box)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.code_label = QLabel(self.db.next_product_code())
        self.code_label.setObjectName("CodeBadge")
        form.addRow("Código:", self.code_label)

        self.template_input = QComboBox()
        self.template_input.setMinimumHeight(36)
        self.template_input.currentIndexChanged.connect(self.template_changed)
        form.addRow("Plantilla:", self.template_input)

        self.title_input = QLineEdit()
        self.title_input.setMinimumHeight(36)
        self.title_input.setPlaceholderText("Ej. Monitor Samsung 24 pulgadas")
        form.addRow("Título:", self.title_input)

        self.price_input = QDoubleSpinBox()
        self.price_input.setMinimumHeight(36)
        self.price_input.setMaximum(99_999_999)
        self.price_input.setDecimals(2)
        self.price_input.setPrefix("S/ ")
        form.addRow("Precio:", self.price_input)

        self.category_input = QLineEdit()
        self.category_input.setMinimumHeight(36)
        self.category_input.setPlaceholderText("Ej. Electrónica")
        form.addRow("Categoría:", self.category_input)

        self.location_input = QLineEdit()
        self.location_input.setMinimumHeight(36)
        self.location_input.setPlaceholderText("Ej. Lima")
        form.addRow("Ubicación:", self.location_input)

        self.status_input = QComboBox()
        self.status_input.setMinimumHeight(36)
        for value, label in STATUSES:
            self.status_input.addItem(label, value)
        form.addRow("Estado:", self.status_input)

        self.description_input = QPlainTextEdit()
        self.description_input.setPlaceholderText("Descripción...")
        self.description_input.setMinimumHeight(110)
        self.description_input.setMaximumHeight(160)
        form.addRow("Descripción:", self.description_input)

        self.selected_label = QLabel("0 fotos seleccionadas")
        self.selected_label.setObjectName("InfoBadge")
        self.selected_label.setMinimumHeight(32)
        form.addRow("Fotos:", self.selected_label)
        right_layout.addWidget(box)

        preview_box = QGroupBox("Vista previa de descripción final")
        preview_layout = QVBoxLayout(preview_box)
        self.final_preview = QPlainTextEdit()
        self.final_preview.setReadOnly(True)
        self.final_preview.setMinimumHeight(260)
        preview_layout.addWidget(self.final_preview)
        right_layout.addWidget(preview_box)

        self.title_input.textChanged.connect(self.update_final_preview)
        self.price_input.valueChanged.connect(self.update_final_preview)
        self.description_input.textChanged.connect(self.update_final_preview)
        self.update_final_preview()

        create_btn = QPushButton("✅ Crear producto y copiar fotos")
        create_btn.setMinimumHeight(48)
        create_btn.clicked.connect(self.create_product)
        set_button_role(create_btn, "primary")
        right_layout.addWidget(create_btn)

        reset_btn = QPushButton("Limpiar formulario")
        reset_btn.clicked.connect(self.reset_form)
        set_button_role(reset_btn, "ghost")
        right_layout.addWidget(reset_btn)

        note = QLabel(
            "Al crear el producto, las fotos se COPIAN y renombran dentro de "
            "Documents\\MarketplaceManager\\media\\PROD-XXXX. "
            "Los archivos originales no se modifican."
        )
        note.setWordWrap(True)
        note.setProperty("role", "muted")
        right_layout.addWidget(note)
        right_layout.addStretch()

        splitter.addWidget(right_scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setSizes([900, 540])
        self.statusBar().showMessage("Listo")

    def appearance_changed(self):
        mode = self.appearance_combo.currentData()
        self.theme_manager.apply(mode)

    def load_templates(self, select_id=None):
        templates = self.db.list_templates()
        if select_id is None:
            select_id = self.db.get_last_template_id()
        default_id = self.db.get_default_template_id()
        self.template_input.blockSignals(True)
        self.template_input.clear()
        for template in templates:
            label = template["name"] + (" ★" if template["id"] == default_id else "")
            self.template_input.addItem(label, template["id"])
        index = self.template_input.findData(select_id)
        if index < 0:
            index = self.template_input.findData(default_id)
        self.template_input.setCurrentIndex(max(index, 0))
        self.template_input.blockSignals(False)
        self.update_final_preview()

    def template_changed(self):
        template_id = self.template_input.currentData()
        if template_id:
            self.db.set_last_template_id(template_id)
        self.update_final_preview()

    def manage_templates(self):
        current_id = self.template_input.currentData()
        TemplateManagerDialog(self.db, self).exec()
        self.load_templates(current_id)

    def edit_defaults(self):
        dialog = DefaultsDialog(self.db, self)
        if dialog.exec():
            self.apply_defaults()
            self.update_final_preview()

    def apply_defaults(self):
        defaults = self.db.get_defaults()
        self.category_input.setText(defaults["category"])
        self.location_input.setText(defaults["location"])
        index = self.status_input.findData(defaults["status"])
        self.status_input.setCurrentIndex(max(index, 0))

    def update_final_preview(self):
        settings = self.db.get_template_settings(self.template_input.currentData())
        self.final_preview.setPlainText(
            render_template(
                settings["template"],
                self.title_input.text(),
                self.description_input.toPlainText(),
                self.price_input.value(),
                settings["delivery_method"],
                settings["payment_method"],
                settings["contact_number"],
            )
        )

    def choose_folder(self):
        start = str(self.current_folder or Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de fotos", start)
        if not folder:
            return
        self.current_folder = Path(folder).resolve()
        self.folder_label.setText(str(self.current_folder))
        self.db.set_setting("last_folder", self.current_folder)
        self.scan_and_refresh(scan=True)

    def scan_and_refresh(self, scan=True):
        if not self.current_folder or not self.current_folder.exists():
            QMessageBox.warning(self, "Sin carpeta", "Selecciona primero una carpeta local.")
            return
        if scan:
            self.statusBar().showMessage("Escaneando carpeta...")
            seen = self.db.scan_folder(self.current_folder, recursive=self.recursive.isChecked())
            self.statusBar().showMessage(f"Escaneo completado: {seen} imágenes")
        self.refresh_gallery()

    def refresh_gallery(self):
        if not self.current_folder or not self.current_folder.exists():
            return

        rows = self.db.list_photos(
            self.current_folder,
            usage_filter=self.filter_combo.currentData(),
            search=self.search.text(),
            recursive=self.recursive.isChecked(),
        )

        sort_mode = self.sort_combo.currentData()

        if sort_mode == "NAME_DESC":
            rows.sort(
                key=lambda photo: photo["filename"].lower(),
                reverse=True,
            )
        elif sort_mode == "NEWEST":
            rows.sort(
                key=lambda photo: photo["modified_ts"],
                reverse=True,
            )
        elif sort_mode == "OLDEST":
            rows.sort(
                key=lambda photo: photo["modified_ts"],
            )
        else:
            rows.sort(
                key=lambda photo: photo["filename"].lower(),
            )

        self.gallery_rows = rows
        self.gallery_loaded = 0

        self.photo_list.clear()
        self.item_by_path = {}

        self.append_gallery_batch()
        self.update_selection_label()

    def append_gallery_batch(self):
        if self.gallery_loaded >= len(self.gallery_rows):
            self.gallery_label.setText(
                f"{len(self.gallery_rows)} imágenes cargadas"
            )
            return

        batch_end = min(
            self.gallery_loaded + self.gallery_batch_size,
            len(self.gallery_rows),
        )

        placeholder = QPixmap(180, 180)
        placeholder.fill(Qt.lightGray)
        placeholder_icon = QIcon(placeholder)

        for photo in self.gallery_rows[
            self.gallery_loaded:batch_end
        ]:
            label = (
                ("✓ " if photo["is_used"] else "")
                + photo["filename"]
            )

            item = QListWidgetItem(
                placeholder_icon,
                label,
            )
            item.setData(
                ROLE_PHOTO_ID,
                photo["id"],
            )
            item.setData(
                ROLE_PATH,
                photo["original_path"],
            )
            item.setToolTip(photo["original_path"])

            self.photo_list.addItem(item)
            self.item_by_path[photo["original_path"]] = item

            task = ThumbnailTask(photo["original_path"])
            task.signals.ready.connect(self.thumbnail_ready)
            self.thread_pool.start(task)

        self.gallery_loaded = batch_end

        self.gallery_label.setText(
            f"{self.gallery_loaded} de "
            f"{len(self.gallery_rows)} imágenes cargadas"
        )

    def maybe_load_more(self, value):
        scrollbar = self.photo_list.verticalScrollBar()

        if scrollbar.maximum() <= 0:
            return

        if value >= scrollbar.maximum() - 150:
            self.append_gallery_batch()

    def thumbnail_ready(self, source_path, thumbnail_path):
        item = self.item_by_path.get(source_path)

        if not item:
            return

        pix = QPixmap(thumbnail_path)

        if not pix.isNull():
            item.setIcon(QIcon(pix))

    def update_selection_label(self):
        self.selected_label.setText(f"{len(self.photo_list.selectedItems())} fotos seleccionadas")

    def select_all_visible(self):
        self.photo_list.selectAll()

    def clear_selection(self):
        self.photo_list.clearSelection()

    def preview_item(self, item):
        dialog = ImagePreviewDialog(item.data(ROLE_PATH), self)
        dialog.exec()

    def selected_photo_ids(self):
        selected = sorted(
            self.photo_list.selectedItems(),
            key=lambda item: self.photo_list.row(item),
        )
        return [item.data(ROLE_PHOTO_ID) for item in selected]

    def create_product(self):
        title = self.title_input.text().strip()
        photo_ids = self.selected_photo_ids()

        if not title:
            QMessageBox.warning(self, "Falta título", "Escribe el título del producto.")
            return
        if not photo_ids:
            QMessageBox.warning(self, "Faltan fotos", "Selecciona al menos una foto.")
            return

        try:
            _, code = self.db.create_product(
                {
                "title": title,
                "price": self.price_input.value(),
                "description": self.description_input.toPlainText(),
                "final_description": self.final_preview.toPlainText(),
                "category": self.category_input.text().strip(),
                "location": self.location_input.text().strip(),
                "status": self.status_input.currentData(),
                "template_id": self.template_input.currentData(),
            },
                photo_ids,
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Error al crear producto",
                f"No se pudo crear el producto o copiar sus fotos:\n\n{exc}",
            )
            return

        QMessageBox.information(
            self,
            "Producto creado",
            f"{code} creado con {len(photo_ids)} fotos copiadas y renombradas."
        )
        self.reset_form()
        self.refresh_gallery()

    def reset_form(self):
        self.title_input.clear()
        self.price_input.setValue(0)
        self.description_input.clear()
        self.photo_list.clearSelection()
        self.apply_defaults()
        self.code_label.setText(self.db.next_product_code())
        self.update_final_preview()

    def show_products(self):
        dialog = ProductsDialog(self.db, self)
        dialog.exec()
        self.code_label.setText(self.db.next_product_code())
        self.refresh_gallery()

    def show_publish(self):
        dialog = PublishDialog(self.db, self)
        dialog.exec()

    def export_xlsx(self):
        rows = self.db.export_rows()
        if not rows:
            QMessageBox.information(self, "Sin productos", "Todavía no hay productos para exportar.")
            return

        default = EXPORT_DIR / "marketplace.xlsx"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Guardar Excel", str(default), "Excel (*.xlsx)"
        )
        if not filename:
            return
        if not filename.lower().endswith(".xlsx"):
            filename += ".xlsx"

        output = export_products(rows, Path(filename))
        QMessageBox.information(
            self, "Excel generado",
            f"Excel generado correctamente:\n\n{output}"
        )
