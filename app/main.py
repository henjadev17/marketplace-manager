import sys
from PySide6.QtWidgets import QApplication, QMessageBox
from app.services.photo_storage import PhotoRecoveryError
from app.ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Marketplace Manager")
    app.setOrganizationName("MarketplaceManager")
    app.setStyle("Fusion")
    try:
        window = MainWindow()
    except PhotoRecoveryError as exc:
        QMessageBox.critical(None, "No se pudieron recuperar las fotos", str(exc))
        sys.exit(1)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
