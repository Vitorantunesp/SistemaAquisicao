"""Qt-native LSCF stabilization diagram; no nested matplotlib GUI/event loop."""
import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget, QToolTip


COLORS = {'novo': '#64748b', 'frequencia': '#2563eb',
          'frequencia_amortecimento': '#ea580c', 'estavel': '#16a34a'}
LABELS = {'novo': 'Novo/não repetido', 'frequencia': 'Frequência estável',
          'frequencia_amortecimento': 'Frequência e amortecimento estáveis',
          'estavel': 'Frequência, amortecimento e MAC estáveis'}


class StabilizationCanvas(QWidget):
    selection_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setMinimumSize(450, 340)
        self.setMouseTracking(True)
        self.result = None
        self.selected = set()
        self.locations = []

    def set_result(self, result):
        self.result = result
        self.selected = set(map(tuple, result.get('selected_poles', []))) if result else set()
        self.locations = []
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('white'))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.locations = []
        if not self.result or 'stabilization' not in self.result:
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Calcule com sdypy-EMA para exibir o diagrama LSCF.')
            return
        result = self.result
        orders = result['stabilization']['orders']
        rect = QRectF(65, 40, self.width()-90, self.height()-100)
        lo, hi = result['settings']['fmin'], result['settings']['fmax']
        ymax = max(row['order'] for row in orders)+2
        def point(f, order):
            return QPointF(rect.left()+(f-lo)/(hi-lo)*rect.width(), rect.bottom()-order/ymax*rect.height())
        p.setPen(QColor('#334155'))
        p.drawText(8, 20, 'Ordem dinâmica · LSCF (2 × ordem polinomial)')
        step = max(2, 2*int(np.ceil(ymax/24)))
        for order in range(0, ymax, step):
            y = point(lo, order).y()
            p.setPen(QColor('#e2e8f0'))
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            p.setPen(QColor('#334155'))
            p.drawText(QRectF(5, y-9, 50, 20), Qt.AlignmentFlag.AlignRight, str(order))
        for f in np.linspace(lo, hi, 5):
            x = point(f, 0).x()
            p.setPen(QColor('#e2e8f0'))
            p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            p.setPen(QColor('#334155'))
            p.drawText(QRectF(x-30, rect.bottom()+5, 60, 20), Qt.AlignmentFlag.AlignCenter, f'{f:.5g}')
        p.drawText(QRectF(rect.left(), rect.bottom()+26, rect.width(), 22), Qt.AlignmentFlag.AlignCenter, 'Frequência natural [Hz]')
        p.save()
        p.setClipRect(rect)
        for mode in result['modes']:
            x = point(mode['frequency_hz'], 0).x()
            p.setPen(QPen(QColor('#9333ea'), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        for row in orders:
            for mode in row['modes']:
                location = point(mode['frequency_hz'], row['order'])
                key = (mode['pole_order_index'], mode['pole_index'])
                p.setPen(QPen(QColor('#be123c' if key in self.selected else COLORS[mode['stability']]), 2))
                p.setBrush(QColor(COLORS[mode['stability']]))
                p.drawEllipse(location, 6 if key in self.selected else 3.5, 6 if key in self.selected else 3.5)
                self.locations.append((location, key, mode, row['order']))
        p.restore()

    def nearest(self, position):
        if not self.locations:
            return None
        item = min(self.locations, key=lambda item: (item[0].x()-position.x())**2+(item[0].y()-position.y())**2)
        return item if (item[0]-position).manhattanLength() < 15 else None

    def mouseMoveEvent(self, event):
        item = self.nearest(event.position())
        if item:
            _, _, mode, order = item
            mac = 'indisponível' if mode['mac'] is None else f"{mode['mac']:.4f}"
            QToolTip.showText(event.globalPosition().toPoint(),
                f"Ordem {order} · {mode['frequency_hz']:.5g} Hz · ζ {mode['damping_ratio']*100:.4g}%\n"
                f"{LABELS[mode['stability']]} · MAC: {mac}\nClique para marcar/desmarcar.\n"+'\n'.join(mode['warnings']), self)
        else:
            QToolTip.hideText()

    def mousePressEvent(self, event):
        item = self.nearest(event.position())
        if event.button() == Qt.MouseButton.LeftButton and item:
            key = item[1]
            self.selected.symmetric_difference_update([key])
            self.update()
            self.selection_changed.emit()
