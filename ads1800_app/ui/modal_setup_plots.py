import numpy as np
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF

from ads1800_app.ui.plots import ChannelCanvas, envelope_indices


class WindowCanvas(ChannelCanvas):
    """The green region shows normalized window weight, independently of signal units."""
    def __init__(self, color='#2563eb'):
        super().__init__(color)
        self.window_times = np.array([])
        self.window_weights = np.array([])
        self.window_name = ''

    def paint_signal_region(self, painter):
        if not len(self.window_times) or len(self.window_times) != len(self.window_weights):
            return
        rect = self.plot_rect()
        x0, x1 = self.x_range
        y0, y1 = self.y_range
        baseline = float(np.clip(0, y0, y1))
        finite = self.values[np.isfinite(self.values)]
        negative = len(finite) and abs(float(np.min(finite))) > 2*max(float(np.max(finite)), 1e-20)
        extent = y0 if negative else y1
        def point(t, weight):
            level = baseline+np.clip(weight, 0, 1)*(extent-baseline)
            return QPointF(rect.left()+(t-x0)/(x1-x0)*rect.width(),
                           rect.bottom()-(level-y0)/(y1-y0)*rect.height())
        indices = envelope_indices(self.window_weights, max(1, int(rect.width())))
        region = [point(self.window_times[0], 0)]
        region.extend(point(self.window_times[i], self.window_weights[i]) for i in indices)
        region.append(point(self.window_times[-1], 0))
        painter.setPen(QPen(QColor(22, 163, 74, 130), 1))
        painter.setBrush(QColor(34, 197, 94, 42))
        painter.drawPolygon(QPolygonF(region))


class TriggerCanvas(WindowCanvas):
    def __init__(self):
        super().__init__('#2563eb')
        self.thresholds = []

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.y_range[1] <= self.y_range[0]:
            return
        p = QPainter(self)
        rect = self.plot_rect()
        p.setClipRect(rect)
        p.setPen(QPen(QColor('#ea580c'), 1, Qt.PenStyle.DashLine))
        for value in self.thresholds:
            y = rect.bottom()-(value-self.y_range[0])/(self.y_range[1]-self.y_range[0])*rect.height()
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
