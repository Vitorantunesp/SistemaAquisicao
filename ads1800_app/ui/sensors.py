"""Sensor catalog editor and channel profile selection."""
from dataclasses import replace
from pathlib import Path
import uuid

from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QMessageBox, QPushButton, QScrollArea, QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ads1800_app.config import SENSOR_TYPES
from ads1800_app.sensors import SensorProfile, load_catalog, save_catalog

CATALOG_PATH = Path(__file__).resolve().parents[2] / 'configuracoes' / 'sensores.json'


class SensorEditor(QDialog):
    def __init__(self, profile=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Parâmetros do sensor')
        self.resize(620, 740)
        self.original = profile or SensorProfile()
        self.profile = None
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        form = QFormLayout()
        self.fields = {}
        for key, label in [('name', 'Nome'), ('sensor_type', 'Tipo'), ('manufacturer', 'Fabricante'),
                           ('model', 'Modelo'), ('serial_number', 'Número de série'),
                           ('input_type', 'Tipo de entrada elétrica'), ('input_scale', 'Escala de entrada (com unidade)'),
                           ('input_min', 'Mínimo elétrico (opcional)'), ('input_max', 'Máximo elétrico (opcional)'), ('input_unit', 'Unidade elétrica'),
                           ('sensitivity', 'Sensibilidade (opcional)'), ('sensitivity_unit', 'Unidade da sensibilidade'),
                           ('unit', 'Unidade de saída'), ('gain', 'Ganho aplicado'), ('offset', 'Offset aplicado'),
                           ('notes', 'Observações')]:
            if key in ('sensor_type', 'input_type'):
                widget = QComboBox()
                widget.setEditable(True)
                widget.addItems(SENSOR_TYPES if key == 'sensor_type' else ['', 'Tensão', 'IEPE / CCP', 'Corrente', 'Ponte resistiva', 'Termopar', 'Pt100', 'Outro'])
                widget.setCurrentText(getattr(self.original, key))
            else:
                value = getattr(self.original, key)
                widget = QLineEdit('' if value is None else str(value))
            self.fields[key] = widget
            form.addRow(label, widget)
        self.fields['input_scale'].setPlaceholderText('Ex.: ±10 V, ±100 mV, 4–20 mA')
        content_layout.addLayout(form)
        scroll.setWidget(content)
        layout.addWidget(scroll, 2)
        calculate = QPushButton('Calcular ganho pela sensibilidade...')
        calculate.clicked.connect(self._calculate_gain)
        layout.addWidget(calculate)
        note = QLabel('Sensibilidade: use Calcular ganho e depois Salvar / Aplicar ao canal. A leitura usa valor recebido × ganho + offset. Tipo e escala de entrada registram a configuração elétrica; ajuste esses parâmetros no Assistente LYNX, pois este cadastro não programa o hardware.')
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addWidget(QLabel('Parâmetros adicionais livres (ex.: massa, faixa, IEPE, ponta do martelo, calibração):'))
        self.extra = QTableWidget(0, 2)
        self.extra.setHorizontalHeaderLabels(['Parâmetro', 'Valor / unidade'])
        self.extra.horizontalHeader().setStretchLastSection(True)
        for name, value in self.original.parameters.items():
            self._add_row(name, value)
        layout.addWidget(self.extra, 1)
        row = QHBoxLayout()
        add = QPushButton('Adicionar parâmetro')
        add.clicked.connect(lambda: self._add_row())
        remove = QPushButton('Remover parâmetro')
        remove.clicked.connect(lambda: self.extra.removeRow(self.extra.currentRow()) if self.extra.currentRow() >= 0 else None)
        row.addWidget(add)
        row.addWidget(remove)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('Salvar')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Cancelar')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_row(self, name='', value=''):
        row = self.extra.rowCount()
        self.extra.insertRow(row)
        self.extra.setItem(row, 0, QTableWidgetItem(name))
        self.extra.setItem(row, 1, QTableWidgetItem(value))

    def _calculate_gain(self):
        try:
            value = float(self.fields['sensitivity'].text().replace(',', '.'))
            unit = self.fields['unit'].text().strip()
            sensitivity_unit = self.fields['sensitivity_unit'].text().strip()
            if not unit or sensitivity_unit not in (f'mV/{unit}', f'V/{unit}'):
                raise ValueError('Use mV/<unidade de saída> ou V/<unidade de saída>, por exemplo mV/g, mV/(m/s²) com saída (m/s²), ou mV/N.')
            import math
            if not math.isfinite(value) or value <= 0:
                raise ValueError('Informe uma sensibilidade positiva.')
            source, accepted = QInputDialog.getItem(self, 'Unidade recebida',
                'Unidade dos valores que o driver entrega ao aplicativo\n(considere a escala já configurada no equipamento):',
                ['Selecione...', 'V', 'mV'], 0, False)
            if not accepted or source == 'Selecione...':
                return
            volts_per_unit = value / 1000 if sensitivity_unit.startswith('mV/') else value
            gain = (1 if source == 'V' else .001) / volts_per_unit
            self.fields['gain'].setText(f'{gain:.12g}')
        except Exception as exc:
            QMessageBox.warning(self, 'Sensibilidade', str(exc))

    def read_profile(self):
        data = {key: widget.currentText().strip() if isinstance(widget, QComboBox) else widget.text().strip()
                for key, widget in self.fields.items()}
        for key in ('gain', 'offset'):
            data[key] = float(data[key].replace(',', '.'))
        for key in ('input_min', 'input_max'):
            data[key] = float(data[key].replace(',', '.')) if data[key] else None
        if data['input_min'] is not None and data['input_max'] is not None:
            data['input_scale'] = f"{data['input_min']:g} a {data['input_max']:g} {data['input_unit']}"
        parameters = {}
        for row in range(self.extra.rowCount()):
            name = self.extra.item(row, 0).text().strip() if self.extra.item(row, 0) else ''
            value = self.extra.item(row, 1).text().strip() if self.extra.item(row, 1) else ''
            if not name and not value:
                continue
            if not name or name in parameters:
                raise ValueError('Cada parâmetro adicional precisa de um nome único.')
            parameters[name] = value
        profile = SensorProfile(id=self.original.id, parameters=parameters, **data)
        profile.validate()
        return profile

    def accept(self):
        try:
            self.profile = self.read_profile()
        except Exception as exc:
            QMessageBox.warning(self, 'Parâmetros inválidos', str(exc))
            return
        super().accept()


class SensorCatalogDialog(QDialog):
    def __init__(self, parent=None, path=CATALOG_PATH):
        super().__init__(parent)
        self.path = Path(path)
        self.profiles = load_catalog(self.path) if self.path.exists() else []
        self.setWindowTitle('Catálogo de sensores')
        self.resize(720, 500)
        layout = QVBoxLayout(self)
        label = QLabel('Cadastre sensores reutilizáveis. As alterações são salvas no catálogo ao confirmar cada edição.')
        label.setWordWrap(True)
        layout.addWidget(label)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _: self._edit())
        layout.addWidget(self.list)
        row = QHBoxLayout()
        for label, callback in [('Novo', self._new), ('Editar', self._edit), ('Duplicar', self._duplicate), ('Excluir', self._delete)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        row = QHBoxLayout()
        for label, callback in [('Importar lista JSON...', self._import), ('Exportar lista JSON...', self._export)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText('Fechar')
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh()

    def _refresh(self, selection=0):
        self.list.clear()
        for p in self.profiles:
            self.list.addItem(f'{p.name} | {p.sensor_type} | {p.model} | Série: {p.serial_number or "—"}')
        self.list.setCurrentRow(selection)

    def _commit(self, profiles, selection=0):
        try:
            save_catalog(self.path, profiles)
        except Exception as exc:
            QMessageBox.critical(self, 'Falha ao salvar catálogo', str(exc))
            return
        self.profiles = profiles
        self._refresh(selection)

    def _new(self):
        editor = SensorEditor(parent=self)
        if editor.exec() == QDialog.DialogCode.Accepted:
            self._commit(self.profiles + [editor.profile], len(self.profiles))

    def _edit(self):
        index = self.list.currentRow()
        if index < 0:
            return
        editor = SensorEditor(self.profiles[index], self)
        if editor.exec() == QDialog.DialogCode.Accepted:
            profiles = list(self.profiles)
            profiles[index] = editor.profile
            self._commit(profiles, index)

    def _duplicate(self):
        index = self.list.currentRow()
        if index >= 0:
            profile = replace(self.profiles[index], name=self.profiles[index].name + ' (cópia)', id=str(uuid.uuid4()))
            self._commit(self.profiles + [profile], len(self.profiles))

    def _delete(self):
        index = self.list.currentRow()
        if index >= 0 and QMessageBox.question(self, 'Excluir sensor', f'Excluir {self.profiles[index].name} do catálogo?') == QMessageBox.StandardButton.Yes:
            self._commit(self.profiles[:index] + self.profiles[index + 1:])

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Importar catálogo', '', 'Catálogo JSON (*.json)')
        if path:
            try:
                imported = load_catalog(path)
                # Import as independent entries: never overwrite operator records.
                imported = [replace(p, id=str(uuid.uuid4())) for p in imported]
                self._commit(self.profiles + imported)
            except Exception as exc:
                QMessageBox.critical(self, 'Falha ao importar', str(exc))

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Exportar catálogo', 'sensores.json', 'Catálogo JSON (*.json)')
        if path:
            try:
                save_catalog(path, self.profiles)
            except Exception as exc:
                QMessageBox.critical(self, 'Falha ao exportar', str(exc))
