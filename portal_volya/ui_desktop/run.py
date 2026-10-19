"""
Точка запуска нативного настольного портала «Воля» (Zero Local Web).
Запуск: python -m portal_volya.ui_desktop.run
"""

import os
from pathlib import Path
import sys

# Автоматически добавляем корень проекта (C:\Volya) в sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from portal_volya.ui_desktop.main_window import VolyaLivingWindow


def main() -> None:
    # Поддержка четких шрифтов и High DPI
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Воля")
    app.setOrganizationName("Volya")

    # Тёмная гармоничная системная палитра
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.Window, QColor("#080d1a"))
    dark_palette.setColor(QPalette.WindowText, QColor("#f1f5f9"))
    dark_palette.setColor(QPalette.Base, QColor("#0b1222"))
    dark_palette.setColor(QPalette.AlternateBase, QColor("#111b33"))
    dark_palette.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
    dark_palette.setColor(QPalette.ToolTipText, QColor("#ffffff"))
    dark_palette.setColor(QPalette.Text, QColor("#f1f5f9"))
    dark_palette.setColor(QPalette.Button, QColor("#14203d"))
    dark_palette.setColor(QPalette.ButtonText, QColor("#f8fafc"))
    dark_palette.setColor(QPalette.BrightText, QColor("#ef4444"))
    dark_palette.setColor(QPalette.Highlight, QColor("#3b82f6"))
    dark_palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(dark_palette)

    # Гармоничный шрифт интерфейса
    app.setFont(QFont("Segoe UI", 10))

    window = VolyaLivingWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
