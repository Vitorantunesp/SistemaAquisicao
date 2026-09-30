"""Photographic bridge map; marker coordinates are normalized to the image."""
import hashlib
import json
import math
from pathlib import Path
import shutil

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImageReader, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QWidget

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IMAGE = 'assets/ponte_sem_fundo.png'
COLORS = ('#1875ce', '#ef7e20', '#17954b', '#d93636', '#9845ca', '#955534', '#dd32ac', '#7b8794')


def validate_positions(positions):
    if not isinstance(positions, dict):
        raise ValueError('As posições dos sensores devem ser um mapa por canal.')
    for key, xy in positions.items():
        if (not isinstance(key, str) or not key.isdecimal() or not isinstance(xy, (list, tuple))
                or len(xy) != 2 or any(not isinstance(v, (int, float)) or not math.isfinite(v)
                                      or not 0 <= v <= 1 for v in xy)):
            raise ValueError('Posição inválida: use o número do canal e coordenadas entre 0 e 1.')


def resolve_image(path):
    path = Path(path or DEFAULT_IMAGE)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_pixmap(path):
    reader = QImageReader(str(resolve_image(path)))
    reader.setAutoTransform(True)
    size = reader.size()
    if size.width() * size.height() > 40_000_000:
        raise ValueError('Imagem muito grande. Use uma imagem com até 40 megapixels.')
    image = reader.read()
    if image.isNull():
        raise ValueError('Não foi possível abrir a imagem da ponte. Selecione um PNG ou JPG válido.')
    return QPixmap.fromImage(image)


def import_image(path):
    path = Path(path)
    if path.suffix.lower() not in ('.png', '.jpg', '.jpeg'):
        raise ValueError('Selecione uma imagem PNG ou JPG.')
    load_pixmap(path)  # Validate before storing any new preference.
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    relative = f'assets/ponte_{digest}{path.suffix.lower()}'
    destination = PROJECT_ROOT / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copy2(path, destination)
    return relative


def save_preferences(path, image, positions):
    validate_positions(positions)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'bridge_image': image, 'sensor_positions': positions},
                                    ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


class BridgeMap(QWidget):
    positions_changed = pyqtSignal()

    def __init__(self, editable=False):
        super().__init__()
        self.channels = []
        self.positions = {}
        self.pixmap = QPixmap()
        self.editable = editable
        self.dragging = None
        self.setMinimumSize(340, 240)
        self.setMouseTracking(True)

    def set_image(self, path):
        pixmap = load_pixmap(path)
        self.pixmap = pixmap
        self.update()

    def set_positions(self, positions):
        validate_positions(positions)
        self.positions = {key: list(xy) for key, xy in positions.items()}
        self.update()

    def image_rect(self):
        area = QRectF(18, 26, max(1, self.width() - 36), max(1, self.height() - 54))
        if self.pixmap.isNull():
            return area
        scale = min(area.width() / self.pixmap.width(), area.height() / self.pixmap.height())
        w, h = self.pixmap.width() * scale, self.pixmap.height() * scale
        return QRectF(area.center().x() - w / 2, area.center().y() - h / 2, w, h)

    def marker_position(self, number):
        # Initial positions are explicitly provisional, stable even if channels are hidden.
        x = .10 + .80 * (number % 8) / 7
        xy = self.positions.get(str(number), (x, .40 + .44 * (number % 8) / 7))
        rect = self.image_rect()
        return QPointF(rect.left() + xy[0] * rect.width(), rect.top() + xy[1] * rect.height())

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.image_rect()
        if not self.pixmap.isNull():
            p.drawPixmap(rect, self.pixmap, QRectF(self.pixmap.rect()))
        else:
            p.setPen(QColor('#c7d8e3'))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, 'Selecione uma imagem em Configurações')
        for i, channel in enumerate(self.channels):
            pos = self.marker_position(channel.number)
            color = QColor(COLORS[i % len(COLORS)])
            p.setBrush(color)
            p.setPen(QPen(QColor('white'), 2))
            p.drawEllipse(pos, 8, 8)
            if self.editable:
                label = QRectF(min(max(0, pos.x() - 27), self.width() - 56), max(0, pos.y() - 32), 54, 20)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor('#102432'))
                p.drawRoundedRect(label, 3, 3)
                p.setPen(QColor('white'))
                p.drawText(label, Qt.AlignmentFlag.AlignCenter, f'CH {channel.number + 1}')
        pending = any(str(ch.number) not in self.positions for ch in self.channels)
        message = ('Arraste os marcadores para as posições dos sensores' if self.editable else
                   'Posições iniciais sugeridas • ajuste em Configurações' if pending else 'Posições definidas pelo usuário')
        p.setPen(QColor('#b5cbd9'))
        p.drawText(QRectF(0, self.height() - 22, self.width(), 20), Qt.AlignmentFlag.AlignCenter, message)

    def mousePressEvent(self, event):
        if self.editable and event.button() == Qt.MouseButton.LeftButton:
            for channel in reversed(self.channels):
                delta = event.position() - self.marker_position(channel.number)
                if delta.x() ** 2 + delta.y() ** 2 <= 18 ** 2:
                    self.dragging = channel.number
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.dragging is not None:
            rect = self.image_rect()
            self.positions[str(self.dragging)] = [
                min(1., max(0., (event.position().x() - rect.left()) / rect.width())),
                min(1., max(0., (event.position().y() - rect.top()) / rect.height()))]
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.dragging is not None and event.button() == Qt.MouseButton.LeftButton:
            self.mouseMoveEvent(event)
            self.dragging = None
            self.unsetCursor()
            self.positions_changed.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)
