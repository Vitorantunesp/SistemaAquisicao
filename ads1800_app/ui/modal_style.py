"""Use a readable Windows UI font, including Qt's offscreen renderer."""
import os
from pathlib import Path

from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication


def modal_font():
    if os.name == 'nt':
        if not QFontDatabase.families():
            font = Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts/segoeui.ttf'
            if font.is_file():
                QFontDatabase.addApplicationFont(str(font))
        return QFont('Segoe UI', 10)
    return QApplication.font()
