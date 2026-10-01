"""Time-based display buffers and independent Qt channel plots."""
from collections import deque
import math

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (QCheckBox, QDoubleSpinBox, QGridLayout, QHBoxLayout,
                            QLabel, QMdiArea, QMdiSubWindow, QToolTip, QVBoxLayout, QWidget)

COLORS = ('#2563eb', '#dc2626', '#16a34a', '#9333ea', '#ea580c', '#0891b2', '#4f46e5', '#be123c')


class DisplayBuffer:
    def __init__(self, seconds=10):
        self.seconds = seconds
        self.blocks = deque()

    def append(self, times, values):
        if len(times):
            self.blocks.append((np.asarray(times, dtype=float), np.asarray(values, dtype=float)))
            self.trim()

    def trim(self):
        if not self.blocks:
            return
        cutoff = self.blocks[-1][0][-1] - self.seconds
        while self.blocks and self.blocks[0][0][-1] < cutoff:
            self.blocks.popleft()
        times, values = self.blocks[0]
        start = np.searchsorted(times, cutoff)
        if start:
            self.blocks[0] = (times[start:].copy(), values[:, start:].copy())

    def snapshot(self):
        if not self.blocks:
            return np.array([]), np.empty((0, 0))
        return (np.concatenate([b[0] for b in self.blocks]),
                np.concatenate([b[1] for b in self.blocks], axis=1))


def envelope_indices(values, width):
    """Retain both extrema in each pixel bucket, including narrow peaks."""
    size = len(values)
    if size <= width * 2:
        return np.arange(size)
    step = math.ceil(size / width)
    padded = np.full(math.ceil(size / step) * step, np.nan)
    padded[:size] = values
    bins = padded.reshape(-1, step)
    valid = np.isfinite(bins)
    offsets = np.arange(len(bins)) * step
    low = np.argmin(np.where(valid, bins, np.inf), axis=1) + offsets
    high = np.argmax(np.where(valid, bins, -np.inf), axis=1) + offsets
    # A nonfinite point splits the curve rather than connecting missing data.
    gaps = np.argmax(~valid, axis=1) + offsets
    gaps = gaps[(~valid).any(axis=1)]
    indices = np.unique(np.concatenate(([0, size - 1], low, high, gaps)))
    return indices[indices < size]


class ChannelCanvas(QWidget):
    def __init__(self, color, parent=None):
        super().__init__(parent)
        self.color = color
        self.setMinimumSize(300, 180)
        self.times = np.array([])
        self.values = np.array([])
        self.x_range = (0, 10)
        self.y_range = (-1, 1)
        self.x_label = 'Tempo [s]'
        self.setMouseTracking(True)

    def plot_rect(self):
        height = self.fontMetrics().height()
        return QRectF(85, 12, max(1, self.width()-105),
                      max(1, self.height()-12-(2*height+20)))

    def mouseMoveEvent(self, event):
        rect = self.plot_rect()
        if rect.contains(event.position()) and len(self.times):
            x = self.x_range[0] + (event.position().x()-rect.left())/rect.width()*(self.x_range[1]-self.x_range[0])
            index = int(np.argmin(abs(self.times-x)))
            unit = 'Hz' if self.x_label == 'Frequência [Hz]' else 's'
            QToolTip.showText(event.globalPosition().toPoint(),
                             f'{self.times[index]:.6g} {unit}\nValor: {self.values[index]:.6g}', self)
        else:
            QToolTip.hideText()
        super().mouseMoveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('white'))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.plot_rect()
        left, top, right, bottom = rect.left(), rect.top(), rect.right(), rect.bottom()
        text_height = self.fontMetrics().height()+4
        x0, x1 = self.x_range
        y0, y1 = self.y_range
        for i in range(5):
            fraction = i / 4
            y = top + rect.height() * fraction
            painter.setPen(QColor('#e2e8f0'))
            painter.drawLine(QPointF(left, y), QPointF(right, y))
            painter.setPen(QColor('#475569'))
            painter.drawText(QRectF(0, y - 9, left - 8, 18), Qt.AlignmentFlag.AlignRight, f'{y1 - (y1 - y0) * fraction:.4g}')
        # Reserve space from actual font metrics; endpoint labels stay inside the widget.
        label_width = max(self.fontMetrics().horizontalAdvance(f'{v:.6g}') for v in np.linspace(x0, x1, 5))+16
        intervals = max(1, min(4, int(rect.width()/label_width)))
        for i in range(intervals+1):
            x = left+rect.width()*i/intervals
            painter.setPen(QColor('#e2e8f0'))
            painter.drawLine(QPointF(x, top), QPointF(x, bottom))
            painter.setPen(QColor('#334155'))
            label_left = max(0, min(x-label_width/2, self.width()-label_width))
            painter.drawText(QRectF(label_left, bottom+4, label_width, text_height),
                             Qt.AlignmentFlag.AlignCenter, f'{x0+(x1-x0)*i/intervals:.6g}')
        painter.drawText(QRectF(left, bottom+text_height+5, rect.width(), text_height),
                         Qt.AlignmentFlag.AlignCenter, self.x_label)
        if not len(self.times):
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, 'Aguardando amostras...')
            return
        painter.setClipRect(rect)
        painter.setPen(QPen(QColor(self.color), 1.4))
        points = QPolygonF()
        for i in envelope_indices(self.values, max(1, int(rect.width()))):
            if not np.isfinite(self.values[i]):
                painter.drawPolyline(points)
                points = QPolygonF()
                continue
            points.append(QPointF(left + (self.times[i] - x0) / (x1 - x0) * rect.width(),
                                  bottom - (self.values[i] - y0) / (y1 - y0) * rect.height()))
        painter.drawPolyline(points)


