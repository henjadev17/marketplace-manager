from PySide6.QtCore import Qt, QSignalBlocker, QTimer
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
        self._loaded_id = None
        self._saved_content = None
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
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _content(self):
        return self.name.text(), normalize_newlines(self.body.toPlainText())

    def _select(self, template_id):
        with QSignalBlocker(self.list):
            for index in range(self.list.count()):
                if self.list.item(index).data(Qt.UserRole) == template_id:
                    self.list.setCurrentRow(index)
                    return

    def _load(self, template_id):
        template = self.db.get_template(template_id)
        if template:
            self._loaded_id = template_id
            self.name.setText(template['name'])
            self.body.setPlainText(template['body'])
            self._saved_content = self._content()

    def refresh(self, select_id=None):
        # Callers resolve pending edits before rebuilding the list.
        templates = self.db.list_templates()
        default_id = self.db.get_default_template_id()
        target = select_id or default_id
        with QSignalBlocker(self.list):
            self.list.clear()
            for template in templates:
                label = ('★ ' if template['id'] == default_id else '') + template['name']
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, template['id'])
                self.list.addItem(item)
            self._select(target)
            if self.list.currentRow() < 0 and self.list.count():
                self.list.setCurrentRow(0)
        self._load(self.selected_id())

    def _confirm_pending_changes(self):
        if self._loaded_id is None or self._content() == self._saved_content:
            return True
        message = QMessageBox(self)
        message.setWindowTitle('Cambios sin guardar')
        message.setIcon(QMessageBox.Warning)
        message.setText('La plantilla tiene cambios sin guardar. ¿Qué deseas hacer?')
        save = message.addButton('Guardar', QMessageBox.AcceptRole)
        discard = message.addButton('Descartar', QMessageBox.DestructiveRole)
        cancel = message.addButton('Cancelar', QMessageBox.RejectRole)
        message.setDefaultButton(cancel)
        message.setEscapeButton(cancel)
        message.exec()
        if message.clickedButton() == save:
            return self.save_current()
        return message.clickedButton() == discard

    def load_selected(self):
        target = self.selected_id()
        if target is None or target == self._loaded_id:
            return
        # Restore selection before prompting: Save must address the draft's ID,
        # and Cancel must restore the selection as well as retain the text.
        if self._loaded_id is not None:
            self._select(self._loaded_id)
        if self._confirm_pending_changes():
            self._select(target)
            self._load(target)
        # Keyboard navigation may finish updating selection after this signal
        # returns. Reconcile the highlight once that Qt input event has ended.
        QTimer.singleShot(0, self._restore_selection)

    def _restore_selection(self):
        self._select(self._loaded_id)

    def done(self, result):
        # Covers Cerrar, accept(), reject() and Escape.
        if self._confirm_pending_changes():
            super().done(result)

    def closeEvent(self, event):
        if self._confirm_pending_changes():
            super().done(QDialog.Rejected)
            event.accept()
        else:
            event.ignore()

    def new_template(self):
        if not self._confirm_pending_changes():
            return
        base = 'Nueva plantilla'
        existing = {t['name'].lower() for t in self.db.list_templates()}
        name, number = base, 2
        while name.lower() in existing:
            name = f'{base} {number}'
            number += 1
        try:
            template_id = self.db.create_template(name, DEFAULT_TEMPLATE)
        except Exception as exc:
            QMessageBox.warning(self, 'No se pudo crear', str(exc))
            return
        self.refresh(template_id)
        self.name.selectAll()
        self.name.setFocus()

    def duplicate_template(self):
        if not self._confirm_pending_changes():
            return
        template = self.db.get_template(self._loaded_id)
        if not template:
            return
        base = template['name'] + ' copia'
        existing = {t['name'].lower() for t in self.db.list_templates()}
        name, number = base, 2
        while name.lower() in existing:
            name = f'{base} {number}'
            number += 1
        try:
            template_id = self.db.create_template(name, template['body'])
        except Exception as exc:
            QMessageBox.warning(self, 'No se pudo duplicar', str(exc))
            return
        self.refresh(template_id)

    def delete_template(self):
        if not self._loaded_id or not self._confirm_pending_changes():
            return
        if QMessageBox.question(self, 'Eliminar plantilla', '¿Eliminar esta plantilla?') != QMessageBox.Yes:
            return
        try:
            self.db.delete_template(self._loaded_id)
        except Exception as exc:
            QMessageBox.warning(self, 'No se pudo eliminar', str(exc))
            return
        self.refresh()

    def save_current(self):
        if not self._loaded_id:
            return False
        try:
            self.db.update_template(self._loaded_id, *self._content())
        except Exception as exc:
            QMessageBox.warning(self, 'No se pudo guardar', str(exc))
            return False
        self.refresh(self._loaded_id)
        return True

    def set_default(self):
        if not self._loaded_id:
            return
        try:
            self.db.set_default_template_id(self._loaded_id)
        except Exception as exc:
            QMessageBox.warning(self, 'No se pudo cambiar la plantilla predeterminada', str(exc))
            return
        # Update only labels; changing a preference must not reload the editor.
        names = {t['id']: t['name'] for t in self.db.list_templates()}
        for index in range(self.list.count()):
            item = self.list.item(index)
            template_id = item.data(Qt.UserRole)
            item.setText(('★ ' if template_id == self._loaded_id else '') + names[template_id])
