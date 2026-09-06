from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette


LIGHT = {
    "bg": "#F4F6FA",
    "surface": "#FFFFFF",
    "surface_alt": "#F8FAFC",
    "input": "#FFFFFF",
    "border": "#D7DEE8",
    "border_strong": "#C5CEDA",
    "text": "#172033",
    "muted": "#667085",
    "accent": "#2563EB",
    "accent_hover": "#1D4ED8",
    "accent_pressed": "#1E40AF",
    "accent_soft": "#E8F0FF",
    "selection": "#DCE9FF",
    "danger": "#DC2626",
    "danger_hover": "#B91C1C",
    "success": "#15803D",
    "success_hover": "#166534",
    "warning": "#B45309",
    "warning_hover": "#92400E",
    "disabled": "#E5E7EB",
    "disabled_text": "#98A2B3",
    "scroll": "#B8C2D1",
}

DARK = {
    "bg": "#0D1117",
    "surface": "#151B24",
    "surface_alt": "#111720",
    "input": "#10161F",
    "border": "#2A3442",
    "border_strong": "#3A4657",
    "text": "#E8EDF5",
    "muted": "#9AA7B8",
    "accent": "#4C8DFF",
    "accent_hover": "#6BA1FF",
    "accent_pressed": "#3576E5",
    "accent_soft": "#172A48",
    "selection": "#1E365C",
    "danger": "#EF5350",
    "danger_hover": "#FF6B68",
    "success": "#38A169",
    "success_hover": "#48BB78",
    "warning": "#D69E2E",
    "warning_hover": "#ECC94B",
    "disabled": "#242D39",
    "disabled_text": "#667085",
    "scroll": "#465365",
}


def palette_for(resolved_theme: str):
    return DARK if resolved_theme == "dark" else LIGHT


