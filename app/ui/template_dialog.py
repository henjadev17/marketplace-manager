from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from app.services.template_service import normalize_newlines


class TemplateDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Plantilla de descripción")
        self.resize(780, 700)

        data = db.get_template_settings()

        layout = QVBoxLayout(self)

        help_label = QLabel(
            "Variables disponibles: {NOMBRE_PRODUCTO}, {DESCRIPCION}, {PRECIO}, "
            "{METODO_ENTREGA}, {FORMA_PAGO}, {CONTACTO}"
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        form = QFormLayout()

        self.template = QPlainTextEdit()
        self.template.setPlainText(data["template"])
        self.template.setMinimumHeight(320)
        form.addRow("Plantilla:", self.template)

        self.delivery = QPlainTextEdit()
        self.delivery.setPlainText(data["delivery_method"])
        self.delivery.setMaximumHeight(95)
        self.delivery.setPlaceholderText("Ej. Entrega en punto acordado / delivery con costo")
        form.addRow("Método de entrega:", self.delivery)

        self.payment = QPlainTextEdit()
        self.payment.setPlainText(data["payment_method"])
        self.payment.setMaximumHeight(95)
        self.payment.setPlaceholderText("Ej. Yape, Plin o efectivo")
        form.addRow("Forma de pago:", self.payment)

        self.contact = QLineEdit(data["contact_number"])
        self.contact.setPlaceholderText("Ej. 999 999 999")
        form.addRow("Número de contacto:", self.contact)

        layout.addLayout(form)

        note = QLabel(
            "Los Enter y las líneas vacías se conservan tal como los escribes. "
            "La plantilla se guarda como texto plano, adecuado para copiar a Facebook."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QHBoxLayout()
        buttons.addStretch()

        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)

        save = QPushButton("Guardar plantilla")
        save.clicked.connect(self.save)
        buttons.addWidget(save)

        layout.addLayout(buttons)

    def save(self):
        template = normalize_newlines(self.template.toPlainText())
        if not template:
            QMessageBox.warning(
                self, "Plantilla vacía", "La plantilla no puede estar vacía."
            )
            return

        self.db.save_template_settings(
            {
                "template": template,
                "delivery_method": normalize_newlines(self.delivery.toPlainText()),
                "payment_method": normalize_newlines(self.payment.toPlainText()),
                "contact_number": self.contact.text(),
            }
        )
        self.accept()
