"""Compact bridge dashboard with independent time, FFT and PSD canvases."""
import math
import numpy as np
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPointF, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QScrollArea, QToolButton
from ads1800_app.ui.plots import DisplayBuffer, ChannelCanvas, envelope_indices
from ads1800_app.monitor_signal import StreamingBandpass, spectra
from ads1800_app.ui.bridge_image import BridgeMap

COLORS = ('#1875ce', '#ef7e20', '#17954b', '#d93636', '#9845ca', '#955534', '#dd32ac', '#7b8794')


class BridgeCanvas(ChannelCanvas):
    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#f7f9fc'))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(65, 10, max(1, self.width() - 95), max(1, self.height() - 36))
        x0, x1 = self.x_range
        y0, y1 = self.y_range
        for fraction in (0, .5, 1):
            y = rect.top() + fraction * rect.height()
            p.setPen(QColor('#dde4ec'))
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            p.setPen(QColor('#475569'))
            p.drawText(QRectF(0, y - 8, 58, 16), Qt.AlignmentFlag.AlignRight, f'{y1 - fraction * (y1 - y0):.3g}')
        for fraction in (0, .25, .5, .75, 1):
            x = rect.left() + fraction * rect.width()
            p.setPen(QColor('#dde4ec'))
            p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            p.setPen(QColor('#475569'))
            p.drawText(QRectF(x - 30, rect.bottom() + 4, 60, 18), Qt.AlignmentFlag.AlignCenter, f'{x0 + fraction * (x1 - x0):.3g}')
        if not len(self.times):
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, 'Aguardando amostras...')
            return
        p.setClipRect(rect)
        p.setPen(QPen(QColor(self.color), 1.4))
        points = QPolygonF()
        for i in envelope_indices(self.values, max(1, int(rect.width()))):
            if not np.isfinite(self.values[i]):
                p.drawPolyline(points)
                points = QPolygonF()
                continue
            points.append(QPointF(rect.left() + (self.times[i] - x0) / (x1 - x0) * rect.width(),
                                  rect.bottom() - (self.values[i] - y0) / (y1 - y0) * rect.height()))
        p.drawPolyline(points)


class MonitorPanel(QWidget):
    def __init__(self, channel, color):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet('MonitorPanel {background: #f7f9fc; border-radius: 6px;} QLabel {color: #172b40;}')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)
        self.title = QLabel(f'● CH {channel.number + 1} — {channel.label()} [{channel.unit}]')
        self.title.setStyleSheet(f'color: {color}; font-weight: 700;')
        layout.addWidget(self.title)
        self.stats = QLabel('RMS: —     Pico absoluto: —     Média: —')
        layout.addWidget(self.stats)
        self.plots = []
        self.captions = []
        self.scale_buttons = []
        self.time_limits = None
        low, high = channel.engineering_min, channel.engineering_max
        # Engineering limits describe the time-domain signal, not FFT amplitude or PSD.
        if low is not None and high is not None and math.isfinite(low) and math.isfinite(high) and low != high:
            self.time_limits = tuple(sorted((low, high)))
        self.plot_row = QHBoxLayout()
        layout.addLayout(self.plot_row)
        for caption in (f'Tempo (s) · {channel.unit}', f'FFT · Hz / amplitude ({channel.unit})',
                        f'Espectro PSD · Hz / ({channel.unit})²/Hz'):
            holder = QWidget()
            col = QVBoxLayout(holder)
            col.setContentsMargins(0, 0, 0, 0)
            canvas = BridgeCanvas(color)
            canvas.manual_y_range = None
            canvas.default_y_range = self.time_limits if not self.plots and self.time_limits else (-1., 1.)
            canvas.y_range = canvas.default_y_range
            canvas.setMinimumSize(230, 78)
            col.addWidget(canvas)
            label = QLabel(caption)
            col.addWidget(label)
            scale = QHBoxLayout()
            scale.addWidget(QLabel('Zoom Y'))
            buttons = {}
            for text, factor, hint in (
                    ('+', .5, 'Ampliar verticalmente: reduzir a faixa do eixo Y pela metade'),
                    ('−', 2., 'Reduzir verticalmente: dobrar a faixa do eixo Y'),
                    ('Restaurar', None, 'Restaurar a escala inicial: limites do canal no tempo; automática na FFT e PSD')):
                button = QToolButton()
                button.setText(text)
                button.setToolTip(hint)
                button.clicked.connect(lambda checked=False, c=canvas, f=factor: self.zoom_vertical(c, f))
                scale.addWidget(button)
                buttons[text] = button
            scale.addStretch()
            col.addLayout(scale)
            self.scale_buttons.append(buttons)
            self.captions.append(label)
            self.plots.append((holder, canvas))
            self.plot_row.addWidget(holder)
        self.set_mode('Tempo')

    def set_mode(self, mode):
        for (holder, _), name in zip(self.plots, ('Tempo', 'FFT', 'Espectro')):
            holder.setVisible(mode == name or mode == 'Todos')
        self.setMinimumHeight(144)

    @staticmethod
    def zoom_vertical(canvas, factor):
        if factor is None:
            canvas.manual_y_range = None
            canvas.y_range = canvas.default_y_range
        else:
            low, high = canvas.y_range
            center = low / 2 + high / 2
            half = (high - low) * factor / 2
            bounds = (center - half, center + half)
            if not all(math.isfinite(v) for v in bounds) or bounds[0] >= bounds[1]:
                return
            canvas.manual_y_range = canvas.y_range = bounds
        canvas.update()

    @staticmethod
    def draw(canvas, x, y, limits, engineering_limits=None):
        canvas.times, canvas.values, canvas.x_range = x, y, limits
        finite = y[np.isfinite(y) & (x >= limits[0]) & (x <= limits[1])]
        if engineering_limits is not None:
            canvas.default_y_range = engineering_limits
        elif len(finite):
            low, high = float(finite.min()), float(finite.max())
            margin = max((high - low) * .08, abs(low) * .01, 1e-9)
            canvas.default_y_range = (low - margin, high + margin)
        else:
            canvas.default_y_range = (-1., 1.)
        canvas.y_range = canvas.manual_y_range or canvas.default_y_range
        canvas.update()


