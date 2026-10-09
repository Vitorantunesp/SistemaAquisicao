"""Explicit interval and point assignment for historical continuous CSV files."""
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import uuid

from PyQt6.QtWidgets import (QDialog, QFormLayout, QLabel, QComboBox, QCheckBox,
                            QDoubleSpinBox, QDialogButtonBox, QFileDialog, QMessageBox)
from ads1800_app.modal_csv import read_recording, import_interval


class ImportDialog(QDialog):
    def __init__(self, recording, config, parent):
        super().__init__(parent)
        self.setWindowTitle('Importar trecho — associar a um ponto')
        self.recording, self.config = recording, config
        form = QFormLayout(self)
        note = QLabel(f'{recording.path.name}\n{recording.sample_rate:g} Hz · unidades convertidas de '
                      f'{recording.units[0]} e {recording.units[1]} para N e m/s².\n'
                      'Selecione um trecho de uma única estrutura e de um único ponto. '
                      'Exclua as batidas usadas para marcar o fim da série.\n'
                      'A geometria e as posições vêm da aba Configuração. Todas as capturas ficarão pendentes de revisão.')
        note.setWordWrap(True)
        form.addRow(note)
        self.point = QComboBox()
        self.point.addItems([p[0] for p in config.points])
        self.point.setCurrentIndex(-1)
        form.addRow('Ponto deste trecho (obrigatório)', self.point)
        self.fields = {}
        for name, title, value, low, high in [
            ('start', 'Início do trecho [s]', recording.samples[0, 0], recording.samples[0, 0], recording.samples[-1, 0]),
            ('end', 'Fim do trecho [s]', recording.samples[-1, 0], recording.samples[0, 0], recording.samples[-1, 0]),
            ('threshold', 'Trigger [N]', config.threshold, .0001, 1e9),
            ('duration', 'Registro total por batida [s]', config.duration, .01, 600),
            ('pretrigger', 'Pré-trigger [s]', config.pretrigger, .001, 60),
            ('low_cut', 'Passa-banda inferior [Hz]', config.low_cut, .0001, 1e6),
            ('high_cut', 'Passa-banda superior [Hz]', min(config.high_cut, .45*recording.sample_rate), .001, 1e6)]:
            box = QDoubleSpinBox()
            box.setDecimals(4)
            box.setRange(low, high)
            box.setValue(value)
            self.fields[name] = box
            form.addRow(title, box)
        self.bandpass = QCheckBox('Ativar passa-banda')
        self.bandpass.setChecked(config.bandpass_enabled)
        form.addRow(self.bandpass)
        self.confirm = QCheckBox('Conferi que este trecho pertence ao ponto selecionado e à mesma estrutura')
        form.addRow(self.confirm)
        explanation = QLabel('O corte sugerido é limitado a 45% da taxa do arquivo; não há reamostragem. '
                             'A faixa elétrica não será importada: confira saturação nos sinais originais.')
        explanation.setWordWrap(True)
        form.addRow(explanation)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def accept(self):
        try:
            if self.point.currentIndex() < 0 or not self.confirm.isChecked():
                raise ValueError('Informe o ponto e confira a associação do trecho antes de importar.')
            values = {name: box.value() for name, box in self.fields.items()}
            if values['start'] >= values['end']:
                raise ValueError('O fim do trecho deve ser posterior ao início.')
            self.import_config = replace(self.config, sample_rate=self.recording.sample_rate,
                bandpass_enabled=self.bandpass.isChecked(),
                **{name: value for name, value in values.items() if name not in ('start', 'end')})
            self.import_config.validate()
        except ValueError as exc:
            QMessageBox.warning(self, 'Importação', str(exc))
            return
        super().accept()


def import_csv(owner):
    try:
        config = owner.read_config()
    except ValueError as exc:
        owner.error(exc)
        return
    path, _ = QFileDialog.getOpenFileName(owner, 'Importar CSV contínuo do ADS', '', 'CSV (*.csv)')
    if not path:
        return
    def loaded(recording):
        dialog = ImportDialog(recording, config, owner)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        folder = QFileDialog.getExistingDirectory(owner, 'Pasta para salvar o novo ensaio importado')
        if not folder:
            return
        directory = Path(folder)/f'importado_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}'
        point = dialog.point.currentText()
        start, end = dialog.fields['start'].value(), dialog.fields['end'].value()
        owner.work(lambda: import_interval(recording, dialog.import_config, directory, point, start, end), owner.adopt_session)
    owner.work(lambda: read_recording(path), loaded)
