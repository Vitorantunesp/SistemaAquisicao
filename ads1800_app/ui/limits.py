"""Separate electrical input ranges from calibrated display ranges."""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
                            QCheckBox, QDoubleSpinBox, QLabel, QLineEdit, QScrollArea)


def number(value):
    field = QDoubleSpinBox()
    field.setRange(-1e12, 1e12)
    field.setDecimals(6)
    field.setValue(value)
    return field


class LimitsTab(QScrollArea):
    display_changed = pyqtSignal(int, float, float, bool)
    input_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        note = QLabel('Entrada elétrica: registro da faixa configurada no ADS 1800 pelo Assistente LYNX. Visualização: escala na unidade calibrada do sensor, sincronizada com o gráfico. Esses limites não recortam os dados adquiridos nem o CSV.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.electrical = QGroupBox('Faixa elétrica de entrada — configurar fisicamente no Assistente LYNX')
        electrical = QGridLayout(self.electrical)
        self.visual = QGroupBox('Limites do gráfico — unidade do sensor')
        visual = QGridLayout(self.visual)
        for grid, labels in [(electrical, ['Canal', 'Definir faixa', 'Mínimo', 'Máximo', 'Unidade elétrica']),
                             (visual, ['Canal / sensor', 'Unidade', 'Y automático', 'Mínimo', 'Máximo'])]:
            for col, text in enumerate(labels):
                grid.addWidget(QLabel(text), 0, col)
        self.rows = []
        for i in range(8):
            row = dict(name=QLabel(f'Canal {i+1}'), unit=QLabel('V'),
                       auto=QCheckBox(), low=number(-1), high=number(1),
                       defined=QCheckBox(), input_low=number(-10), input_high=number(10), input_unit=QLineEdit('V'))
            row['auto'].setChecked(True)
            for col, widget in enumerate([QLabel(f'Canal {i+1}'), row['defined'], row['input_low'], row['input_high'], row['input_unit']]):
                electrical.addWidget(widget, i+1, col)
            for col, key in enumerate(['name', 'unit', 'auto', 'low', 'high']):
                visual.addWidget(row[key], i+1, col)
            self.rows.append(row)
            for key in ('low', 'high'):
                row[key].valueChanged.connect(lambda _, index=i: self._display_edited(index))
            row['auto'].toggled.connect(lambda _, index=i: self._display_edited(index))
            for key in ('input_low', 'input_high'):
                row[key].valueChanged.connect(lambda _, index=i: self._input_edited(index))
            row['defined'].toggled.connect(lambda _, index=i: self._input_edited(index))
            row['input_unit'].textChanged.connect(lambda _, index=i: self._input_edited(index))
            self._enable_fields(i)
        layout.addWidget(self.electrical)
        layout.addWidget(self.visual)
        self.status = QLabel('')
        layout.addWidget(self.status)
        self.actions = QHBoxLayout()
        layout.addLayout(self.actions)
        layout.addStretch()
        self.setWidget(content)

    def _enable_fields(self, index):
        row = self.rows[index]
        for key in ('low', 'high'):
            row[key].setEnabled(not row['auto'].isChecked())
        for key in ('input_low', 'input_high', 'input_unit'):
            row[key].setEnabled(row['defined'].isChecked())

    def _display_edited(self, index):
        self._enable_fields(index)
        row = self.rows[index]
        if row['low'].value() >= row['high'].value():
            self.status.setText(f'Canal {index+1}: mínimo do gráfico deve ser menor que máximo.')
            return
        self.status.clear()
        self.display_changed.emit(index, row['low'].value(), row['high'].value(), row['auto'].isChecked())

    def _input_edited(self, index):
        self._enable_fields(index)
        self.input_changed.emit(index)

    def set_display(self, index, low, high, automatic):
        row = self.rows[index]
        for key in ('low', 'high', 'auto'):
            row[key].blockSignals(True)
        row['low'].setValue(low)
        row['high'].setValue(high)
        row['auto'].setChecked(automatic)
        for key in ('low', 'high', 'auto'):
            row[key].blockSignals(False)
        self._enable_fields(index)

    def apply_channel(self, channel):
        row = self.rows[channel.number]
        self.set_display(channel.number, channel.display_min, channel.display_max, channel.display_auto)
        for key in ('defined', 'input_low', 'input_high', 'input_unit'):
            row[key].blockSignals(True)
        row['defined'].setChecked(channel.input_min is not None)
        row['input_low'].setValue(channel.input_min if channel.input_min is not None else -10)
        row['input_high'].setValue(channel.input_max if channel.input_max is not None else 10)
        row['input_unit'].setText(channel.input_unit)
        for key in ('defined', 'input_low', 'input_high', 'input_unit'):
            row[key].blockSignals(False)
        self._enable_fields(channel.number)

    def values(self, index):
        row = self.rows[index]
        defined = row['defined'].isChecked()
        return dict(display_min=row['low'].value(), display_max=row['high'].value(), display_auto=row['auto'].isChecked(),
                    input_min=row['input_low'].value() if defined else None,
                    input_max=row['input_high'].value() if defined else None,
                    input_unit=row['input_unit'].text().strip())