def stylesheet_for(resolved_theme: str) -> str:
    c = palette_for(resolved_theme)

    return f"""
    * {{
        font-family: "Segoe UI";
        font-size: 10pt;
    }}

    QMainWindow, QDialog {{
        background: {c["bg"]};
        color: {c["text"]};
    }}

    QWidget {{
        color: {c["text"]};
    }}

    QFrame#TopBar,
    QFrame#ToolCard,
    QFrame#GalleryCard,
    QFrame#EditorCard {{
        background: {c["surface"]};
        border: 1px solid {c["border"]};
        border-radius: 12px;
    }}

    QLabel#PageTitle {{
        font-size: 20pt;
        font-weight: 700;
        color: {c["text"]};
    }}

    QLabel#PageSubtitle,
    QLabel[role="muted"] {{
        color: {c["muted"]};
    }}

    QLabel#PathLabel {{
        background: {c["surface_alt"]};
        border: 1px solid {c["border"]};
        border-radius: 8px;
        padding: 7px 10px;
        color: {c["muted"]};
    }}

    QLabel#CodeBadge,
    QLabel#InfoBadge {{
        background: {c["accent_soft"]};
        color: {c["accent"]};
        border: 1px solid {c["accent"]};
        border-radius: 7px;
        padding: 4px 8px;
        font-weight: 600;
    }}

    QGroupBox {{
        background: {c["surface"]};
        border: 1px solid {c["border"]};
        border-radius: 12px;
        margin-top: 14px;
        padding: 16px 12px 12px 12px;
        font-weight: 600;
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 14px;
        padding: 0 6px;
        color: {c["text"]};
    }}

    QLineEdit,
    QComboBox,
    QAbstractSpinBox {{
        background: {c["input"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 8px;
        padding: 4px 10px;
        min-height: 24px;
        selection-background-color: {c["accent"]};
        selection-color: #FFFFFF;
    }}

    QPlainTextEdit,
    QTextEdit {{
        background: {c["input"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 8px;
        padding: 8px 10px;
        selection-background-color: {c["accent"]};
        selection-color: #FFFFFF;
    }}

    QPlainTextEdit[readOnly="true"],
    QTextEdit[readOnly="true"],
    QLineEdit[readOnly="true"] {{
        background: {c["surface_alt"]};
    }}

    QLineEdit:focus,
    QPlainTextEdit:focus,
    QTextEdit:focus,
    QComboBox:focus,
    QAbstractSpinBox:focus {{
        border: 1px solid {c["accent"]};
    }}

    QComboBox {{
        padding-right: 28px;
    }}

    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}

    QAbstractSpinBox {{
        padding-right: 24px;
    }}

    QAbstractSpinBox::up-button,
    QAbstractSpinBox::down-button {{
        border: none;
        width: 16px;
        background: transparent;
        subcontrol-origin: border;
    }}

    QAbstractSpinBox::up-button {{
        subcontrol-position: top right;
        margin: 4px 4px 0 0;
        height: 10px;
    }}

    QAbstractSpinBox::down-button {{
        subcontrol-position: bottom right;
        margin: 0 4px 4px 0;
        height: 10px;
    }}

    QComboBox QAbstractItemView {{
        background: {c["surface"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        selection-background-color: {c["selection"]};
        selection-color: {c["text"]};
        outline: none;
    }}

    QPushButton {{
        background: {c["surface_alt"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 8px;
        padding: 7px 12px;
        min-height: 20px;
        font-weight: 600;
    }}

    QPushButton:hover {{
        border-color: {c["border_strong"]};
        background: {c["accent_soft"]};
    }}

    QPushButton:pressed {{
        padding-top: 8px;
        padding-bottom: 6px;
    }}

    QPushButton[role="primary"] {{
        background: {c["accent"]};
        color: #FFFFFF;
        border-color: {c["accent"]};
    }}

    QPushButton[role="primary"]:hover {{
        background: {c["accent_hover"]};
        border-color: {c["accent_hover"]};
    }}

    QPushButton[role="danger"] {{
        background: {c["danger"]};
        color: #FFFFFF;
        border-color: {c["danger"]};
    }}

    QPushButton[role="danger"]:hover {{
        background: {c["danger_hover"]};
    }}

    QPushButton[role="success"] {{
        background: {c["success"]};
        color: #FFFFFF;
        border-color: {c["success"]};
    }}

    QPushButton[role="success"]:hover {{
        background: {c["success_hover"]};
    }}

    QPushButton[role="warning"] {{
        background: {c["warning"]};
        color: #FFFFFF;
        border-color: {c["warning"]};
    }}

    QPushButton[role="warning"]:hover {{
        background: {c["warning_hover"]};
    }}

    QPushButton[role="ghost"] {{
        background: transparent;
        border-color: transparent;
        color: {c["muted"]};
    }}

    QPushButton[role="ghost"]:hover {{
        background: {c["accent_soft"]};
        color: {c["accent"]};
    }}

    QPushButton:disabled {{
        background: {c["disabled"]};
        border-color: {c["disabled"]};
        color: {c["disabled_text"]};
    }}

    QCheckBox {{
        spacing: 8px;
    }}

    QListWidget {{
        background: {c["surface"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 12px;
        padding: 6px;
        outline: none;
    }}

    QListWidget::item {{
        border: 1px solid transparent;
        border-radius: 9px;
        padding: 5px;
        margin: 2px;
    }}

    QListWidget::item:hover {{
        background: {c["surface_alt"]};
        border-color: {c["border"]};
    }}

    QListWidget::item:selected {{
        background: {c["selection"]};
        color: {c["text"]};
        border: 2px solid {c["accent"]};
    }}

    QTableWidget {{
        background: {c["surface"]};
        alternate-background-color: {c["surface_alt"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 10px;
        gridline-color: {c["border"]};
        selection-background-color: {c["selection"]};
        selection-color: {c["text"]};
        outline: none;
    }}

    QTableWidget::item {{
        padding: 6px;
        border: none;
    }}

    QHeaderView::section {{
        background: {c["surface_alt"]};
        color: {c["muted"]};
        border: none;
        border-bottom: 1px solid {c["border"]};
        padding: 8px 7px;
        font-weight: 700;
    }}

    QStatusBar {{
        background: {c["surface"]};
        color: {c["muted"]};
        border-top: 1px solid {c["border"]};
    }}

    QSplitter::handle {{
        background: transparent;
        width: 8px;
        height: 8px;
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 12px;
        margin: 2px;
    }}

    QScrollBar::handle:vertical {{
        background: {c["scroll"]};
        border-radius: 5px;
        min-height: 32px;
    }}

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical,
    QScrollBar::sub-page:vertical {{
        background: transparent;
        height: 0;
    }}

    QScrollBar:horizontal {{
        background: transparent;
        height: 12px;
        margin: 2px;
    }}

    QScrollBar::handle:horizontal {{
        background: {c["scroll"]};
        border-radius: 5px;
        min-width: 32px;
    }}

    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal,
    QScrollBar::add-page:horizontal,
    QScrollBar::sub-page:horizontal {{
        background: transparent;
        width: 0;
    }}

    QToolTip {{
        background: {c["surface"]};
        color: {c["text"]};
        border: 1px solid {c["border_strong"]};
        padding: 5px;
    }}
    """


class ThemeManager(QObject):
    themeChanged = Signal(str)

    MODES = ("system", "light", "dark")

    def __init__(self, app, db):
        super().__init__()
        self.app = app
        self.db = db

        stored = self.db.get_setting("appearance", "system")
        self.mode = stored if stored in self.MODES else "system"

        self.app.setFont(QFont("Segoe UI", 10))
        self.apply(self.mode, persist=False)

        try:
            hints = QGuiApplication.styleHints()
            signal = getattr(hints, "colorSchemeChanged", None)
            if signal is not None:
                signal.connect(self._system_scheme_changed)
        except Exception:
            pass

    def resolved(self):
        if self.mode in ("light", "dark"):
            return self.mode

        try:
            scheme = QGuiApplication.styleHints().colorScheme()
            if scheme == Qt.ColorScheme.Dark:
                return "dark"
            if scheme == Qt.ColorScheme.Light:
                return "light"
        except Exception:
            pass

        color = self.app.palette().color(QPalette.Window)
        return "dark" if color.lightness() < 128 else "light"

    def apply(self, mode=None, persist=True):
        if mode is not None:
            if mode not in self.MODES:
                mode = "system"
            self.mode = mode

        if persist:
            self.db.set_setting("appearance", self.mode)

        resolved = self.resolved()
        self.app.setProperty("appearanceMode", self.mode)
        self.app.setProperty("resolvedTheme", resolved)
        self.app.setStyle("Fusion")
        self.app.setStyleSheet(stylesheet_for(resolved))
        self.themeChanged.emit(resolved)

    def _system_scheme_changed(self, *_):
        if self.mode == "system":
            self.apply("system", persist=False)
