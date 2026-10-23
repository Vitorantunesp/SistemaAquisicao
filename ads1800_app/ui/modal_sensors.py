"""Editable additional accelerometers with hardware channel selectors."""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
    QLineEdit, QComboBox, QDoubleSpinBox, QPushButton, QHeaderView)


class SensorTable(QWidget):
    def __init__(self):
        super().__init__()
        self.channels = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['Nome', 'Canal', 'X [m]', 'Y [m]', 'Fator SI'])
        self.table.setMinimumHeight(150)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(1, 225)
        layout.addWidget(self.table)
        row = QHBoxLayout()
        add = QPushButton('Adicionar acelerômetro')
        add.clicked.connect(lambda: self.add_sensor())
        remove = QPushButton('Remover selecionado')
        remove.clicked.connect(lambda: self.table.removeRow(self.table.currentRow()) if self.table.currentRow() >= 0 else None)
        row.addWidget(add)
        row.addWidget(remove)
        layout.addLayout(row)

    def populate_channels(self, combo, selected=None):
        combo.clear()
        combo.addItem('Selecione o canal…', None)
        for channel in self.channels:
            combo.addItem(f'CH {channel.number+1}: {channel.name} [{channel.unit}]', channel.number)
        if selected is not None and combo.findData(selected) < 0:
            combo.addItem(f'CH {selected+1} — indisponível', selected)
        combo.setCurrentIndex(max(0, combo.findData(selected)))

    def set_channels(self, channels):
        self.channels = list(channels)
        for row in range(self.table.rowCount()):
            combo = self.table.cellWidget(row, 1)
            self.populate_channels(combo, combo.currentData())

    def add_sensor(self, sensor=None):
        if sensor is None:
            used = {self.table.cellWidget(i, 0).text() for i in range(self.table.rowCount())}
            number = 2
            while f'A{number}' in used:
                number += 1
            sensor = dict(name=f'A{number}', channel=None, position=[0, 0], factor=1)
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setCellWidget(row, 0, QLineEdit(sensor['name']))
        combo = QComboBox()
        self.populate_channels(combo, sensor['channel'])
        self.table.setCellWidget(row, 1, combo)
        for col, value in enumerate([*sensor['position'], sensor['factor']], 2):
            box = QDoubleSpinBox()
            box.setDecimals(6)
            box.setRange(-1e9 if col == 4 else -1e6, 1e9 if col == 4 else 1e6)
            box.setValue(value)
            self.table.setCellWidget(row, col, box)
        self.table.setCurrentCell(row, 0)

    def set_sensors(self, sensors):
        self.table.setRowCount(0)
        for sensor in sensors:
            self.add_sensor(sensor)

    def sensors(self):
        result = []
        available = {c.number for c in self.channels}
        for row in range(self.table.rowCount()):
            channel = self.table.cellWidget(row, 1).currentData()
            if channel is None or channel not in available:
                raise ValueError(f'Selecione um canal disponível para o acelerômetro da linha {row+1}.')
            result.append(dict(name=self.table.cellWidget(row, 0).text().strip(), channel=channel,
                               position=[self.table.cellWidget(row, col).value() for col in (2, 3)],
                               factor=self.table.cellWidget(row, 4).value(), limits=None))
        return result
