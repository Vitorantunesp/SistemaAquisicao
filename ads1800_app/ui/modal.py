"""Standalone modal test application using the current ADS1800 backend."""
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
import json
import queue
import sys
import threading
import uuid

import numpy as np
from PyQt6.QtCore import QPointF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QSpinBox, QTabWidget, QTextEdit,
    QVBoxLayout, QWidget, QSplitter, QTableWidget, QTableWidgetItem)

from ads1800_app.backends.lynx import LynxBackend
from ads1800_app.backends.modal_simulator import ModalSimulatorBackend
from ads1800_app.config import ADS1800_SAMPLE_RATES, ExperimentConfig
from ads1800_app.controller import AcquisitionController
from ads1800_app.modal import ModalConfig, ImpactCapture, ModalSession, ensemble, processed_signals
from ads1800_app.monitor_signal import StreamingBandpass
from ads1800_app.ui.plots import ChannelCanvas, DisplayBuffer
from ads1800_app.ui.modal_post import PostPanel


class Geometry(QWidget):
    def __init__(self):
        super().__init__()
        self.config = ModalConfig()
        self.selected = 'P1'
        self.setMinimumSize(280, 180)

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#f8fafc'))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = self.config
        xy = np.asarray([*c.outline, *[v[1:] for v in c.points], c.accelerometer], float)
        low, high = xy.min(axis=0), xy.max(axis=0)
        span = np.maximum(high-low, 1e-6)
        scale = min((self.width()-70)/span[0], (self.height()-65)/span[1])
        def pos(v):
            return QPointF(35+(v[0]-low[0])*scale, self.height()-35-(v[1]-low[1])*scale)
        p.setPen(QPen(QColor('#64748b'), 2))
        p.setBrush(QColor('#e2e8f0'))
        p.drawPolygon(QPolygonF([pos(v) for v in c.outline]))
        for name, x, y in c.points:
            point = pos([x, y])
            p.setBrush(QColor('#f97316' if name == self.selected else '#2563eb'))
            p.drawEllipse(point, 5, 5)
            p.drawText(point+QPointF(7, -7), name)
        point = pos(c.accelerometer)
        p.setPen(QPen(QColor('#16a34a'), 3))
        p.drawLine(point+QPointF(-7, -7), point+QPointF(7, 7))
        p.drawLine(point+QPointF(-7, 7), point+QPointF(7, -7))
        p.drawText(point+QPointF(9, 17), 'A fixo')
        p.drawText(8, 17, 'Plano XY [m] · força e aceleração em +Z')


class ModalApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Análise modal — Roving hammer | ADS 1800')
        self.resize(1440, 940)
        self.backend = self.controller = self.capture = self.session = None
        self.pending = None
        self.channels = []
        self.busy = False
        self.events = queue.Queue(maxsize=300)
        self.live = DisplayBuffer(2)
        self.live_filter = None
        self.lost = 0
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.make_settings()
        self.make_acquisition()
        self.post = PostPanel(self)
        self.tabs.addTab(self.post, '3. Pós-processamento modal')
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.process)
        self.timer.start(40)
        self.refresh()

    def button(self, text, callback, layout):
        button = QPushButton(text)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def number(self, default, low, high, decimals=4):
        box = QDoubleSpinBox()
        box.setDecimals(decimals)
        box.setRange(low, high)
        box.setValue(default)
        return box

    def make_settings(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        self.tabs.addTab(scroll, '1. Configuração do ensaio')
        layout = QVBoxLayout(content)
        row = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(['Simulador modal', 'ADS 1800 real'])
        self.ip = QLineEdit('192.168.1.180')
        row.addWidget(self.mode)
        row.addWidget(self.ip)
        self.connect_button = self.button('Conectar', self.connect_device, row)
        self.connection = QLabel('Desconectado')
        row.addWidget(self.connection)
        layout.addLayout(row)
        self.settings = QWidget()
        grid = QGridLayout(self.settings)
        layout.addWidget(self.settings)
        form = QFormLayout()
        grid.addLayout(form, 0, 0)
        self.fields = {}
        c = ModalConfig()
        for key, label, low, high in [
            ('duration', 'Registro total [s]', .01, 600), ('pretrigger', 'Pré-trigger [s]', .001, 60),
            ('threshold', 'Trigger de força [N]', .0001, 1e9), ('force_width', 'Janela de força após trigger [s]', .0001, 60),
            ('exponential_end', 'Resíduo exponencial final (0–1)', .0001, 1),
            ('force_factor', 'Fator: unidade do canal → N', -1e9, 1e9),
            ('response_factor', 'Fator: unidade do canal → m/s²', -1e9, 1e9)]:
            self.fields[key] = self.number(getattr(c, key), low, high)
            form.addRow(label, self.fields[key])
        self.rate = QComboBox()
        self.rate.addItems([str(v) for v in ADS1800_SAMPLE_RATES])
        self.rate.setCurrentText('2000')
        form.insertRow(0, 'Amostragem [Hz]', self.rate)
        self.bandpass = QCheckBox('Ativar filtro passa-banda em todos os resultados')
        self.bandpass.setChecked(True)
        form.addRow(self.bandpass)
        for key, label, default in [('low_cut', 'Corte inferior [Hz]', 1), ('high_cut', 'Corte superior [Hz]', 500)]:
            self.fields[key] = self.number(default, .0001, 1e6)
            form.addRow(label, self.fields[key])
            self.bandpass.toggled.connect(self.fields[key].setEnabled)
        for key, label, items in [('polarity', 'Polaridade do trigger', ['Absoluto', 'Positivo', 'Negativo']),
                                 ('force_window', 'Janela do martelo', ['Força', 'Retangular', 'Hann']),
                                 ('response_window', 'Janela da aceleração', ['Exponencial', 'Retangular', 'Hann'])]:
            box = QComboBox()
            box.addItems(items)
            self.fields[key] = box
            form.addRow(label, box)
        self.averages = QSpinBox()
        self.averages.setRange(2, 10000)
        self.averages.setValue(3)
        form.addRow('Meta de batidas aceitas por ponto', self.averages)
        self.force_channel, self.response_channel = QComboBox(), QComboBox()
        form.addRow('Canal do martelo', self.force_channel)
        form.addRow('Canal do acelerômetro fixo', self.response_channel)
        shape = QFormLayout()
        grid.addLayout(shape, 0, 1)
        self.outline = QTextEdit()
        self.points = QTextEdit()
        self.outline.setPlainText('0; 0\n1; 0\n1; 0.5\n0; 0.5')
        self.points.setPlainText('P1; 0.1; 0.25\nP2; 0.5; 0.25\nP3; 0.9; 0.25')
        self.outline.setMaximumHeight(130)
        self.points.setMinimumHeight(170)
        shape.addRow('Contorno: x; y [m], um vértice por linha', self.outline)
        shape.addRow('Impactos: nome; x; y [m], um ponto por linha', self.points)
        self.ax, self.ay = self.number(.5, -1e6, 1e6), self.number(.25, -1e6, 1e6)
        shape.addRow('Acelerômetro fixo — X [m]', self.ax)
        shape.addRow('Acelerômetro fixo — Y [m]', self.ay)
        self.preview = Geometry()
        shape.addRow(self.preview)
        self.button('Atualizar desenho', self.preview_geometry, shape)
        note = QLabel('Configure sensores e faixas no Assistente LYNX. Os canais já chegam em unidades de engenharia; '
                      'os fatores acima convertem apenas para SI (ex.: g → m/s²: 9,80665).\n'
                      'Janela exponencial altera o amortecimento aparente. Hann pode atenuar o impacto; '
                      'use retangular quando toda a resposta já decai dentro do registro.\n'
                      'Passa-banda: corte superior deve ser menor que metade da amostragem. '
                      'Para 1–500 Hz, use mais de 1000 amostras/s (padrão: 2000). Trigger e alertas da batida usam o sinal original.')
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        self.button('Salvar configuração…', self.save_config, row)
        self.button('Carregar configuração…', self.load_config, row)
        self.open_button = self.button('Abrir ensaio salvo…', self.open_session, row)
        layout.addLayout(row)
        self.start_button = self.button('Iniciar novo ensaio…', self.start, layout)

    def make_acquisition(self):
        widget = QWidget()
        self.tabs.addTab(widget, '2. Impactos e resultados')
        layout = QVBoxLayout(widget)
        row = QHBoxLayout()
        self.point = QComboBox()
        self.point.currentTextChanged.connect(self.point_changed)
        row.addWidget(QLabel('Ponto da batida:'))
        row.addWidget(self.point)
        self.arm_button = self.button('Armar trigger', self.arm, row)
        self.cancel_button = self.button('Cancelar espera', self.cancel, row)
        self.accept_button = self.button('Aceitar batida', lambda: self.review(True), row)
        self.reject_button = self.button('Rejeitar batida', lambda: self.review(False), row)
        self.stop_button = self.button('Parar aquisição', self.stop, row)
        layout.addLayout(row)
        self.status = QLabel('Inicie um ensaio na configuração.')
        self.status.setWordWrap(True)
        self.status.setMaximumHeight(55)
        layout.addWidget(self.status)
        splitter = QSplitter()
        left = QWidget()
        left.setMaximumWidth(450)
        side = QVBoxLayout(left)
        self.geometry = Geometry()
        side.addWidget(self.geometry)
        self.progress = QLabel('0 batidas')
        side.addWidget(self.progress)
        self.history = QTableWidget(0, 4)
        self.history.setHorizontalHeaderLabels(['Ponto', 'Estado', 'Pico [N]', 'Qualidade'])
        self.history.horizontalHeader().setStretchLastSection(True)
        self.history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history.cellClicked.connect(self.inspect)
        side.addWidget(self.history)
        self.folder = QLabel('Os sinais de cada batida serão salvos automaticamente.')
        self.folder.setWordWrap(True)
        self.folder.setMinimumWidth(0)
        self.folder.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        side.addWidget(self.folder)
        self.button('Exportar sinais da batida selecionada…', self.export_hit, side)
        splitter.addWidget(left)
        right = QWidget()
        plots = QGridLayout(right)
        self.plots = {}
        for index, (key, label) in enumerate([
            ('force', 'Força [N] × tempo [s]'), ('frf', 'FRF H1 — módulo [(m/s²)/N] × Hz'),
            ('acceleration', 'Aceleração [m/s²] × tempo [s]'), ('phase', 'FRF H1 — fase [graus] × Hz'),
            ('fft_force', 'FFT da força janelada — amplitude [N] × Hz'), ('coherence', 'Coerência (≥2 batidas aceitas) × Hz'),
            ('fft_acceleration', 'FFT da aceleração janelada — amplitude [m/s²] × Hz')]):
            panel = QWidget()
            box = QVBoxLayout(panel)
            box.setContentsMargins(0, 0, 0, 0)
            box.addWidget(QLabel(label))
            canvas = ChannelCanvas('#2563eb' if index % 2 == 0 else '#16a34a')
            canvas.x_label = 'Tempo [s]' if key in ('force', 'acceleration') else 'Frequência [Hz]'
            canvas.setMinimumSize(260, 140)
            box.addWidget(canvas)
            self.plots[key] = canvas
            plots.addWidget(panel, index//2, index % 2)
        self.quality = QLabel('Qualidade: aguardando batida.\nClique em uma captura para rever seus sinais.')
        self.quality.setWordWrap(True)
        plots.addWidget(self.quality, 3, 1)
        splitter.addWidget(right)
        splitter.setSizes([340, 1050])
        layout.addWidget(splitter)

    def error(self, exc):
        self.status.setText(str(exc))
        QMessageBox.critical(self, 'Análise modal', str(exc))

    def work(self, action, done):
        self.busy = True
        self.refresh()
        def worker():
            try:
                self.events.put(('done', done, action()))
            except Exception as exc:
                self.events.put(('error', exc))
        threading.Thread(target=worker, daemon=True).start()

    def connect_device(self):
        if self.backend:
            backend = self.backend
            def disconnected(_):
                self.backend = self.controller = None
                self.connection.setText('Desconectado')
            self.work(backend.disconnect, disconnected)
            return
        backend = ModalSimulatorBackend() if self.mode.currentIndex() == 0 else LynxBackend()
        def connected(info):
            self.backend = backend
            self.channels = info.channels
            self.connection.setText(info.name)
            for combo in (self.force_channel, self.response_channel):
                combo.clear()
                for ch in self.channels:
                    combo.addItem(f'CH {ch.number+1}: {ch.name} [{ch.unit}]', ch.number)
            self.response_channel.setCurrentIndex(min(1, len(self.channels)-1))
            previous = self.rate.currentText()
            self.rate.clear()
            self.rate.addItems([f'{r:g}' for r in info.available_sample_rates or ADS1800_SAMPLE_RATES])
            self.rate.setCurrentText(previous)
        self.work(lambda: backend.connect(self.ip.text()), connected)

    def read_config(self, require_channels=False):
        values = {k: w.currentText() if isinstance(w, QComboBox) else w.value() for k, w in self.fields.items()}
        def rows(text, names=False):
            result = []
            for line in text.toPlainText().splitlines():
                if not line.strip():
                    continue
                items = [v.strip() for v in line.split(';')]
                if len(items) != (3 if names else 2):
                    raise ValueError('Use ponto e vírgula para separar as coordenadas.')
                result.append(([items[0]] if names else [])+[float(v.replace(',', '.')) for v in items[1 if names else 0:]])
            return result
        c = ModalConfig(**values, bandpass_enabled=self.bandpass.isChecked(), sample_rate=float(self.rate.currentText()), averages=self.averages.value(),
                        outline=rows(self.outline), points=rows(self.points, True), accelerometer=[self.ax.value(), self.ay.value()],
                        force_channel=self.force_channel.currentData() if self.force_channel.count() else 0,
                        response_channel=self.response_channel.currentData() if self.response_channel.count() else 1)
        if require_channels:
            by_id = {ch.number: ch for ch in self.channels}
            for key, factor in [('force', c.force_factor), ('response', c.response_factor)]:
                ch = by_id[getattr(c, key+'_channel')]
                if ch.engineering_min is not None and ch.engineering_max is not None:
                    setattr(c, key+'_limits', sorted([ch.engineering_min*factor, ch.engineering_max*factor]))
        c.validate()
        return c

    def preview_geometry(self):
        try:
            self.preview.config = self.read_config()
            self.preview.update()
        except Exception as exc:
            self.error(exc)

    def save_config(self):
        try:
            c = self.read_config()
            path, _ = QFileDialog.getSaveFileName(self, 'Salvar configuração modal', 'modal.json', 'JSON (*.json)')
            if path:
                Path(path).write_text(json.dumps(asdict(c), ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as exc:
            self.error(exc)

    def load_config(self):
        if self.busy or self.controller and self.controller.running:
            return
        if not self.backend:
            self.error(ValueError('Conecte ao equipamento ou simulador antes de carregar a configuração, para conferir os canais.'))
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Carregar configuração modal', '', 'JSON (*.json)')
        if not path:
            return
        try:
            c = ModalConfig.from_dict(json.loads(Path(path).read_text(encoding='utf-8')))
            c.validate()
            if self.rate.findText(f'{c.sample_rate:g}') < 0:
                raise ValueError('Taxa da configuração não disponível; conecte ao equipamento correspondente.')
            if any(combo.findData(channel) < 0 for combo, channel in [(self.force_channel, c.force_channel), (self.response_channel, c.response_channel)]):
                raise ValueError('Canais da configuração não estão disponíveis neste equipamento.')
            for key, widget in self.fields.items():
                if isinstance(widget, QComboBox):
                    widget.setCurrentText(getattr(c, key))
                else:
                    widget.setValue(getattr(c, key))
            self.rate.setCurrentText(f'{c.sample_rate:g}')
            self.bandpass.setChecked(c.bandpass_enabled)
            self.averages.setValue(c.averages)
            self.outline.setPlainText('\n'.join('; '.join(map(str, row)) for row in c.outline))
            self.points.setPlainText('\n'.join('; '.join(map(str, row)) for row in c.points))
            self.ax.setValue(c.accelerometer[0])
            self.ay.setValue(c.accelerometer[1])
            for combo, channel in [(self.force_channel, c.force_channel), (self.response_channel, c.response_channel)]:
                if combo.findData(channel) >= 0:
                    combo.setCurrentIndex(combo.findData(channel))
            self.preview_geometry()
        except Exception as exc:
            self.error(exc)

    def open_session(self):
        directory = QFileDialog.getExistingDirectory(self, 'Abrir pasta do ensaio (session.json)')
        if not directory:
            return
        try:
            session = ModalSession.load(directory)
            self.capture = None
            self.pending = None
            self.session = session
            self.post.set_session(session)
            self.point.clear()
            self.point.addItems([p[0] for p in session.config.points])
            self.geometry.config = session.config
            self.geometry.update()
            self.folder.setText(str(session.directory))
            self.update_history()
            self.results()
            if session.records:
                self.show_hit(session.records[-1])
            self.tabs.setCurrentIndex(1)
            self.status.setText('Ensaio salvo aberto. Clique nas capturas para revisar; decisões atualizam as médias e os arquivos.')
        except Exception as exc:
            self.error(exc)
        self.refresh()

    def start(self):
        try:
            c = self.read_config(True)
            directory = QFileDialog.getExistingDirectory(self, 'Pasta para o novo ensaio')
            if not directory:
                return
            selected = [replace(ch, enabled=True) for ch in self.channels if ch.number in (c.force_channel, c.response_channel)]
            config = ExperimentConfig(name='Ensaio modal', device_ip=self.ip.text(), sample_rate=c.sample_rate, channels=selected)
            path = Path(directory)/f'modal_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}'
            self.session = ModalSession(path, c, {'mode': self.mode.currentText(), 'device_ip': self.ip.text(),
                                                 'channels': [asdict(ch) for ch in selected]})
            self.post.set_session(self.session)
            self.capture = ImpactCapture(c)
            self.indices = ([ch.number for ch in selected].index(c.force_channel), [ch.number for ch in selected].index(c.response_channel))
            self.pending = None
            self.live = DisplayBuffer(2)
            self.live_filter = StreamingBandpass(c.sample_rate, c.low_cut, c.high_cut, 2) if c.bandpass_enabled else None
            self.history.setRowCount(0)
            for canvas in self.plots.values():
                canvas.times, canvas.values = np.array([]), np.array([])
                canvas.update()
            self.point.clear()
            self.point.addItems([p[0] for p in c.points])
            self.geometry.config = c
            self.geometry.update()
            self.folder.setText(str(path))
            self.controller = AcquisitionController(self.backend,
                lambda times, values: self.events.put_nowait(('data', times, values)),
                lambda exc: self.events.put(('acquisition_error', exc)))
            if isinstance(self.backend, ModalSimulatorBackend):
                self.backend.period = c.duration+1
            def started(_):
                self.lost = self.backend.samples_lost()
                self.tabs.setCurrentIndex(1)
                self.status.setText('Selecione o ponto e arme o trigger. Cada batida aguarda aceitação ou rejeição.')
            self.work(lambda: self.controller.start(config), started)
        except Exception as exc:
            self.error(exc)

    def arm(self):
        self.capture.arm(self.point.currentText())
        self.pending = None
        self.status.setText('Armado: aguardando cruzamento do limiar de força após retornar abaixo de 50% do trigger.')
        self.refresh()

    def cancel(self):
        self.capture.cancel()
        self.status.setText('Espera cancelada; registro incompleto descartado.')
        self.refresh()

    def stop(self):
        self.capture.cancel()
        self.work(self.controller.stop, lambda _: self.status.setText('Aquisição encerrada. Resultados salvos; capturas pendentes ainda podem ser revisadas.'))

    def plot(self, key, x, y, fixed=None):
        canvas = self.plots[key]
        x, y = np.asarray(x), np.asarray(y)
        spectral = key in ('fft_force', 'fft_acceleration', 'frf', 'phase', 'coherence')
        if spectral and self.session and self.session.config.bandpass_enabled:
            maximum = self.session.config.high_cut
            visible = (x >= 0) & (x <= maximum)
            x, y = x[visible], y[visible]
            canvas.x_range = (0, maximum)
        elif len(x) > 1:
            canvas.x_range = (float(x[0]), float(x[-1]))
        canvas.times, canvas.values = x, y
        valid = np.asarray(y)[np.isfinite(y)]
        if fixed:
            canvas.y_range = fixed
        elif len(valid):
            low, high = float(valid.min()), float(valid.max())
            margin = max((high-low)*.08, abs(high)*.01, 1e-12)
            canvas.y_range = (low-margin, high+margin)
        canvas.update()

    def show_hit(self, record):
        c = self.session.config
        with np.load(self.session.directory/record['file']) as d:
            t = (np.arange(c.n)-c.pre)/c.sample_rate
            force, acceleration = processed_signals(c, d['force_N'], d['acceleration_m_s2']) if c.bandpass_enabled else (d['force_N'], d['acceleration_m_s2'])
            self.plot('force', t, force)
            self.plot('acceleration', t, acceleration)
            freq = np.fft.rfftfreq(c.n, 1/c.sample_rate)
            for key, spectrum in [('fft_force', d['F']), ('fft_acceleration', d['A'])]:
                amplitude = abs(spectrum)/c.n
                amplitude[1:-1 if c.n % 2 == 0 else None] *= 2
                self.plot(key, freq, amplitude)
        self.quality.setText(f"{record['point']} · {record['status']}\nPico: {record['peak_N']:.3g} N | S/R: {record['snr_dB']:.1f} dB\n"
                            f"RMS final / pós-trigger: {record['tail_ratio']:.1%}\n"+
                            ('\n'.join(record['issues']) or 'Sem alertas nos critérios automáticos.')+
                            '\nCritérios são indicativos; a aceitação é manual.')

    def results(self):
        if not self.session:
            return
        point = self.point.currentText()
        hits = self.session.hits(point)
        f, h1, coh = ensemble(self.session.config, hits)
        self.plot('frf', f, abs(h1))
        self.plot('phase', f, np.angle(h1, deg=True), (-180, 180))
        self.plot('coherence', f, coh, (0, 1))
        self.progress.setText(f'{point}: {len(hits)} / {self.session.config.averages} batidas aceitas\n'
                              + ('Coerência: precisa de ≥2 batidas.' if len(hits) < 2 else 'Médias espectrais das batidas aceitas.')
                              + (f'\nPassa-banda: {self.session.config.low_cut:g}–{self.session.config.high_cut:g} Hz' if self.session.config.bandpass_enabled else '\nPassa-banda desativado'))

    def point_changed(self):
        self.geometry.selected = self.point.currentText()
        self.geometry.update()
        self.results()

    def update_history(self):
        self.history.setRowCount(len(self.session.records))
        for row, record in enumerate(self.session.records):
            for col, value in enumerate([record['point'], record['status'], f"{record['peak_N']:.3g}", '; '.join(record['issues']) or 'Sem alertas']):
                self.history.setItem(row, col, QTableWidgetItem(value))

    def review(self, accept):
        if self.pending is None:
            return
        try:
            self.session.review(self.pending, accept)
            self.post.invalidate()
            self.show_hit(self.pending)
            self.pending = None
            self.update_history()
            self.results()
            self.status.setText('Revisão salva. Arme o trigger para a próxima batida ou selecione outro ponto.')
        except Exception as exc:
            self.error(exc)
        self.refresh()

    def inspect(self, row, column=0):
        if self.busy or self.capture and self.capture.armed or self.pending is not None:
            return
        record = self.session.records[row]
        self.point.setCurrentText(record['point'])
        self.show_hit(record)
        self.pending = record  # Existing decisions may be revised, recomputing averages.
        self.status.setText('Revisando captura selecionada; aceite ou rejeite para continuar.')
        self.refresh()

    def export_hit(self):
        if not self.session or not self.session.records:
            return
        row = self.history.currentRow()
        record = self.pending if self.pending is not None else self.session.records[max(0, row)]
        path, _ = QFileDialog.getSaveFileName(self, 'Exportar batida', 'batida.csv', 'CSV (*.csv)')
        if path:
            try:
                with np.load(self.session.directory/record['file']) as d:
                    columns = [d['time'], d['force_N'], d['acceleration_m_s2']]
                    header = 'tempo_s;forca_original_N;aceleracao_original_m_s2'
                    if self.session.config.bandpass_enabled:
                        columns.extend(processed_signals(self.session.config, d['force_N'], d['acceleration_m_s2']))
                        header += ';forca_filtrada_N;aceleracao_filtrada_m_s2'
                    np.savetxt(path, np.column_stack(columns), delimiter=';', header=header, comments='')
            except Exception as exc:
                self.error(exc)

    def process(self):
        for _ in range(60):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            try:
                if event[0] == 'done':
                    self.busy = False
                    event[1](event[2])
                elif event[0] in ('error', 'acquisition_error'):
                    if event[0] == 'error':
                        self.busy = False
                    if self.capture:
                        self.capture.cancel()
                    self.error(event[1])
                elif event[0] == 'data' and self.capture:
                    c = self.capture.config
                    times = event[1]
                    force = np.asarray(event[2][self.indices[0]])*c.force_factor
                    acceleration = np.asarray(event[2][self.indices[1]])*c.response_factor
                    lost = self.backend.samples_lost()
                    if lost > self.lost:
                        self.capture.cancel()
                        if self.live_filter:
                            self.live_filter.reset()
                        self.status.setText('Perda de amostras: batida cancelada; rearme o trigger.')
                    self.lost = lost
                    display_values = self.live_filter.apply([force, acceleration]) if self.live_filter else [force, acceleration]
                    self.live.append(times, display_values)
                    result = self.capture.feed(times, force, acceleration)
                    if result:
                        self.pending, _ = self.session.capture(*result)
                        self.show_hit(self.pending)
                        self.update_history()
                        self.history.selectRow(len(self.session.records)-1)
                        self.status.setText('Batida salva. Revise os sinais e aceite ou rejeite a captura.')
                    elif self.capture.pending is not None:
                        self.status.setText('Impacto detectado — capturando resposta…')
            except Exception as exc:
                if self.capture:
                    self.capture.cancel()
                if self.live_filter:
                    self.live_filter.reset()
                if isinstance(exc, OSError) and self.controller and self.controller.running and not self.busy:
                    self.work(self.controller.stop, lambda _: None)
                # Do not repeatedly open dialogs on a broken data stream.
                self.status.setText(f'Captura interrompida: {exc}')
        if self.capture and self.capture.armed:
            times, values = self.live.snapshot()
            if len(times):
                self.plot('force', times-times[-1], values[0])
                self.plot('acceleration', times-times[-1], values[1])
        self.refresh()

    def refresh(self):
        running = bool(self.controller and self.controller.running)
        armed = bool(self.capture and self.capture.armed)
        self.settings.setEnabled(not running and not self.busy)
        self.mode.setEnabled(not self.backend and not self.busy)
        self.ip.setEnabled(not self.backend and not self.busy)
        self.connect_button.setEnabled(not running and not self.busy)
        self.connect_button.setText('Desconectar' if self.backend else 'Conectar')
        self.start_button.setEnabled(bool(self.backend) and not running and not self.busy and self.pending is None)
        self.open_button.setEnabled(not running and not self.busy and self.pending is None)
        self.arm_button.setEnabled(running and not armed and self.pending is None and not self.busy)
        self.cancel_button.setEnabled(armed and not self.busy)
        self.stop_button.setEnabled(running and not self.busy)
        self.point.setEnabled(not armed and self.pending is None and not self.busy)
        self.accept_button.setEnabled(self.pending is not None and not self.busy)
        self.reject_button.setEnabled(self.pending is not None and not self.busy)
        self.post.refresh(running, self.busy)

    def closeEvent(self, event):
        if self.busy:
            event.ignore()
            return
        if self.backend:
            event.ignore()
            if self.capture:
                self.capture.cancel()
            def shutdown():
                if self.controller:
                    self.controller.stop()
                self.backend.disconnect()
            def closed(_):
                self.backend = self.controller = None
                self.close()
            self.work(shutdown, closed)
            return
        self.timer.stop()
        event.accept()


def run():
    app = QApplication.instance() or QApplication(sys.argv)
    window = ModalApp()
    window.show()
    sys.exit(app.exec())
