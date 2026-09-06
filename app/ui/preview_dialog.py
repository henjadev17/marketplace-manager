from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QScrollArea

class ImagePreviewDialog(QDialog):
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(str(image_path))
        self.resize(1000, 750)
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        pix = QPixmap(str(image_path))
        if not pix.isNull():
            pix = pix.scaled(950, 700, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            label.setPixmap(pix)
        else:
            label.setText("No se pudo previsualizar esta imagen.")
        scroll.setWidget(label)
        layout.addWidget(scroll)