class ChannelPlot(QWidget):
    limits_changed = pyqtSignal(float, float, bool)

    def __init__(self, label, unit, color):
        super().__init__()
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        title = QLabel(f'{label} [{unit}]' if unit else label)
        title.setStyleSheet(f'font-weight: bold; color: {color}')
        header.addWidget(title)
        header.addStretch()
        self.auto = QCheckBox('Y automático')
        self.auto.setChecked(True)
        header.addWidget(self.auto)
        layout.addLayout(header)
        self.unit = unit
        self.current_value = QLabel('—')
        self.current_value.setTextFormat(Qt.TextFormat.PlainText)
        self.current_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.current_value.setWordWrap(True)
        self.current_value.setStyleSheet(f'font-size: 22px; font-weight: bold; color: {color}')
        self.current_value.setToolTip('Valor da última amostra recebida, já calibrado. Não é média, RMS ou pico.')
        self.value_time = QLabel('Aguardando amostras')
        layout.addWidget(self.current_value)
        layout.addWidget(self.value_time)
        scale = QHBoxLayout()
        self.minimum, self.maximum = QDoubleSpinBox(), QDoubleSpinBox()
        for name, field, value in [('Mín.', self.minimum, -1), ('Máx.', self.maximum, 1)]:
            field.setRange(-1e12, 1e12)
            field.setDecimals(6)
            field.setValue(value)
            field.setEnabled(False)
            scale.addWidget(QLabel(name))
            scale.addWidget(field)
            field.valueChanged.connect(self._limits_edited)
        layout.addLayout(scale)
        self.canvas = ChannelCanvas(color)
        layout.addWidget(self.canvas, 1)
        self.message = QLabel('Tempo desde o início (s)')
        layout.addWidget(self.message)
        self.auto.toggled.connect(self._toggle_auto)

    def _toggle_auto(self, automatic):
        self.minimum.setEnabled(not automatic)
        self.maximum.setEnabled(not automatic)
        self._limits_edited()

    def _limits_edited(self):
        self.refresh()
        if self.minimum.value() < self.maximum.value():
            self.limits_changed.emit(self.minimum.value(), self.maximum.value(), self.auto.isChecked())

    def set_limits(self, minimum, maximum, automatic):
        for widget in (self.minimum, self.maximum, self.auto):
            widget.blockSignals(True)
        self.minimum.setValue(minimum)
        self.maximum.setValue(maximum)
        self.auto.setChecked(automatic)
        self.minimum.setEnabled(not automatic)
        self.maximum.setEnabled(not automatic)
        for widget in (self.minimum, self.maximum, self.auto):
            widget.blockSignals(False)
        self.refresh()

    def refresh(self):
        if len(self.canvas.values) and len(self.canvas.times):
            value = float(self.canvas.values[-1])
            suffix = f' {self.unit}' if self.unit else ''
            number = f'{value:.6g}'.replace('.', ',') if math.isfinite(value) else 'Inválido'
            self.current_value.setText(number + suffix)
            self.value_time.setText(f'Última amostra · t = {self.canvas.times[-1]:.3f} s'.replace('.', ','))
        else:
            self.current_value.setText('—')
            self.value_time.setText('Aguardando amostras')
        if self.auto.isChecked():
            finite = self.canvas.values[np.isfinite(self.canvas.values)]
            if len(finite):
                low, high = float(finite.min()), float(finite.max())
                margin = max((high - low) * .05, abs(low) * .01, 1e-6)
                self.canvas.y_range = (low - margin, high + margin)
            self.message.setText('Tempo desde o início (s)')
        elif self.minimum.value() < self.maximum.value():
            self.canvas.y_range = (self.minimum.value(), self.maximum.value())
            self.message.setText('Tempo desde o início (s)')
        else:
            self.message.setText('O mínimo deve ser menor que o máximo. Escala anterior mantida.')
        self.canvas.update()


class PlotWindow(QMdiSubWindow):
    hidden_by_user = pyqtSignal()

    def closeEvent(self, event):
        # Closing a plot only hides it; the checkbox can restore it and its data.
        event.ignore()
        self.hidden_by_user.emit()


