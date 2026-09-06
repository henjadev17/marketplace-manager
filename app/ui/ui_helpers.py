from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import QApplication, QAbstractItemView


def set_button_role(button, role):
    button.setProperty("role", role)
    button.style().unpolish(button)
    button.style().polish(button)


def configure_table(table):
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setShowGrid(False)
    table.verticalHeader().setVisible(False)
    table.setSortingEnabled(False)


def _is_dark():
    app = QApplication.instance()
    return bool(app and app.property("resolvedTheme") == "dark")


def status_colors(status):
    dark = _is_dark()

    if dark:
        colors = {
            "DRAFT": ("#26303D", "#C5D0DC"),
            "READY": ("#163B2A", "#83E3AD"),
            "PUBLISHED": ("#163457", "#91BCFF"),
            "SOLD": ("#493015", "#F7C979"),
            "ARCHIVED": ("#302B4D", "#C7B9FF"),
        }
    else:
        colors = {
            "DRAFT": ("#F2F4F7", "#475467"),
            "READY": ("#ECFDF3", "#027A48"),
            "PUBLISHED": ("#EFF8FF", "#175CD3"),
            "SOLD": ("#FFF7ED", "#B54708"),
            "ARCHIVED": ("#F4F3FF", "#5925DC"),
        }

    return colors.get(status, colors["DRAFT"])


def style_status_item(item, status):
    background, foreground = status_colors(status)
    item.setBackground(QBrush(QColor(background)))
    item.setForeground(QBrush(QColor(foreground)))
