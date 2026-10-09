"""Post-processing controls, FRF fit comparison and measured mode animation."""
from datetime import datetime
import uuid

import numpy as np
from PyQt6.QtCore import QPointF, Qt, QTimer, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QDoubleSpinBox, QSpinBox, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QComboBox, QSplitter, QSlider, QTabWidget)

from ads1800_app.modal_post import PostSettings, StabilitySettings, prepare_data, fit_modes, export_results
from ads1800_app.modal_ema import identify_ema, reconstruct_ema
from ads1800_app.ui.stabilization import StabilizationCanvas
from ads1800_app.ui.plots import ChannelCanvas, envelope_indices
from ads1800_app.ui.frf_view import FRF_VIEWS, frf_components


class Comparison(ChannelCanvas):
    def __init__(self):
        super().__init__('#2563eb')
        self.x_label = 'Frequência [Hz]'
        self.model = np.array([])

    def paintEvent(self, event):
        super().paintEvent(event)
        if len(self.model) != len(self.times) or not len(self.times):
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.plot_rect()
        left, top, right, bottom = rect.left(), rect.top(), rect.right(), rect.bottom()
        p.setClipRect(rect)
        p.setPen(QPen(QColor('#e87916'), 1.5, Qt.PenStyle.DashLine))
        x0, x1 = self.x_range
        y0, y1 = self.y_range
        points = QPolygonF()
        for i in envelope_indices(self.model, max(1, int(right-left))):
            if not np.isfinite(self.model[i]):
                p.drawPolyline(points)
                points = QPolygonF()
                continue
            points.append(QPointF(left+(self.times[i]-x0)/(x1-x0)*(right-left),
                                  bottom-(self.model[i]-y0)/(y1-y0)*(bottom-top)))
        p.drawPolyline(points)
        self.paint_frequency_markers(p)