class PlotDashboard(QMdiArea):
    limits_changed = pyqtSignal(int, float, float, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setOption(QMdiArea.AreaOption.DontMaximizeSubWindowOnActivation, True)
        self.windows = []
        self.buffer = DisplayBuffer()
        self.panels = []
        self.origin = None
        self.dirty = False
        self.columns = 2
        self.channel_controls = QWidget()
        self.channel_layout = QGridLayout(self.channel_controls)
        self.channel_layout.setContentsMargins(0, 0, 0, 0)
        self.channel_checks = []
        self.channel_numbers = []
        self.visibility = {}
        self.live_status = QLabel('Aguardando amostras.')
        self.placeholder = QLabel('Inicie a aquisição para visualizar os canais selecionados.', self.viewport())
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setWordWrap(True)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.set_refresh_rate(10)

    def reset(self, channels):
        for window in self.windows:
            self.removeSubWindow(window)
            window.hide()
            window.deleteLater()
        self.windows = []
        self.panels = []
        for check in self.channel_checks:
            self.channel_layout.removeWidget(check)
            check.deleteLater()
        self.channel_checks = []
        self.channel_numbers = []
        self.placeholder.hide()
        self.live_status.setText('Aguardando amostras.')
        self.buffer.blocks.clear()
        self.origin = None
        for i, channel in enumerate(channels):
            panel = ChannelPlot(channel.label(), channel.unit, COLORS[i % len(COLORS)])
            panel.set_limits(channel.display_min, channel.display_max, channel.display_auto)
            panel.limits_changed.connect(lambda low, high, auto, number=channel.number: self.limits_changed.emit(number, low, high, auto))
            self.panels.append(panel)
            window = PlotWindow()
            window.setWidget(panel)
            window.setWindowTitle(f'CH {channel.number + 1} · {channel.label()}')
            window.setMinimumSize(380, 350)
            self.addSubWindow(window)
            window.hidden_by_user.connect(lambda index=i: self.set_channel_visible(index, False))
            self.windows.append(window)
            self.channel_numbers.append(channel.number)
            check = QCheckBox(f'CH {channel.number + 1} · {channel.label()}')
            check.setToolTip('Mostrar/ocultar apenas o gráfico. A aquisição e o CSV continuam para este canal.')
            check.setChecked(self.visibility.get(channel.number, True))
            self.channel_checks.append(check)
            self.channel_layout.addWidget(check, i // 4, i % 4)
            check.toggled.connect(lambda visible, index=i: self.set_channel_visible(index, visible))
        self.set_columns(self.columns)
        self.dirty = True

    def set_channel_visible(self, index, visible):
        check = self.channel_checks[index]
        check.blockSignals(True)
        check.setChecked(visible)
        check.blockSignals(False)
        self.visibility[self.channel_numbers[index]] = visible
        self.set_columns(self.columns)
        self.dirty = True
        self.refresh()

    def set_columns(self, columns):
        self.columns = columns
        visible_windows = []
        for i, window in enumerate(self.windows):
            visible = self.channel_checks[i].isChecked()
            self.panels[i].setVisible(visible)
            window.setVisible(visible)
            if visible:
                visible_windows.append(window)
        self.placeholder.setVisible(not visible_windows)
        if self.panels and not visible_windows:
            self.placeholder.setText('Todos os gráficos estão ocultos. Marque um canal acima para visualizá-lo.')
        if not visible_windows:
            return
        columns = min(columns, len(visible_windows))
        rows = math.ceil(len(visible_windows) / columns)
        width = max(380, self.viewport().width() // columns)
        height = max(350, self.viewport().height() // rows)
        for i, window in enumerate(visible_windows):
            window.showNormal()
            window.setGeometry((i % columns) * width, (i // columns) * height, width, height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'placeholder'):
            self.placeholder.setGeometry(self.viewport().rect())

    def set_window(self, seconds):
        self.buffer.seconds = seconds
        self.buffer.trim()
        self.dirty = True
        self.refresh()

    def set_refresh_rate(self, hz):
        self.timer.start(round(1000 / hz))

    def append(self, timestamps, values):
        if len(timestamps):
            if self.origin is None:
                self.origin = timestamps[0]
            self.buffer.append(np.asarray(timestamps) - self.origin, values)
            self.dirty = True

    def refresh(self):
        if not self.dirty:
            return
        times, values = self.buffer.snapshot()
        # Follow the newest sample from the first packet, preserving the chosen span.
        end = float(times[-1]) if len(times) else 0
        if len(times):
            self.live_status.setText(f'Última amostra: {end:.3f} s · janela acompanha os dados recebidos')
        for i, panel in enumerate(self.panels):
            if not self.channel_checks[i].isChecked():
                continue
            panel.canvas.times = times
            panel.canvas.values = values[i] if len(values) > i else np.array([])
            panel.canvas.x_range = (end - self.buffer.seconds, end)
            panel.refresh()
        self.dirty = False
