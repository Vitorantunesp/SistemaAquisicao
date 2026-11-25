"""Readable left navigation for the three modal workspaces."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QListWidget, QStackedWidget, QScrollArea, QFrame


class ModalNavigation(QWidget):
    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(220)
        self.sidebar.setWordWrap(True)
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar.setStyleSheet('''
            QListWidget { background: #f1f5f9; border: 0; padding: 12px 8px; }
            QListWidget::item { padding: 18px 12px; margin-bottom: 6px; border-radius: 6px; }
            QListWidget::item:selected { background: #dbeafe; color: #1d4ed8; }
            QListWidget::item:hover:!selected { background: #e2e8f0; }
        ''')
        self.stack = QStackedWidget()
        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, 1)

    def addTab(self, widget, title):
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        index = self.stack.addWidget(scroll)
        self.sidebar.addItem(title)
        if self.sidebar.currentRow() < 0:
            self.sidebar.setCurrentRow(0)
        return index

    def setCurrentIndex(self, index):
        self.sidebar.setCurrentRow(index)

    def currentIndex(self):
        return self.stack.currentIndex()

    def widget(self, index):
        return self.stack.widget(index).widget()

    def count(self):
        return self.stack.count()