class ModeView(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(400, 300)
        self.config = None
        self.shape = {}
        self.shape_imag = {}
        self.mode_label = 'Nenhum modo selecionado'
        self.phase = 0
        self.amplitude = .25
        self.speed = .5
        self.playing = True
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(40)

    def tick(self):
        if self.playing and self.isVisible() and self.shape:
            self.phase = (self.phase+2*np.pi*self.speed*.04) % (2*np.pi)
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#f8fafc'))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.config is None:
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Abra um ensaio e calcule os modos.')
            return
        c = self.config
        xy = np.asarray([*c.outline, *[v[1:] for v in c.points], c.accelerometer], float)
        center = (xy.min(axis=0)+xy.max(axis=0))/2
        span = max(float(np.ptp(xy, axis=0).max()), 1e-6)
        relative = xy-center
        plan_x = .86*relative[:, 0]-.5*relative[:, 1]
        plan_y = .3*relative[:, 0]+.52*relative[:, 1]
        scale = min((self.width()-160)/max(float(np.ptp(plan_x)), span*.1),
                    (self.height()-100)/max(float(np.ptp(plan_y))+2*span*self.amplitude, span*.1))
        def pos(v, z=0):
            x, y = np.asarray(v)-center
            return QPointF(self.width()/2+scale*(.86*x-.5*y), self.height()/2+scale*(.3*x+.52*y-z))
        p.setBrush(QColor('#e2e8f0'))
        p.setPen(QPen(QColor('#94a3b8'), 1, Qt.PenStyle.DashLine))
        p.drawPolygon(QPolygonF([pos(v) for v in c.outline]))
        for name, x, y in c.points:
            reference = pos([x, y])
            measured = name in self.shape
            displacement = (self.shape.get(name, 0)*np.cos(self.phase)-self.shape_imag.get(name, 0)*np.sin(self.phase))*span*self.amplitude
            moving = pos([x, y], displacement)
            p.setPen(QPen(QColor('#64748b'), 1, Qt.PenStyle.DotLine))
            p.drawLine(reference, moving)
            p.setPen(QPen(QColor('#475569'), 1))
            p.setBrush(QColor('#94a3b8' if not measured else '#2563eb' if self.shape[name] >= 0 else '#e87916'))
            p.drawEllipse(moving, 5, 5)
            p.drawText(moving+QPointF(8, -8), f'{name}' if measured else f'{name} (sem estimativa)')
        a = pos(c.accelerometer)
        p.setPen(QPen(QColor('#16a34a'), 2))
        p.drawLine(a+QPointF(-6, -6), a+QPointF(6, 6))
        p.drawLine(a+QPointF(-6, 6), a+QPointF(6, -6))
        p.drawText(a+QPointF(8, 16), 'Referência A (posição do sensor)')
        p.setPen(QColor('#334155'))
        p.drawText(12, 22, self.mode_label)
        p.drawText(12, 42, 'Deslocamento relativo em Z · perspectiva do plano XY')
        p.drawText(12, self.height()-15, 'Amplitude ampliada; animação lenta, sem escala física de tempo.')


class PostPanel(QWidget):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.session = None
        self.result = None
        self.computing = False
        layout = QVBoxLayout(self)
        self.controls = QWidget()
        grid = QGridLayout(self.controls)
        self.fields = {}
        for index, (key, label, default, low, high, digits) in enumerate([
            ('fmin', 'Frequência mínima [Hz]', 5, .001, 1e6, 3),
            ('fmax', 'Frequência máxima [Hz]', 200, .002, 1e6, 3),
            ('min_coherence', 'Coerência mínima', .8, 0, 1, 2),
            ('exponential_end', 'Resíduo da exponencial comum (1 = sem janela)', .01, .00001, 1, 5),
            ('prominence_db', 'Proeminência dos picos [dB]', 3, .1, 100, 1)]):
            w = QDoubleSpinBox()
            w.setDecimals(digits)
            w.setRange(low, high)
            w.setValue(default)
            self.fields[key] = w
            grid.addWidget(QLabel(label), index//3*2, index % 3)
            grid.addWidget(w, index//3*2+1, index % 3)
            w.valueChanged.connect(self.invalidate)
        for col, (key, label, default, high) in enumerate([
            ('max_modes', 'Máximo de candidatos automáticos', 6, 12),
            ('min_hits', 'Mínimo de batidas aceitas por ponto', 2, 10000)]):
            w = QSpinBox()
            w.setRange(1, high)
            w.setValue(default)
            self.fields[key] = w
            grid.addWidget(QLabel(label), 4, col)
            grid.addWidget(w, 5, col)
            w.valueChanged.connect(self.invalidate)
        self.seeds = QLineEdit()
        self.seeds.setPlaceholderText('Automático, ou frequências em Hz: 35; 90')
        self.seeds.textChanged.connect(self.invalidate)
        grid.addWidget(QLabel('Candidatos manuais (opcional)'), 4, 2)
        grid.addWidget(self.seeds, 5, 2)
        self.engine = QComboBox()
        self.engine.addItems(['sdypy-EMA · LSCF + LSFD', 'Ajuste de modos reais (anterior)'])
        self.engine.currentIndexChanged.connect(self.invalidate)
        grid.addWidget(QLabel('Identificação modal'), 6, 0)
        grid.addWidget(self.engine, 7, 0)
        self.polynomial_order = QSpinBox()
        self.polynomial_order.setRange(3, 60)
        self.polynomial_order.setValue(20)
        self.polynomial_order.valueChanged.connect(self.invalidate)
        grid.addWidget(QLabel('Limite polinomial LSCF (ordem dinâmica = 2×)'), 6, 1)
        grid.addWidget(self.polynomial_order, 7, 1)
        self.stability_fields = {}
        tolerances = QHBoxLayout()
        for name, title, default, low, high in [('frequency_tolerance', 'Δf %', 1, .01, 50),
                                               ('damping_tolerance', 'Δζ %', 5, .01, 100),
                                               ('min_mac', 'MAC', .95, 0, 1)]:
            box = QDoubleSpinBox()
            box.setDecimals(2)
            box.setRange(low, high)
            box.setValue(default)
            box.valueChanged.connect(self.invalidate)
            self.stability_fields[name] = box
            tolerances.addWidget(QLabel(title))
            tolerances.addWidget(box)
        grid.addWidget(QLabel('Tolerâncias entre ordens adjacentes'), 6, 2)
        grid.addLayout(tolerances, 7, 2)
        layout.addWidget(self.controls)
        row = QHBoxLayout()
        self.calculate = QPushButton('Calcular frequências, amortecimentos e modos')
        self.calculate.clicked.connect(self.compute)
        row.addWidget(self.calculate)
        self.export = QPushButton('Salvar pós-processamento')
        self.export.clicked.connect(self.save)
        row.addWidget(self.export)
        layout.addLayout(row)
        self.summary = QLabel('Abra um ensaio ou finalize uma aquisição para calcular os modos.')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        splitter = QSplitter()
        left = QWidget()
        left_box = QVBoxLayout(left)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['Modo', 'Natural [Hz]', 'ζ [%]', 'Verificação'])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.currentCellChanged.connect(lambda row, col, *_: self.select_mode(row, col))
        left_box.addWidget(self.table)
        self.components = QTableWidget(0, 3)
        self.components.setHorizontalHeaderLabels(['Ponto', 'Z real', 'Z imaginário'])
        self.components.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        left_box.addWidget(self.components)
        self.notes = QLabel('Formas normalizadas: maior componente = +1.\n'
            'A hipótese é de estrutura linear e recíproca com modos reais.\n'
            'Modos com nó na referência fixa podem não ser observados.')
        self.notes.setWordWrap(True)
        left_box.addWidget(self.notes)
        splitter.addWidget(left)
        right = QWidget()
        right_box = QVBoxLayout(right)
        self.view = ModeView()
        right_box.addWidget(self.view)
        animation = QHBoxLayout()
        self.pause = QPushButton('Pausar animação')
        self.pause.clicked.connect(self.toggle_animation)
        animation.addWidget(self.pause)
        animation.addWidget(QLabel('Ampliação'))
        amplitude = QSlider(Qt.Orientation.Horizontal)
        amplitude.setRange(0, 70)
        amplitude.setValue(25)
        amplitude.valueChanged.connect(self.set_amplitude)
        animation.addWidget(amplitude)
        right_box.addLayout(animation)
        comparison_row = QHBoxLayout()
        comparison_row.addWidget(QLabel('FRF azul: medida · laranja: ajustada'))
        self.point = QComboBox()
        self.point.currentIndexChanged.connect(self.show_comparison)
        comparison_row.addWidget(self.point)
        right_box.addLayout(comparison_row)
        self.frf_view = QComboBox()
        self.frf_view.addItems(FRF_VIEWS)
        self.frf_view.currentIndexChanged.connect(self.show_comparison)
        right_box.addWidget(self.frf_view)
        self.comparison = Comparison()
        self.comparison_secondary = Comparison()
        self.comparison_labels = [QLabel('Magnitude [(m/s²)/N]'), QLabel('Fase [graus]')]
        comparison_charts = QHBoxLayout()
        for label, canvas in zip(self.comparison_labels, (self.comparison, self.comparison_secondary)):
            column = QVBoxLayout()
            column.addWidget(label)
            column.addWidget(canvas)
            comparison_charts.addLayout(column)
        right_box.addLayout(comparison_charts)
        self.error_label = QLabel('Módulo da acelerância [(m/s²)/N] × frequência [Hz]')
        right_box.addWidget(self.error_label)
        self.result_tabs = QTabWidget()
        self.result_tabs.addTab(right, 'Formas e FRF')
        stability_page = QWidget()
        stability_box = QVBoxLayout(stability_page)
        self.stability_canvas = StabilizationCanvas()
        stability_box.addWidget(self.stability_canvas, 1)
        legend = QLabel('Cinza: novo · azul: frequência · laranja: frequência + amortecimento · verde: + MAC\n'
                        'Borda vermelha: selecionado. Clique para marcar uma ocorrência de cada modo e aplique.\n'
                        'Linhas roxas tracejadas: frequências do ajuste selecionado. Estabilidade não certifica um modo físico.')
        legend.setWordWrap(True)
        stability_box.addWidget(legend)
        self.selection_label = QLabel('Sem polos selecionados.')
        stability_box.addWidget(self.selection_label)
        self.apply_poles = QPushButton('Aplicar polos selecionados (LSFD)')
        self.apply_poles.clicked.connect(self.reconstruct)
        self.stability_canvas.selection_changed.connect(self.selection_updated)
        stability_box.addWidget(self.apply_poles)
        self.mac_label = QLabel('Auto-MAC disponível após selecionar modos.')
        self.mac_label.setWordWrap(True)
        stability_box.addWidget(self.mac_label)
        self.result_tabs.addTab(stability_page, 'Diagrama de estabilização')
        splitter.addWidget(self.result_tabs)
        splitter.setSizes([460, 800])
        layout.addWidget(splitter, 1)

    def set_session(self, session):
        self.session = session
        self.view.config = session.config if session else None
        if session:
            nyquist = session.config.sample_rate/2
            low = session.config.low_cut if session.config.bandpass_enabled else .001
            high = session.config.high_cut if session.config.bandpass_enabled else nyquist
            self.fields['fmax'].setValue(min(max(200, low+(high-low)/2), high))
            self.fields['fmin'].setValue(max(low, min(5, high/10)))
        self.invalidate()

    def invalidate(self, *_):
        self.result = None
        self.table.setRowCount(0)
        self.components.setRowCount(0)
        self.view.shape = {}
        self.view.shape_imag = {}
        self.view.mode_label = 'Nenhum modo selecionado'
        self.view.update()
        for canvas in (self.comparison, self.comparison_secondary):
            canvas.times = canvas.values = canvas.model = np.array([])
            canvas.update()
        self.stability_canvas.set_result(None)
        self.mac_label.setText('Auto-MAC disponível após selecionar modos.')
        self.update_markers([])
        self.summary.setText('Resultados não calculados ou desatualizados. Calcule com as batidas atualmente aceitas.')
        self.notes.setText('Formas relativas para estrutura linear e recíproca.\n'
                           'Modos com nó na referência fixa podem não ser observados.')
        self.error_label.setText('Módulo da acelerância [(m/s²)/N] × frequência [Hz]')
        self.export.setEnabled(False)

    def update_markers(self, frequencies):
        for canvas in [self.comparison, self.comparison_secondary, *[self.owner.plots[key] for key in ('fft_force', 'fft_acceleration', 'frf', 'phase', 'coherence')]]:
            canvas.frequency_markers = list(frequencies)
            canvas.update()

    def selection_updated(self):
        self.selection_label.setText(f'{len(self.stability_canvas.selected)} polos marcados; aplique para atualizar FRF, formas e linhas.')

    def reconstruct(self):
        if not self.result or '_ema_context' not in self.result or self.owner.busy:
            return
        context = self.result['_ema_context']
        selected = [list(key) for key in sorted(self.stability_canvas.selected)]
        self.owner.work(lambda: reconstruct_ema(context, selected), self.display)

    def refresh(self, running, busy):
        if self.computing and not busy:
            self.computing = False
            if self.result is None:
                self.summary.setText('Cálculo não concluído. Confira a mensagem de erro e revise os parâmetros.')
        allowed = self.session is not None and not running and not busy and self.owner.pending is None
        self.controls.setEnabled(not busy)
        self.calculate.setEnabled(allowed)
        self.export.setEnabled(allowed and self.result is not None)
        self.apply_poles.setEnabled(allowed and self.result is not None and '_ema_context' in self.result)
        self.stability_canvas.setEnabled(not busy)

    def compute(self):
        if self.session is None or self.owner.busy or self.owner.controller and self.owner.controller.running:
            return
        try:
            settings = PostSettings(**{k: w.value() for k, w in self.fields.items()})
            settings.validate(self.session.config.sample_rate/2)
            seeds = [float(x.strip().replace(',', '.')) for x in self.seeds.text().split(';')] if self.seeds.text().strip() else None
        except Exception as exc:
            self.owner.error(exc)
            return
        self.invalidate()
        self.summary.setText('Recalculando FRFs aceitas e ajustando os modos…')
        self.computing = True
        session = self.session
        engine = self.engine.currentIndex()
        order = self.polynomial_order.value()
        stability = StabilitySettings(frequency_tolerance=self.stability_fields['frequency_tolerance'].value()/100,
                                      damping_tolerance=self.stability_fields['damping_tolerance'].value()/100,
                                      min_mac=self.stability_fields['min_mac'].value())
        self.owner.work(lambda: identify_ema(prepare_data(session, settings), settings, seeds, order, stability)
                        if engine == 0 else fit_modes(prepare_data(session, settings), settings, seeds), self.display)

    def display(self, result):
        self.computing = False
        self.result = result
        self.update_markers([m['frequency_hz'] for m in result['modes']])
        self.stability_canvas.set_result(result)
        self.selection_updated()
        self.table.setRowCount(len(result['modes']))
        for row, mode in enumerate(result['modes']):
            for col, value in enumerate([str(row+1), f"{mode['frequency_hz']:.4f}", f"{mode['damping_ratio']*100:.4f}",
                                         '; '.join(mode['warnings']) or 'Conferir ajuste da FRF']):
                self.table.setItem(row, col, QTableWidgetItem(value))
        self.point.clear()
        self.point.addItems(result['point_ids'])
        error = max([v for v in result['relative_fit_error'].values() if v is not None], default=0)
        self.summary.setText(f"{len(result['modes'])} modos estimados · erro máximo da FRF: {error:.1%} · "
                               f"resolução: {result['frequency_resolution_hz']:.4g} Hz · exponencial considerada no ajuste.")
        if not result['modes']:
            self.summary.setText('Nenhum polo selecionado automaticamente. Revise o diagrama e selecione os modos para reconstruir a FRF.')
        warnings = result['warnings']
        self.notes.setText('Formas relativas, sem normalização por massa. Pontos sem estimativa ficam cinza.\n'
                           'Formas complexas no sdypy-EMA. Modos nodais na referência podem ser invisíveis.\n'+
                           '\n'.join(warnings[:8])+ ('\nMais alertas no relatório exportado.' if len(warnings) > 8 else ''))
        if result['modes']:
            self.table.selectRow(0)
            self.select_mode(0)
        else:
            self.view.shape = self.view.shape_imag = {}
            self.view.mode_label = 'Selecione polos no diagrama'
            self.components.setRowCount(0)
            self.result_tabs.setCurrentIndex(1)
        if 'auto_mac' in result:
            matrix = np.asarray(result['auto_mac'])
            self.mac_label.setText('Auto-MAC (linhas/colunas = modos):\n'+'\n'.join('  '.join(f'{v:.3f}' for v in row) for row in matrix))
        self.show_comparison()

    def select_mode(self, row, column=0):
        if self.result is None or row < 0:
            return
        mode = self.result['modes'][row]
        self.view.mode_label = f"Modo {row+1} · {mode['frequency_hz']:.3f} Hz · ζ = {100*mode['damping_ratio']:.3f}%"
        self.view.shape = mode['shape']
        self.view.shape_imag = mode.get('shape_imag', {})
        self.view.phase = 0
        self.view.update()
        self.components.setRowCount(len(self.session.config.points))
        for i, (name, *_) in enumerate(self.session.config.points):
            self.components.setItem(i, 0, QTableWidgetItem(name))
            self.components.setItem(i, 1, QTableWidgetItem(f"{mode['shape'][name]:+.5f}" if name in mode['shape'] else 'Sem estimativa'))
            self.components.setItem(i, 2, QTableWidgetItem(f"{mode.get('shape_imag', {}).get(name, 0):+.5f}" if name in mode['shape'] else 'Sem estimativa'))

    def show_comparison(self, *_):
        if self.result is None or self.point.currentIndex() < 0:
            return
        i = self.point.currentIndex()
        r = self.result
        maximum = r['settings']['fmax']
        if self.session.config.bandpass_enabled:
            maximum = min(maximum, self.session.config.high_cut)
        mask = (r['frequency'] >= r['settings']['fmin']) & (r['frequency'] <= maximum)
        x = r['frequency'][mask]
        measured = frf_components(r['measured'][i, mask], self.frf_view.currentIndex())
        fitted = frf_components(r['fitted'][i, mask], self.frf_view.currentIndex())
        for canvas, title, (y, label, fixed), (fit, _, _) in zip(
                (self.comparison, self.comparison_secondary), self.comparison_labels, measured, fitted):
            title.setText(label)
            canvas.times, canvas.values, canvas.model = x, y, fit
            canvas.x_range = (r['settings']['fmin'], maximum)
            valid = np.r_[y[np.isfinite(y)], fit[np.isfinite(fit)]]
            low, high = (float(valid.min()), float(valid.max())) if len(valid) else (0, 1)
            margin = max((high-low)*.08, abs(high)*.01, 1e-12)
            canvas.y_range = fixed or (low-margin, high+margin)
            canvas.update()
        error = r['relative_fit_error'][self.point.currentText()]
        self.error_label.setText('Acelerância [(m/s²)/N] × Hz · erro complexo: '+(f'{error:.2%}' if error is not None else 'sem reconstrução'))

    def set_amplitude(self, value):
        self.view.amplitude = value/100
        self.view.update()

    def toggle_animation(self):
        self.view.playing = not self.view.playing
        self.pause.setText('Pausar animação' if self.view.playing else 'Animar modo')

    def save(self):
        if self.result is None:
            return
        try:
            directory = self.session.directory/f'pos_processamento_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}'
            # Include geometry so exported relative shapes remain self-contained.
            report = dict(self.result, geometry={'outline': self.session.config.outline,
                          'points': self.session.config.points, 'accelerometer': self.session.config.accelerometer},
                          bandpass={'enabled': self.session.config.bandpass_enabled,
                                    'low_hz': self.session.config.low_cut, 'high_hz': self.session.config.high_cut,
                                    'method': 'Butterworth SOS causal; protótipo ordem 4; antes do janelamento'})
            export_results(report, directory)
            self.summary.setText(f'Resultados salvos em {directory}')
        except Exception as exc:
            self.owner.error(exc)