class BridgeDashboard(QScrollArea):
    limits_changed = pyqtSignal(int, float, float, bool)

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.content = QWidget()
        self.grid = QGridLayout(self.content)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setWidget(self.content)
        self.buffer = DisplayBuffer(20)
        self.panels = []
        self.channels = []
        self.origin = None
        self.last_timestamp = None
        self.sample_rate = 1000
        self.frequency_max = 500
        self.filter = None
        self.mode = 'Tempo'
        self.columns = 2
        self.dirty = False
        self.channel_controls = QWidget()
        self.live_status = QLabel('Aguardando amostras.')
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.set_refresh_rate(10)

    def configure(self, config):
        self.sample_rate = config.sample_rate
        self.frequency_max = config.high_cut if config.bandpass_enabled else config.sample_rate / 2
        self.filter = (StreamingBandpass(config.sample_rate, config.low_cut, config.high_cut,
                                        len(config.enabled_channels)) if config.bandpass_enabled else None)

    def reset(self, channels):
        for panel in self.panels:
            self.grid.removeWidget(panel)
            panel.deleteLater()
        self.channels = list(channels)
        self.panels = [MonitorPanel(ch, COLORS[i % 8]) for i, ch in enumerate(channels)]
        self.origin = self.last_timestamp = None
        if self.filter:
            self.filter.reset()
        self.clear()
        self.set_columns(self.columns)
        self.set_mode(self.mode)

    def clear(self):
        # Keep time origin and causal filter state when clearing only the display.
        self.buffer.blocks.clear()
        self.dirty = True
        self.refresh()

    def set_columns(self, columns):
        self.columns = columns
        for panel in self.panels:
            self.grid.removeWidget(panel)
        rows = math.ceil(len(self.panels) / columns) if self.panels else 1
        for i, panel in enumerate(self.panels):
            self.grid.addWidget(panel, i % rows, i // rows)

    def set_mode(self, mode):
        self.mode = mode
        for panel in self.panels:
            panel.set_mode(mode)
        self.dirty = True
        self.refresh()

    def set_window(self, seconds):
        self.buffer.seconds = seconds
        self.buffer.trim()
        self.dirty = True
        self.refresh()

    def set_refresh_rate(self, hz):
        self.timer.start(round(1000 / hz))

    def append(self, timestamps, values):
        t = np.asarray(timestamps, dtype=float)
        if not len(t):
            return
        x = np.asarray(values, dtype=float)
        if self.origin is None:
            self.origin = t[0]
        # Start a fresh display interval after a timing discontinuity. No FFT over gaps.
        gaps = np.flatnonzero(np.abs(np.diff(t) - 1 / self.sample_rate) > .5 / self.sample_rate)
        discontinuity = self.last_timestamp is not None and abs(t[0] - self.last_timestamp - 1 / self.sample_rate) > .5 / self.sample_rate
        if len(gaps) or discontinuity:
            self.buffer.blocks.clear()
            if self.filter:
                self.filter.reset()
            if len(gaps):
                start = gaps[-1] + 1
                t, x = t[start:], x[:, start:]
        self.last_timestamp = t[-1]
        self.buffer.append(t - self.origin, self.filter.apply(x) if self.filter else x)
        self.dirty = True

    def refresh(self):
        if not self.dirty:
            return
        times, values = self.buffer.snapshot()
        end = float(times[-1]) if len(times) else 0
        self.live_status.setText(f'Última amostra: {end:.3f} s • ' + ('Passa-banda ativo' if self.filter else 'Sem filtro'))
        for i, panel in enumerate(self.panels):
            y = values[i] if len(values) > i else np.array([])
            finite = y[np.isfinite(y)]
            panel.stats.setText(f'RMS: {np.sqrt(np.mean(finite ** 2)):.4g}     Pico absoluto: {np.max(np.abs(finite)):.4g}     Média: {np.mean(finite):.4g}' if len(finite) else 'RMS: —     Pico absoluto: —     Média: —')
            panel.draw(panel.plots[0][1], times, y, (end - self.buffer.seconds, end), panel.time_limits)
            if self.mode != 'Tempo':
                # Use only the contiguous finite tail for spectral estimates.
                invalid = np.flatnonzero(~np.isfinite(y))
                tail = y[invalid[-1] + 1:] if len(invalid) else y
                f, a, pf, psd = spectra(tail, self.sample_rate)
                panel.draw(panel.plots[1][1], f, a, (0, self.frequency_max))
                panel.draw(panel.plots[2][1], pf, psd, (0, self.frequency_max))
        self.dirty = False
