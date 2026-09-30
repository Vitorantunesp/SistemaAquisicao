"""Trigger settings and completed-event Morlet views (Qt main thread only)."""
from dataclasses import replace
import numpy as np
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QLinearGradient
from PyQt6.QtWidgets import (QWidget, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                            QGroupBox, QLabel, QDoubleSpinBox, QCheckBox, QDialogButtonBox,
                            QScrollArea, QComboBox)
from ads1800_app.automatic import channel_threshold, validate_automatic
from ads1800_app.ui.bridge_plots import BridgeCanvas

AUTOMATIC_FIELDS = ('trigger_percent', 'trigger_thresholds', 'pre_trigger',
                    'capture_duration', 'wavelet_min', 'wavelet_max')


class TriggerDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle('Aquisição automática')
        self.resize(620, 760)
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        sections = QVBoxLayout(content)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        trigger = QGroupBox('Trigger')
        form = QFormLayout(trigger)
        form.addRow(QLabel('Critério: |valor de engenharia| ≥ limiar'))
        self.percent = self.spin(config.trigger_percent, .001, 100, ' %')
        form.addRow('Percentual de |máximo da escala|', self.percent)
        self.rows = []
        for channel in config.enabled_channels:
            row = QHBoxLayout()
            default = QCheckBox('Usar percentual')
            default.setChecked(str(channel.number) not in config.trigger_thresholds)
            try:
                initial = channel_threshold(channel, config)
            except ValueError:
                initial = .1
                default.setChecked(False)
            value = self.spin(initial, .000000001, 1e12, f' {channel.unit}', 9)
            value.setEnabled(not default.isChecked())
            maximum = 'indisponível' if channel.engineering_max is None else f'{channel.engineering_max:g} {channel.unit}'
            row.addWidget(default)
            row.addWidget(value)
            form.addRow(f'CH {channel.number + 1} · máx.: {maximum}', row)
            self.rows.append((channel, default, value))
            default.toggled.connect(self.update_thresholds)
        self.percent.valueChanged.connect(self.update_thresholds)
        note = QLabel('Qualquer canal dispara a captura conjunta de todos os selecionados.\n'
                      'A detecção usa os valores originais, sem o filtro de visualização.\n'
                      'Configure os acelerômetros no equipamento para obter g ou m/s².')
        note.setWordWrap(True)
        form.addRow(note)
        sections.addWidget(trigger)
        capture = QGroupBox('Captura')
        form = QFormLayout(capture)
        self.pre = self.spin(config.pre_trigger, 0, 119.999, ' s')
        self.duration = self.spin(config.capture_duration, .001, 120, ' s')
        self.after = QLabel()
        form.addRow('Pré-trigger', self.pre)
        form.addRow('Duração total (inclui pré-trigger)', self.duration)
        form.addRow('Após trigger', self.after)
        for field in (self.pre, self.duration):
            field.valueChanged.connect(self.update_after)
        self.update_after()
        sections.addWidget(capture)
        wavelet = QGroupBox('Escalogramas')
        form = QFormLayout(wavelet)
        self.low = self.spin(config.wavelet_min, .001, 1e7, ' Hz')
        self.high = self.spin(config.wavelet_max, .001, 1e7, ' Hz')
        form.addRow('Wavelet', QLabel('Morlet complexa · cmor1.5-1.0'))
        form.addRow('Frequência mínima', self.low)
        form.addRow('Frequência máxima', self.high)
        form.addRow(QLabel(f'Máxima deve ser menor que fs/2 = {config.sample_rate / 2:g} Hz.'))
        sections.addWidget(wavelet)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet('color: #ef7676')
        layout.addWidget(self.error)
        buttons = QDialogButtonBox()
        buttons.addButton('Aplicar', QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton('Cancelar', QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def spin(value, low, high, suffix, decimals=3):
        widget = QDoubleSpinBox()
        widget.setDecimals(decimals)
        widget.setRange(low, high)
        widget.setValue(value)
        widget.setSuffix(suffix)
        return widget

    def update_thresholds(self):
        for channel, default, value in self.rows:
            value.setEnabled(not default.isChecked())
            if default.isChecked() and channel.engineering_max is not None:
                value.setValue(abs(channel.engineering_max) * self.percent.value() / 100)

    def update_after(self):
        self.after.setText(f'{self.duration.value() - self.pre.value():g} s')

    def read_config(self):
        result = replace(self.config, automatic_enabled=True, trigger_percent=self.percent.value(),
                         trigger_thresholds={str(c.number): v.value() for c, default, v in self.rows if not default.isChecked()},
                         pre_trigger=self.pre.value(), capture_duration=self.duration.value(),
                         wavelet_min=self.low.value(), wavelet_max=self.high.value())
        validate_automatic(result)
        return result

    def apply(self):
        try:
            self.read_config()
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class CapturedTrace(BridgeCanvas):
    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        rect = QRectF(65, 10, max(1, self.width() - 95), max(1, self.height() - 36))
        left, right = self.x_range
        zero = rect.left() - left / (right - left) * rect.width()
        p.fillRect(QRectF(rect.left(), rect.top(), max(0, zero - rect.left()), rect.height()), QColor(20, 100, 200, 25))
        p.setPen(QPen(QColor('#1b3040'), 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(zero, rect.top()), QPointF(zero, rect.bottom()))
        p.drawText(QPointF(zero + 5, rect.top() + 13), 'Trigger')


class Scalogram(QWidget):
    COLORS = ('#440154', '#3b528b', '#21918c', '#5ec962', '#fde725')

    def __init__(self, times, frequencies, power, maximum):
        super().__init__()
        self.setMinimumHeight(150)
        self.times, self.frequencies = times, frequencies
        normalized = np.clip(power / maximum, 0, 1) if maximum > 0 else np.zeros_like(power)
        stops = np.array([[QColor(c).red(), QColor(c).green(), QColor(c).blue()] for c in self.COLORS])
        rgb = np.stack([np.interp(normalized, np.linspace(0, 1, 5), stops[:, i]) for i in range(3)], axis=-1)
        rgb = np.ascontiguousarray(rgb[::-1], dtype=np.uint8)
        self.image = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888).copy()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#f7f9fc'))
        rect = QRectF(65, 20, max(1, self.width() - 165), max(1, self.height() - 65))
        p.drawImage(rect, self.image)
        p.setPen(QColor('#172b40'))
        p.drawText(QPointF(7, 13), 'Frequência (Hz)')
        for fraction in (0, .25, .5, .75, 1):
            freq = self.frequencies[-1] - fraction * (self.frequencies[-1] - self.frequencies[0])
            p.drawText(QRectF(0, rect.top() + fraction * rect.height() - 8, 58, 16), Qt.AlignmentFlag.AlignRight, f'{freq:g}')
            value = self.times[0] + fraction * (self.times[-1] - self.times[0])
            p.drawText(QRectF(rect.left() + fraction * rect.width() - 30, rect.bottom() + 4, 60, 18), Qt.AlignmentFlag.AlignCenter, f'{value:.2g}')
        p.drawText(QRectF(rect.left(), rect.bottom() + 24, rect.width(), 18), Qt.AlignmentFlag.AlignCenter, 'Tempo relativo ao trigger (s)')
        zero = rect.left() - self.times[0] / (self.times[-1] - self.times[0]) * rect.width()
        p.setPen(QPen(QColor('white'), 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(zero, rect.top()), QPointF(zero, rect.bottom()))
        bar = QRectF(rect.right() + 15, rect.top(), 12, rect.height())
        gradient = QLinearGradient(bar.bottomLeft(), bar.topLeft())
        for i, color in enumerate(self.COLORS):
            gradient.setColorAt(i / 4, QColor(color))
        p.fillRect(bar, gradient)
        p.setPen(QColor('#172b40'))
        for fraction in (0, .5, 1):
            p.drawText(QPointF(bar.right() + 5, bar.bottom() - fraction * bar.height()), f'{fraction:g}')
        p.drawText(QPointF(rect.right() + 6, 13), 'Pot. relativa')


class EventViewer(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel('Evento'))
        self.events = QComboBox()
        row.addWidget(self.events)
        row.addWidget(QLabel('Sinal capturado'))
        self.channel = QComboBox()
        row.addWidget(self.channel)
        row.addStretch()
        row.addWidget(QLabel('Morlet complexa'))
        layout.addLayout(row)
        self.details = QLabel('Ative Aquisição automática para capturar e analisar os sinais.')
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        layout.addWidget(self.scroll, 1)
        self.history = []
        self.events.currentIndexChanged.connect(self.show_event)
        self.channel.currentIndexChanged.connect(self.show_trace)
        self.trace = None

    def clear(self):
        self.events.clear()
        self.channel.clear()
        self.history.clear()
        self.trace = None
        old = self.scroll.takeWidget()
        if old:
            old.deleteLater()
        self.details.setText('Aguardando captura completa. O monitoramento continua ativo.')

    def add_event(self, capture, result, path, channels):
        self.events.blockSignals(True)
        self.history.append((capture, result, path, channels))
        self.events.addItem(f'{capture.number:03d} · CH ' + ', '.join(str(i + 1) for i in capture.trigger_channels))
        if len(self.history) > 3:
            self.history.pop(0)
            self.events.removeItem(0)
        self.events.setCurrentIndex(len(self.history) - 1)
        self.events.blockSignals(False)
        self.show_event(self.events.currentIndex())

    def show_event(self, index):
        if not 0 <= index < len(self.history):
            return
        capture, result, path, channels = self.history[index]
        self.details.setText(f'Captura {capture.number:03d} concluída · {capture.values.shape[1]} amostras/canal · '
                             f'{capture.sample_rate:g} Hz · sinal e Morlet salvos\n'
                             'Cores: |CWT|² relativa por canal; não comparam amplitudes entre canais. '
                             'Bordas com maior incerteza. Últimos 3 eventos disponíveis.')
        self.details.setToolTip(str(path))
        self.channel.blockSignals(True)
        self.channel.clear()
        for c in channels:
            self.channel.addItem(f'CH {c.number + 1} · {c.label()} [{c.unit}]')
        selected = next((i for i, c in enumerate(channels) if c.number in capture.trigger_channels), 0)
        self.channel.setCurrentIndex(selected)
        self.channel.blockSignals(False)
        content = QWidget()
        content.setStyleSheet('QWidget {background: #f7f9fc; color: #172b40;}')
        layout = QVBoxLayout(content)
        self.trace = CapturedTrace('#1875ce')
        self.trace.setMinimumHeight(100)
        layout.addWidget(self.trace)
        for channel, power in zip(channels, result['power']):
            label = QLabel(f'CH {channel.number + 1} · {channel.label()} [{channel.unit}]')
            label.setStyleSheet('font-weight: bold; color: #1875ce')
            layout.addWidget(label)
            layout.addWidget(Scalogram(result['times'], result['frequencies'], power, float(np.max(power))))
        old = self.scroll.takeWidget()
        if old:
            old.deleteLater()
        self.scroll.setWidget(content)
        self.show_trace(selected)

    def show_trace(self, index):
        event = self.events.currentIndex()
        if self.trace is None or not 0 <= event < len(self.history) or index < 0:
            return
        capture, result, path, channels = self.history[event]
        values = capture.values[index]
        low, high = float(values.min()), float(values.max())
        margin = max((high - low) * .08, 1e-9)
        self.trace.times, self.trace.values = capture.times, values
        self.trace.x_range = (float(capture.times[0]), float(capture.times[-1]))
        self.trace.y_range = (low - margin, high + margin)
        channel = channels[index]
        bounds = (channel.engineering_min, channel.engineering_max)
        if all(v is not None and np.isfinite(v) for v in bounds) and bounds[0] != bounds[1]:
            self.trace.y_range = tuple(sorted(bounds))
        self.trace.update()
