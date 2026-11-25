"""Raw hammer stream, last-hit windows and spectra, and ensemble coherence."""
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import queue
import threading
import uuid

import numpy as np
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QDialog, QDoubleSpinBox, QFileDialog, QTableWidgetItem

from ads1800_app.config import ExperimentConfig
from ads1800_app.controller import AcquisitionController
from ads1800_app.modal import ImpactCapture, ModalConfig, hit_spectra, windows
from ads1800_app.modal_coherence import project_setup_record, spectrum_density
from ads1800_app.modal_setup import SetupSettings, TwoHitStudy, two_hit_metrics
from ads1800_app.ui.plots import DisplayBuffer
from ads1800_app.ui.modal_style import modal_font
from ads1800_app.ui.modal_setup_layout import build_setup_layout


class ModalSetupDialog(QDialog):
    def __init__(self, backend, config, channels, rates, parent=None, *, auto_start=True):
        super().__init__(parent)
        self.setFont(modal_font())
        self.setWindowTitle('Configuração por duas batidas')
        self.resize(1460, 960)
        self.backend, self.base, self.channels, self.rates = backend, config, channels, rates
        self.study = self.capture = self.controller = None
        self.events = queue.Queue(maxsize=300)
        self.generation = 0
        self.busy = False
        self.phase = 'idle'
        self.live = DisplayBuffer(5)
        self.live_rate = config.sample_rate
        self.last_time = None
        self.last_partial_check = 0
        self.old_simulator = {name: getattr(backend, name) for name in
                              ('impacts_enabled', 'period', 'impact_start') if hasattr(backend, name)}
        self.updating_windows = False
        self.window_error = False
        build_setup_layout(self)
        for control in (self.fmin, self.fmax, self.observation):
            control.valueChanged.connect(self.settings_changed)
        self.sensor.currentIndexChanged.connect(self.settings_changed)
        self.point.currentIndexChanged.connect(self.settings_changed)
        self.view.currentIndexChanged.connect(self.redraw)
        self.psd_mode.currentIndexChanged.connect(self.redraw)
        self.response_function.currentIndexChanged.connect(self.redraw)
        self.force_zoom.toggled.connect(self.redraw)
        self.coherence_threshold.valueChanged.connect(self.quality_requirements_changed)
        self.coherence_fraction.valueChanged.connect(self.quality_requirements_changed)
        self.force_window.currentIndexChanged.connect(self.window_controls_changed)
        self.response_window.currentIndexChanged.connect(self.window_controls_changed)
        self.force_width.valueChanged.connect(self.window_controls_changed)
        self.exponential_end.valueChanged.connect(self.window_controls_changed)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(30)
        self.draw_timer = QTimer(self)
        self.draw_timer.timeout.connect(self.redraw)
        self.draw_timer.start(100)
        self.refresh()
        if auto_start:
            QTimer.singleShot(0, self.restart)

    @staticmethod
    def number(value, low, high):
        widget = QDoubleSpinBox()
        widget.setRange(low, high)
        widget.setDecimals(3)
        widget.setValue(value)
        return widget

    def settings_changed(self, *_):
        if self.study:
            self.study.validated = False
            self.study.coherence_result = None
            self.quality_label.setText("Configuração alterada: recomece as batidas.")
            if self.capture:
                self.capture.cancel()
            self.capture = None
            self.phase = 'changed'
            self.status.setText('Banda, canal ou ponto alterado. Clique em Recomeçar para medir novamente.')
        self.redraw()
        self.refresh()

    def _work(self, action, done):
        self.busy = True
        self.refresh()
        def worker():
            try:
                self.events.put(('done', done, action()))
            except Exception as exc:
                self.events.put(('error', exc))
        threading.Thread(target=worker, daemon=True).start()

    def _start_stream(self, config, phase, started):
        config.validate()
        self.generation += 1
        generation = self.generation
        self.capture = None
        self.phase = 'starting'
        self.ready_announced = False
        self.stream_config = config
        self.live_rate = config.sample_rate
        self.live = DisplayBuffer(5)
        self.factors = np.array([config.force_factor, *[s['factor'] for s in config.sensors]])
        desired = [config.force_channel, *[s['channel'] for s in config.sensors]]
        by_id = {c.number: c for c in self.channels}
        experiment = ExperimentConfig(name='Configuração modal', sample_rate=config.sample_rate,
            channels=[replace(by_id[n], enabled=True) for n in desired])
        previous = self.controller
        controller = AcquisitionController(self.backend,
            lambda times, values: self.events.put_nowait(('data', generation, times, values)),
            lambda exc: self.events.put(('stream_error', generation, exc)))
        self.controller = controller
        def start():
            if previous:
                previous.stop()
            if hasattr(self.backend, 'impacts_enabled'):
                self.backend.impacts_enabled = False
                self.backend.period = config.duration+2
            controller.start(experiment)
            return self.backend.samples_lost()
        def ready(lost):
            if generation != self.generation:
                if controller.running:
                    self._work(controller.stop, lambda _: None)
                return
            self.lost = lost
            self.last_time = None
            self.phase = phase
            started()
        self._work(start, ready)

    def restart(self):
        if self.busy or self.phase in ('closing', 'closed'):
            return
        try:
            settings = SetupSettings(fmin=self.fmin.value(), fmax=self.fmax.value(),
                observation_seconds=self.observation.value(), noise_seconds=.5,
                minimum_hits=1, minimum_points=1, confirmation_hits=1)
            self.study = TwoHitStudy(self.base, self.rates, settings, sensor=self.sensor.currentIndex(),
                coherence_threshold=self.coherence_threshold.value(), coherence_fraction=self.coherence_fraction.value()/100)
            self.window_error = False
            self.results.setRowCount(0)
            self.quality_label.setText('Aguardando duas batidas do mesmo ponto.')
            self.quality_label.setStyleSheet('')
            self.plan_label.setText('Primeira batida: medir o pico e o decaimento.\nSegunda batida: conferir consistência e coerência.')
            self.window_hint.setText('Janelamento: aguardando a primeira batida.')
            self.noise_blocks, self.noise_count = [], 0
            c = replace(self.base, sample_rate=self.study.pilot_rate, duration=settings.observation_seconds,
                        pretrigger=.1, bandpass_enabled=False, analysis_band=None,
                        rearm_noise_limits=(), response_window='Retangular', exponential_end=1)
            self._start_stream(c, 'noise_first', lambda: self.status.setText('Sinais ao vivo. Aguarde 0,5 s em repouso para medir o ruído.'))
        except Exception as exc:
            self.fail(exc)

    def begin_second(self):
        if self.busy or not self.study or not self.study.recommendation:
            return
        try:
            if self.study.recommendation.blockers:
                raise ValueError('\n'.join(self.study.recommendation.blockers))
            self.study.reset_confirmation()
            self.quality_label.setText('Nova conferência em andamento. Aguardando a próxima batida.')
            self.quality_label.setStyleSheet('color: #92400e;')
            self.noise_blocks, self.noise_count = [], 0
            result = self.study.recommendation.config
            c = replace(result, duration=max(self.study.settings.observation_seconds, result.duration*1.25),
                        force_window='Retangular', response_window='Retangular', exponential_end=1,
                        rearm_noise_limits=())
            self._start_stream(c, 'noise_second', lambda: self.status.setText('Primeira batida medida. Conferindo ruído na taxa final; aguarde o aviso para a segunda.'))
        except Exception as exc:
            self.fail(exc)

    def _arm(self, second):
        self.stream_config = self.study.confirmation_config() if second else self.study.pilot_config()
        self.capture = ImpactCapture(self.stream_config)
        self.capture.arm(self.point.currentText())
        self.phase = 'second' if second else 'first'
        self.last_partial_check = 0
        self.ready_announced = False
        if hasattr(self.backend, 'impacts_enabled'):
            self.backend.impacts_enabled = True
            self.backend.impact_start = float(self.last_time)+max(.5, self.stream_config.quiet_duration+.2)
        threshold = self.stream_config.threshold
        self.status.setText(f'Aguardando repouso. Detecção da {"segunda" if second else "primeira"} batida: {threshold:.4g} N.')

    def poll(self):
        for _ in range(100):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            try:
                if event[0] == 'done':
                    self.busy = False
                    event[1](event[2])
                elif event[0] == 'error':
                    self.busy = False
                    self.fail(event[1])
                elif event[0] == 'stream_error' and event[1] == self.generation:
                    self.fail(event[2])
                elif event[0] == 'data' and event[1] == self.generation:
                    self.feed(event[2], event[3])
            except Exception as exc:
                self.fail(exc)
        self.refresh()

    def feed(self, times, values):
        c = self.stream_config
        t = np.asarray(times, float)
        values = np.asarray(values, float).T*self.factors
        if not len(t):
            return
        if values.shape != (len(t), len(self.factors)) or not np.isfinite(values).all() or not np.isfinite(t).all():
            raise ValueError('Bloco inválido recebido da aquisição.')
        # Do not process packets queued before the start callback established
        # continuity and the initial loss count.
        if self.phase == 'starting':
            return
        dt = np.diff(np.r_[self.last_time, t] if self.last_time is not None else t)
        if not np.allclose(dt, 1/c.sample_rate, rtol=.05, atol=1e-8) or self.backend.samples_lost() > self.lost:
            raise ValueError('Perda ou descontinuidade de amostras. Recomece a configuração.')
        self.last_time = t[-1]
        self.live.append(t, values.T)
        if self.phase in ('noise_first', 'noise_second'):
            self.noise_blocks.append(values)
            self.noise_count += len(t)
            required = round(self.study.settings.noise_seconds*c.sample_rate)
            if self.noise_count >= required:
                noise = np.vstack(self.noise_blocks)[:required]
                second = self.phase == 'noise_second'
                if second:
                    self.study.set_confirmation_noise(noise)
                else:
                    self.study.set_noise(noise)
                self._arm(second)
        elif self.capture and self.phase in ('first', 'second'):
            result = self.capture.feed(t, values[:, 0], values[:, 1:])
            if self.capture.ready and not self.ready_announced:
                self.ready_announced = True
                QApplication.beep()
                self.status.setText('Pronto — faça a segunda batida no mesmo ponto.' if self.phase == 'second' else
                                    'Pronto — faça a primeira batida. O pico e o decaimento serão medidos automaticamente.')
            if result is None and self.capture.pending is not None:
                count = len(self.capture.pending)
                if count >= c.pre+round(.5*c.sample_rate) and count-self.last_partial_check >= round(.1*c.sample_rate):
                    self.last_partial_check = count
                    partial = np.asarray(self.capture.pending)
                    profile = self.study.confirmation_noise if self.phase == 'second' else self.study.noise
                    metrics = two_hit_metrics(partial, c, profile, self.study.reference_sensor)
                    if metrics['settled'] and metrics['quiet_s'] >= max(.25, .05*metrics['decay_s']):
                        result = self.capture.point, partial
                        self.capture.cancel()
                self.status.setText('Impacto detectado. Medindo o decaimento e atualizando as PSDs…')
            if result is not None:
                second = self.phase == 'second'
                point, data = result
                actual = replace(c, duration=len(data)/c.sample_rate)
                self.capture = None
                self.phase = 'analyzing'
                def analyze():
                    self.controller.stop()
                    if second:
                        return self.study.add_confirmation(point, data, actual)
                    record = self.study.add_pilot(point, data, actual)
                    if record['accepted']:
                        self.study.suggest()
                    return record
                def analyzed(record):
                    self.update_results()
                    if second:
                        self.phase = 'finished'
                        self.status.setText('Duas batidas consistentes. A configuração está pronta para uso.' if self.study.validated else
                                            'A segunda batida não confirmou a primeira: '+' '.join(record['issues']))
                        # Continue displaying raw acquisition after comparison.
                        self._start_stream(actual, 'monitor', lambda: None)
                    elif not record['accepted']:
                        self.phase = 'needs_restart'
                        self.status.setText('Primeira batida inválida: '+' '.join(record['issues'])+' Recomece para repetir.')
                    elif self.study.recommendation.blockers:
                        self.phase = 'needs_restart'
                        self.status.setText(' '.join(self.study.recommendation.blockers))
                    else:
                        self.begin_second()
                self._work(analyze, analyzed)

    def update_results(self):
        if not self.study or not self.study.recommendation:
            return
        rec = self.study.recommendation
        first = self.study.first_metrics
        second = self.study.confirmations[-1]['metrics'] if self.study.confirmations else None
        delta = self.study.confirmations[-1]['variations'] if self.study.confirmations else {}
        number = lambda x: '—' if x is None else f'{x:.5g}'
        variation = lambda key: '—' if delta.get(key) is None else f'{delta[key]:.1%}'
        rows = [
            ('Pico da força [N]', number(first['peak_N']), number(second['peak_N']) if second else 'Aguardando', variation('peak')),
            ('Decaimento da aceleração [s]', number(first['decay_s']), number(second['decay_s']) if second else 'Aguardando', variation('decay')),
            ('Contato do martelo [s]', number(first['contact_s']), number(second['contact_s']) if second else '—', variation('contact'))]
        quality = rec.metrics.get('coherence_quality', {})
        fraction = quality.get('fraction_above')
        rows.append(('Coerência da configuração', 'Duas batidas independentes',
                     number(quality.get('median')), 'Aguardando segunda batida' if fraction is None else
                     f"{fraction:.0%} ≥ {self.study.coherence_threshold:.2f}"))
        self.results.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                self.results.setItem(i, j, QTableWidgetItem(value))
        self.plan_label.setText(f'Taxa: {rec.config.sample_rate:g} Hz\nBloco: {rec.config.n} amostras · {rec.config.duration:.5g} s\n'
                                f'Pré-trigger: {rec.config.pretrigger:.5g} s\nTrigger: {rec.config.threshold:.5g} N (50% do primeiro pico)\n'
                                f'Δf: {rec.config.sample_rate/rec.config.n:.4g} Hz')
        text = ('Coerência adequada. ' if quality.get('passed') else '')
        if fraction is not None:
            text += f"{fraction:.0%} da banda avaliável ≥ {quality['threshold']:.2f}. "
        text += ' '.join(quality.get('reasons', []))
        text += '\nAvaliação preliminar com duas batidas; frequências sem sinal suficiente são excluídas.'
        self.quality_label.setText(text)
        self.quality_label.setStyleSheet('color: #15803d;' if quality.get('passed') else 'color: #92400e;')
        self.populate_window_controls()
        ranges = '; '.join(f"{r['name']}: ±{r['recommended_max']:.3g} {r['unit']}" for r in rec.ranges)
        self.rate_hint.setText(f'Detecção inicial: {rec.metrics["initial_detection_N"]:.4g} N (5% da amplitude de entrada, quando informada). '
                               f'Consistência: pico e decaimento até {self.study.tolerance:.0%}. Ranges recomendados: {ranges}. Ajuste físico na aquisição.')

    def populate_window_controls(self):
        c = self.study.recommendation.config
        self.updating_windows = True
        self.force_window.setCurrentText(c.force_window)
        self.force_width.setValue(c.force_width)
        self.response_window.setCurrentText(c.response_window)
        if c.response_window == 'Exponencial':
            self.exponential_end.setValue(c.exponential_end)
        self.updating_windows = False
        common = ' A exponencial também multiplica a força.' if c.response_window == 'Exponencial' else ''
        self.window_hint.setText('Verde: região e peso da janela.\n'
                                f'Força: {c.force_window}. Resposta: {c.response_window}.'+common)

    def quality_requirements_changed(self, *_):
        if self.busy or self.window_error or not self.study or not self.study.recommendation or self.phase in ('changed', 'error'):
            return
        self.study.coherence_threshold = self.coherence_threshold.value()
        self.study.coherence_fraction = self.coherence_fraction.value()/100
        self.study.evaluate_quality()
        self.update_results()
        self.redraw()
        self.refresh()

    def window_controls_changed(self, *_):
        if self.updating_windows or self.busy or not self.study or not self.study.recommendation or self.phase in ('changed', 'error'):
            return
        try:
            c = replace(self.study.recommendation.config, force_window=self.force_window.currentText(),
                        force_width=self.force_width.value(), response_window=self.response_window.currentText(),
                        exponential_end=self.exponential_end.value() if self.response_window.currentText() == 'Exponencial' else 1)
            c.validate()
            self.window_error = False
            self.study.recommendation.config = c
            self.study.recommendation.metrics['windowing'] = dict(force=c.force_window, response=c.response_window)
            self.study.coherence_threshold = self.coherence_threshold.value()
            self.study.coherence_fraction = self.coherence_fraction.value()/100
            self.study.evaluate_quality()
            self.update_results()
            if self.study.confirmations:
                self.status.setText('Configuração aprovada com o janelamento atual.' if self.study.validated else
                                    'Configuração não aprovada: '+' '.join(self.study.confirmations[-1]['issues']))
        except ValueError as exc:
            self.window_error = True
            self.study.validated = False
            self.status.setText(str(exc))
        self.redraw()
        self.refresh()

    @staticmethod
    def _plot(canvas, x, y, *, x_range=None, include=()):
        canvas.times, canvas.values = np.asarray(x), np.asarray(y)
        if x_range is not None:
            canvas.x_range = x_range
        if len(x):
            canvas.x_range = x_range or (float(x[0]), max(float(x[-1]), float(x[0])+1e-6))
            finite = np.asarray(y)[np.isfinite(y)]
            if len(finite):
                low, high = float(finite.min()), float(finite.max())
                if include:
                    low, high = min(low, *include), max(high, *include)
                margin = max(.1*(high-low), abs(high)*.01, 1e-12)
                canvas.y_range = (low-margin, high+margin)
        canvas.update()

    def selected_record(self):
        if self.view.currentIndex() == 1:
            return self.study.pilots[0] if self.study.pilots else None
        if self.view.currentIndex() == 2:
            return self.study.confirmations[-1] if self.study.confirmations else None
        return self.study.confirmations[-1] if self.study.confirmations else self.study.pilots[-1] if self.study.pilots else None

    def draw_density(self, key, freq, density, title, unit, fs):
        keep = freq <= min(self.fmax.value(), fs/2)
        freq, density = freq[keep], density[keep]
        if self.psd_mode.currentIndex() == 1:
            density = 10*np.log10(np.maximum(density, 1e-30))
            unit = f'dB ref. 1 {unit}'
        self.plot_labels[key].setText(f'{title} [{unit}]')
        self._plot(self.plots[key], freq, density, x_range=(0, min(self.fmax.value(), fs/2)))
        if self.psd_mode.currentIndex() == 0 and len(density):
            self.plots[key].y_range = (0, max(float(np.max(density))*1.1, 1e-24))
        if hasattr(self.plots[key], 'thresholds'):
            self.plots[key].thresholds = []
        self.plots[key].update()

    def redraw(self, *_):
        if not self.study:
            return
        # The top channel is always continuous, unfiltered engineering data.
        t, live_values = self.live.snapshot()
        if len(t):
            raw_config = self.stream_config
            level = raw_config.threshold
            offset = raw_config.trigger_offset
            levels = ([offset+level, offset-level] if raw_config.polarity == 'Absoluto' else
                      [offset+level if raw_config.polarity == 'Positivo' else offset-level])
            self.plots['raw_force'].thresholds = levels
            self._plot(self.plots['raw_force'], t-t[-1], live_values[0], x_range=(-5, 0))
        # The lower plots stay frozen on the last completed impact.
        record = self.selected_record()
        plan = self.study.recommendation.config if self.study.recommendation else None
        lower_key = (id(self.study), id(record), id(plan), id(self.study.coherence_result),
                     self.view.currentIndex(), self.sensor.currentIndex(), self.psd_mode.currentIndex(),
                     self.response_function.currentIndex(), self.force_zoom.isChecked(),
                     self.fmin.value(), self.fmax.value(), self.coherence_threshold.value())
        if getattr(self, '_lower_plot_key', None) == lower_key:
            return
        self._lower_plot_key = lower_key
        if record is None:
            for key in ('force', 'acceleration', 'force_psd', 'acceleration_psd'):
                canvas = self.plots[key]
                canvas.times, canvas.values = np.array([]), np.array([])
                if hasattr(canvas, 'window_times'):
                    canvas.window_times, canvas.window_weights = np.array([]), np.array([])
                if hasattr(canvas, 'thresholds'):
                    canvas.thresholds = []
                canvas.update()
            if self.response_function.currentIndex() == 1:
                self.plot_labels['acceleration_psd'].setText('Coerência força × aceleração · aguardando duas batidas')
            else:
                self.plot_labels['acceleration_psd'].setText('PSD da aceleração [(m/s²)²/Hz]')
            self.last_hit_label.setText('Última batida · aguardando impacto')
            return
        source = ModalConfig.from_dict(record['config'])
        c = self.study.recommendation.config if self.study.recommendation else source
        projected = project_setup_record(record, c) if self.study.recommendation else None
        if projected is None:
            c, data = source, record['data']
        else:
            data = projected
        index = max(0, self.sensor.currentIndex())
        x = (np.arange(c.n)-c.pre)/c.sample_rate
        force, acceleration = data[:, 1], data[:, index+2]
        title = self.view.currentText()
        self.last_hit_label.setText(f'{title} · {record["point"]} · {c.sample_rate:g} Hz · {c.n} amostras')
        force_range = (-c.pretrigger, max(.04, 2*c.force_width)) if self.force_zoom.isChecked() else None
        self.plots['force'].thresholds = [c.trigger_offset+c.threshold, c.trigger_offset-c.threshold] if c.polarity == 'Absoluto' else [c.trigger_offset+(c.threshold if c.polarity == 'Positivo' else -c.threshold)]
        self._plot(self.plots['force'], x, force, x_range=force_range)
        self._plot(self.plots['acceleration'], x, acceleration)
        self.plot_labels['force'].setText('Força da batida [N] · verde = janela')
        self.plot_labels['acceleration'].setText(self.sensor.currentText()+' · aceleração [m/s²] · verde = janela')
        wf, wa = windows(c)
        for key, window, name in [('force', wf, c.force_window), ('acceleration', wa, c.response_window)]:
            canvas = self.plots[key]
            active = not np.allclose(window, 1)
            canvas.window_times = x.copy() if active else np.array([])
            canvas.window_weights = window.copy() if active else np.array([])
            canvas.window_name = name
            canvas.update()
        F, A, _, _ = hit_spectra(c, force, acceleration)
        freq = np.fft.rfftfreq(c.n, 1/c.sample_rate)
        self.draw_density('force_psd', freq, spectrum_density(F, wf, c.sample_rate), 'PSD da força', 'N²/Hz', c.sample_rate)
        if self.response_function.currentIndex() == 0:
            self.draw_density('acceleration_psd', freq, spectrum_density(A, wa, c.sample_rate),
                              'PSD da aceleração', '(m/s²)²/Hz', c.sample_rate)
        else:
            result = self.study.coherence_result
            canvas = self.plots['acceleration_psd']
            canvas.thresholds = [self.coherence_threshold.value()]
            self.plot_labels['acceleration_psd'].setText('Coerência força × aceleração · duas batidas do mesmo ponto')
            if result and np.isfinite(result['coherence']).any():
                self._plot(canvas, result['frequency'], result['coherence'], x_range=(self.fmin.value(), self.fmax.value()))
            else:
                canvas.empty_message = 'Coerência indisponível: requer duas batidas válidas.'
                self._plot(canvas, np.array([]), np.array([]), x_range=(self.fmin.value(), self.fmax.value()))
            canvas.y_range = (0, 1.05)
            canvas.update()

    def export(self):
        directory = QFileDialog.getExistingDirectory(self, 'Salvar diagnóstico das duas batidas')
        if directory:
            try:
                target = Path(directory)/f'configuracao_modal_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}'
                self.study.save(target)
                self.status.setText(f'Diagnóstico e sinais originais salvos em {target}.')
            except Exception as exc:
                self.status.setText(str(exc))

    def fail(self, error):
        self.phase = 'error'
        self.capture = None
        self.generation += 1
        self.status.setText(str(error))
        if self.study:
            self.study.validated = False
        if self.controller and self.controller.running and not self.busy:
            self._work(self.controller.stop, lambda _: None)
        self.refresh()

    def refresh(self):
        available = not self.busy
        self.restart_button.setEnabled(available)
        for control in (self.fmin, self.fmax, self.observation, self.sensor, self.point):
            control.setEnabled(available and self.phase not in ('first', 'second', 'analyzing'))
        has_rec = bool(self.study and self.study.recommendation)
        editable = available and self.phase in ('idle', 'monitor', 'finished', 'needs_restart')
        for control in (self.coherence_threshold, self.coherence_fraction):
            control.setEnabled(editable)
        for control in (self.force_window, self.response_window):
            control.setEnabled(editable and has_rec)
        self.force_width.setEnabled(editable and has_rec and self.force_window.currentText() == 'Força')
        self.exponential_end.setEnabled(editable and has_rec and self.response_window.currentText() == 'Exponencial')
        self.retry_button.setEnabled(available and has_rec and not self.study.recommendation.blockers and
                                     self.phase in ('monitor', 'finished', 'error'))
        self.export_button.setEnabled(available and has_rec)
        self.apply_button.setEnabled(available and not self.window_error and bool(self.study and self.study.validated))

    def done(self, result):
        if self.busy:
            return
        if result == QDialog.DialogCode.Accepted and not (self.study and self.study.validated):
            return
        self.generation += 1
        self.capture = None
        self.phase = 'closing'
        def closed(_=None):
            for key, value in self.old_simulator.items():
                setattr(self.backend, key, value)
            self.timer.stop()
            self.draw_timer.stop()
            self.phase = 'closed'
            super(ModalSetupDialog, self).done(result)
        if self.controller and self.controller.running:
            self._work(self.controller.stop, closed)
        else:
            closed()
