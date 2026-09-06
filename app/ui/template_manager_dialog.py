from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QPushButton, QSplitter, QVBoxLayout, QWidget,
)
from app.config import DEFAULT_TEMPLATE
from app.services.template_service import normalize_newlines
from app.ui.ui_helpers import set_button_role

class TemplateManagerDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Administrar plantillas")
        self.resize(1000, 720)
        root = QVBoxLayout(self)
        info = QLabel(
            "Crea distintas plantillas para categorías o tipos de producto. "
            "Los datos de entrega, pago y contacto se administran en Valores por defecto."
        )
        info.setWordWrap(True)
        root.addWidget(info)
        splitter = QSplitter()
        root.addWidget(splitter,1)
        left = QWidget(); ll = QVBoxLayout(left)
        self.list = QListWidget(); self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.itemSelectionChanged.connect(self.load_selected)
        ll.addWidget(self.list,1)
        row = QHBoxLayout()
        b=QPushButton("Nueva"); b.clicked.connect(self.new_template); row.addWidget(b)
        b=QPushButton("Duplicar"); b.clicked.connect(self.duplicate_template); row.addWidget(b)
        b=QPushButton("Eliminar"); b.clicked.connect(self.delete_template); set_button_role(b, "danger"); row.addWidget(b)
        ll.addLayout(row); splitter.addWidget(left)
        right=QWidget(); rl=QVBoxLayout(right)
        rl.addWidget(QLabel("Nombre:")); self.name=QLineEdit(); rl.addWidget(self.name)
        rl.addWidget(QLabel("Plantilla:")); self.body=QPlainTextEdit(); rl.addWidget(self.body,1)
        help_label=QLabel("Variables: {NOMBRE_PRODUCTO}, {DESCRIPCION}, {PRECIO}, {METODO_ENTREGA}, {FORMA_PAGO}, {CONTACTO}")
        help_label.setWordWrap(True); rl.addWidget(help_label)
        row=QHBoxLayout();
        b=QPushButton("★ Hacer predeterminada"); b.clicked.connect(self.set_default); row.addWidget(b)
        row.addStretch(); b=QPushButton("Guardar cambios"); b.clicked.connect(self.save_current); set_button_role(b, "primary"); row.addWidget(b)
        rl.addLayout(row); splitter.addWidget(right); splitter.setSizes([300,700])
        bottom=QHBoxLayout(); bottom.addStretch(); b=QPushButton("Cerrar"); b.clicked.connect(self.accept); bottom.addWidget(b); root.addLayout(bottom)
        self.refresh()

    def selected_id(self):
        item=self.list.currentItem(); return item.data(Qt.UserRole) if item else None

    def refresh(self, select_id=None):
        templates=self.db.list_templates(); default_id=self.db.get_default_template_id(); self.list.clear()
        for t in templates:
            label=("★ " if t["id"]==default_id else "")+t["name"]
            item=QListWidgetItem(label); item.setData(Qt.UserRole,t["id"]); self.list.addItem(item)
        target=select_id or default_id
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole)==target:
                self.list.setCurrentRow(i); break
        if self.list.currentRow()<0 and self.list.count(): self.list.setCurrentRow(0)

    def load_selected(self):
        tid=self.selected_id(); t=self.db.get_template(tid) if tid else None
        if t:
            self.name.setText(t["name"]); self.body.setPlainText(t["body"])

    def new_template(self):
        base="Nueva plantilla"; existing={t["name"].lower() for t in self.db.list_templates()}; name=base; n=2
        while name.lower() in existing: name=f"{base} {n}"; n+=1
        tid=self.db.create_template(name,DEFAULT_TEMPLATE); self.refresh(tid); self.name.selectAll(); self.name.setFocus()

    def duplicate_template(self):
        tid=self.selected_id(); t=self.db.get_template(tid) if tid else None
        if not t: return
        base=t["name"]+" copia"; existing={x["name"].lower() for x in self.db.list_templates()}; name=base; n=2
        while name.lower() in existing: name=f"{base} {n}"; n+=1
        new_id=self.db.create_template(name,t["body"]); self.refresh(new_id)

    def delete_template(self):
        tid=self.selected_id()
        if not tid: return
        if QMessageBox.question(self,"Eliminar plantilla","¿Eliminar esta plantilla?")!=QMessageBox.Yes: return
        try: self.db.delete_template(tid); self.refresh()
        except Exception as exc: QMessageBox.warning(self,"No se pudo eliminar",str(exc))

    def save_current(self):
        tid=self.selected_id()
        if not tid: return
        try:
            self.db.update_template(tid,self.name.text(),normalize_newlines(self.body.toPlainText())); self.refresh(tid)
        except Exception as exc: QMessageBox.warning(self,"No se pudo guardar",str(exc))

    def set_default(self):
        tid=self.selected_id()
        if tid: self.db.set_default_template_id(tid); self.refresh(tid)
