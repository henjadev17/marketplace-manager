from PySide6.QtWidgets import QComboBox,QDialog,QFormLayout,QHBoxLayout,QLabel,QLineEdit,QPlainTextEdit,QPushButton,QVBoxLayout
from app.ui.product_dialogs import STATUSES
from app.ui.ui_helpers import set_button_role

class DefaultsDialog(QDialog):
    def __init__(self,db,parent=None):
        super().__init__(parent); self.db=db; d=db.get_defaults(); self.setWindowTitle("Valores por defecto"); self.resize(650,580)
        root=QVBoxLayout(self); info=QLabel("Estos valores se cargan automáticamente al crear un producto nuevo y pueden modificarse en cada producto."); info.setWordWrap(True); root.addWidget(info)
        form=QFormLayout(); self.category=QLineEdit(d["category"]); form.addRow("Categoría:",self.category); self.location=QLineEdit(d["location"]); form.addRow("Ubicación:",self.location)
        self.status=QComboBox(); [self.status.addItem(label,value) for value,label in STATUSES]; self.status.setCurrentIndex(max(self.status.findData(d["status"]),0)); form.addRow("Estado:",self.status)
        self.delivery=QPlainTextEdit(); self.delivery.setPlainText(d["delivery_method"]); self.delivery.setMaximumHeight(100); form.addRow("Método de entrega:",self.delivery)
        self.payment=QPlainTextEdit(); self.payment.setPlainText(d["payment_method"]); self.payment.setMaximumHeight(100); form.addRow("Forma de pago:",self.payment)
        self.contact=QLineEdit(d["contact_number"]); form.addRow("Número de contacto:",self.contact); root.addLayout(form)
        row=QHBoxLayout(); row.addStretch(); b=QPushButton("Cancelar"); b.clicked.connect(self.reject); row.addWidget(b); b=QPushButton("Guardar"); b.clicked.connect(self.save); set_button_role(b, "primary"); row.addWidget(b); root.addLayout(row)
    def save(self):
        self.db.save_defaults({"category":self.category.text(),"location":self.location.text(),"status":self.status.currentData(),"delivery_method":self.delivery.toPlainText(),"payment_method":self.payment.toPlainText(),"contact_number":self.contact.text()}); self.accept()
