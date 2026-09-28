from __future__ import annotations

from datetime import datetime
from pathlib import Path
import queue
import sys
import threading

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QSpinBox, QFileDialog, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from ads1800_app.backends import LynxBackend, SimulatorBackend
from ads1800_app.config import ADS1800_SAMPLE_RATES, ChannelConfig, ExperimentConfig
from ads1800_app.controller import AcquisitionController

from ads1800_app.ui.plots import PlotDashboard
from dataclasses import replace



class Ads1800App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Sistema de Aquisição — LYNX ADS 1800')
        self.resize(1180, 760)
        self.setMinimumSize(900, 600)
        self.backend = None
        self.controller = None
        self.events = queue.Queue()
        self._busy = False
        self._session = 0
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        header = QHBoxLayout()
        title = QLabel('LYNX ADS 1800')
        title.setStyleSheet('font-size: 24px; font-weight: bold')
        header.addWidget(title)
        header.addWidget(QLabel('Aquisição, visualização e gravação de experimentos'))
        header.addStretch()
        self.connection_badge = QLabel('Desconectado')
        header.addWidget(self.connection_badge)
        layout.addLayout(header)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.connection_tab = QWidget()
        self.channels_tab = QWidget()
        self.acquisition_tab = QWidget()
        for tab, name in ((self.connection_tab, '1. Conexão'), (self.channels_tab, '2. Canais e experimento'),
                          (self.acquisition_tab, '3. Visualização e gravação')):
            self.tabs.addTab(tab, name)
        self._make_connection()
        self._make_channels()
        self._make_acquisition()
        self.plot.limits_changed.connect(self._set_display_limits)
        self.statusBar().showMessage('Pronto.')
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._process_events)
        self.timer.start(20)
        self._refresh_controls()

    @staticmethod
    def _button(text, callback, layout):
        button = QPushButton(text)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def _make_connection(self):
        layout = QVBoxLayout(self.connection_tab)
        self.connection_fields = QGroupBox('Equipamento')
        form = QFormLayout(self.connection_fields)
        self.mode = QComboBox()
        self.mode.addItems(['ADS 1800 real', 'Simulador'])
        self.ip = QLineEdit('192.168.1.180')
        form.addRow('Modo', self.mode)
        form.addRow('Endereço IP', self.ip)
        layout.addWidget(self.connection_fields)
        self.connect_button = self._button('Conectar e reconhecer', self._toggle_connection, layout)
        self.device_info = QLabel('Nenhum equipamento conectado.')
        self.device_info.setWordWrap(True)
        layout.addWidget(self.device_info)
        note = QLabel('Configure e salve os parâmetros elétricos dos sensores no ADS 1800 pelo Assistente da LYNX antes da aquisição.')
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()

    def _make_channels(self):
        layout = QVBoxLayout(self.channels_tab)
        form = QFormLayout()
        self.exp_name = QLineEdit('Experimento')
        self.operator = QLineEdit()
        self.description = QLineEdit()
        self.frequency = QComboBox()
        self.frequency.setEditable(True)
        self.frequency.addItems([str(rate) for rate in ADS1800_SAMPLE_RATES])
        self.frequency.setCurrentText('1000')
        self.frequency_limit = QLabel('ADS 1800: até 24000 Hz por canal. Conecte para consultar as taxas disponíveis.')
        self.frequency_limit.setWordWrap(True)
        self.device_timestamp = QCheckBox('Usar relógio UTC do equipamento')
        for label, widget in [('Nome', self.exp_name), ('Operador', self.operator), ('Descrição', self.description),
                              ('Frequência (Hz)', self.frequency), ('Tempo', self.device_timestamp)]:
            form.addRow(label, widget)
        form.addRow('', self.frequency_limit)
        layout.addLayout(form)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        grid = QGridLayout(content)
        grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.channel_grid = grid
        self.channel_widgets = []
        self.device_channels = []
        self._selected_channels = {0}
        self._display_limits = {}
        self.channel_hint = QLabel('Conecte ao equipamento para selecionar os canais.')
        grid.addWidget(self.channel_hint, 0, 0)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        note = QLabel('Nomes, unidades e limites de engenharia são lidos do equipamento ao conectar. '
                      'Após alterar a configuração no Assistente LYNX, desconecte e conecte novamente.')
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QHBoxLayout()
        self._button('Salvar experimento...', self._save_config, buttons)
        self._button('Carregar experimento...', self._load_config, buttons)
        layout.addLayout(buttons)

    def _show_device_channels(self, channels):
        if self.channel_widgets:
            self._selected_channels = {c.number for c, w in zip(self.device_channels, self.channel_widgets)
                                       if w['enabled'].isChecked()}
        for widgets in self.channel_widgets:
            self.channel_grid.removeWidget(widgets['enabled'])
            widgets['enabled'].deleteLater()
        self.device_channels = [replace(channel) for channel in channels]
        self.channel_widgets = []
        self.channel_hint.setVisible(not channels)
        for row, channel in enumerate(self.device_channels, 1):
            checkbox = QCheckBox(f'CH {channel.number + 1} · {channel.label()} [{channel.unit}]')
            checkbox.setChecked(channel.number in self._selected_channels)
            checkbox.setToolTip(f'Limites de engenharia do equipamento: '
                               f'{channel.engineering_min:g} a {channel.engineering_max:g} {channel.unit}')
            self.channel_grid.addWidget(checkbox, row, 0)
            self.channel_widgets.append({'enabled': checkbox})

    def _set_display_limits(self, index, low, high, automatic):
        self._display_limits[index] = (low, high, automatic)

    def _make_acquisition(self):
        layout = QVBoxLayout(self.acquisition_tab)
        controls = QHBoxLayout()
        self.start_button = self._button('Iniciar aquisição', self._start_acquisition, controls)
        self.stop_button = self._button('Parar', self._stop_acquisition, controls)
        self.record_button = self._button('Iniciar gravação CSV', self._toggle_recording, controls)
        self.elapsed = QLabel('0 amostras | 0 perdidas')
        controls.addWidget(self.elapsed)
        layout.addLayout(controls)
        display = QHBoxLayout()
        self.time_window = QDoubleSpinBox()
        self.time_window.setRange(0.1, 60)
        self.time_window.setDecimals(1)
        self.time_window.setValue(10)
        self.time_window.setSuffix(' s')
        self.refresh_rate = QSpinBox()
        self.refresh_rate.setRange(1, 30)
        self.refresh_rate.setValue(10)
        self.refresh_rate.setSuffix(' Hz')
        self.refresh_rate.setToolTip('Taxa de desenho da tela. A aquisição e o CSV mantêm a frequência de amostragem escolhida; cada atualização visual mostra os dados mais recentes.')
        self.plot_columns = QComboBox()
        self.plot_columns.addItems(['1 coluna', '2 colunas'])
        self.plot_columns.setCurrentIndex(1)
        for name, field in [('Janela horizontal', self.time_window), ('Atualização visual', self.refresh_rate), ('Gráficos', self.plot_columns)]:
            display.addWidget(QLabel(name))
            display.addWidget(field)
        display.addStretch()
        self._button('Organizar gráficos', lambda: self.plot.set_columns(self.plot_columns.currentIndex() + 1), display)
        layout.addLayout(display)
        note = QLabel('Arraste as bordas ou os cantos para redimensionar cada gráfico e a barra de título para movê-lo. Duplo clique no título amplia/restaura.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.plot = PlotDashboard()
        layout.addWidget(QLabel('Mostrar gráficos:'))
        layout.addWidget(self.plot.channel_controls)
        self.time_window.valueChanged.connect(self.plot.set_window)
        self.refresh_rate.valueChanged.connect(self.plot.set_refresh_rate)
        self.plot_columns.currentIndexChanged.connect(lambda index: self.plot.set_columns(index + 1))
        layout.addWidget(self.plot, 1)
        layout.addWidget(self.plot.live_status)
        self.recording_label = QLabel('Aquisição parada.')
        layout.addWidget(self.recording_label)

    def _work(self, action, completed):
        # Workers never access widgets; the Qt timer consumes their results.
        self._busy = True
        self._refresh_controls()
        def worker():
            try:
                result = action()
                self.events.put(('done', completed, result))
            except Exception as exc:
                self.events.put(('failed', exc))
        threading.Thread(target=worker, daemon=True).start()

    def _refresh_controls(self):
        connected = bool(self.backend and self.backend.connected)
        running = bool(self.controller and self.controller.running)
        self.connect_button.setEnabled(not self._busy and not running)
        self.connect_button.setText('Desconectar' if connected else 'Conectar e reconhecer')
        self.connection_fields.setEnabled(not self._busy and not connected)
        self.channels_tab.setEnabled(not self._busy and not running)
        self.start_button.setEnabled(connected and not running and not self._busy)
        self.stop_button.setEnabled(running and not self._busy)
        self.record_button.setEnabled(running and not self._busy)
        recording = bool(self.controller and self.controller.recording)
        self.record_button.setText('Encerrar gravação' if recording else 'Iniciar gravação CSV')

    def _toggle_connection(self):
        if self.backend and self.backend.connected:
            def disconnected(_):
                self.backend = self.controller = None
                self._show_device_channels([])
                self.connection_badge.setText('Desconectado')
                self.device_info.setText('Nenhum equipamento conectado.')
                self.frequency_limit.setText('Conecte para consultar as taxas disponíveis no equipamento.')
            self._work(self.backend.disconnect, disconnected)
            return
        backend = SimulatorBackend() if self.mode.currentText() == 'Simulador' else LynxBackend()
        ip = self.ip.text().strip()
        def connected(info):
            self._show_device_channels(info.channels)
            self.backend = backend
            self.controller = AcquisitionController(backend, self._on_data, self._on_error)
            self.connection_badge.setText('Conectado')
            self.device_info.setText(f'{info.name} | IP: {info.ip} | Canais analógicos: {info.channel_count}')
            if info.available_sample_rates:
                previous = self.frequency.currentText()
                rates = [f'{v:g}' for v in sorted(set(info.available_sample_rates))]
                self.frequency.clear()
                self.frequency.addItems(rates)
                self.frequency.setCurrentText(previous if previous in rates else rates[0])
                self.frequency_limit.setText(f'Máxima informada: {max(info.available_sample_rates):g} Hz por canal. Selecione uma das taxas disponíveis.')
            else:
                self.frequency_limit.setText('Equipamento não informou as taxas; a frequência digitada será validada pelo ADS 1800.')
            self.tabs.setCurrentWidget(self.channels_tab)
        self.statusBar().showMessage('Conectando...')
        self._work(lambda: backend.connect(ip), connected)

    def _on_data(self, times, values):
        self.events.put(('data', self._session, times, values))

    def _on_error(self, exc):
        self.events.put(('error', exc))

    def _read_config(self):
        if not self.device_channels:
            raise ValueError('Conecte ao equipamento para ler os canais e seus limites.')
        channels = []
        for channel, widgets in zip(self.device_channels, self.channel_widgets):
            low, high, automatic = self._display_limits.get(channel.number, (-1, 1, True))
            channels.append(replace(channel, enabled=widgets['enabled'].isChecked(),
                                    display_min=low, display_max=high, display_auto=automatic))
        config = ExperimentConfig(name=self.exp_name.text().strip() or 'Experimento',
                                  operator=self.operator.text(), description=self.description.text(),
                                  device_ip=self.ip.text().strip(), sample_rate=float(self.frequency.currentText().replace(',', '.')),
                                  use_device_timestamp=self.device_timestamp.isChecked(), channels=channels)
        config.validate()
        return config

    def _apply_config(self, config):
        config.validate()
        self.exp_name.setText(config.name)
        self.operator.setText(config.operator)
        self.description.setText(config.description)
        if not self.backend:
            self.ip.setText(config.device_ip)
        self.frequency.setCurrentText(f'{config.sample_rate:g}')
        self.device_timestamp.setChecked(config.use_device_timestamp)
        # Saved sensor calibration is legacy data. Only selection and view preferences
        # are restored; connected hardware remains the authority for measurements.
        self._selected_channels = {c.number for c in config.channels if c.enabled}
        self._display_limits = {c.number: (c.display_min, c.display_max, c.display_auto)
                                for c in config.channels}
        for channel, widgets in zip(self.device_channels, self.channel_widgets):
            widgets['enabled'].setChecked(channel.number in self._selected_channels)

    def _save_config(self):
        try:
            config = self._read_config()
            path, _ = QFileDialog.getSaveFileName(self, 'Salvar configuração', 'experimento.json', 'Configuração JSON (*.json)')
            if path:
                config.save(path)
        except Exception as exc:
            self._show_error(exc)

    def _load_config(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Carregar configuração', '', 'Configuração JSON (*.json)')
        if path:
            try:
                self._apply_config(ExperimentConfig.load(path))
            except Exception as exc:
                self._show_error(exc)

    def _start_acquisition(self):
        if not self.controller or self._busy or self.controller.running:
            return
        try:
            config = self._read_config()
        except Exception as exc:
            self._show_error(exc)
            return
        self._session += 1
        self.plot.reset(config.enabled_channels)
        def started(_):
            self.recording_label.setText('Aquisição em andamento.')
            self.statusBar().showMessage('Aquisição iniciada.')
        self._work(lambda: self.controller.start(config), started)

    def _stop_acquisition(self):
        if self.controller and not self._busy:
            self.statusBar().showMessage('Encerrando aquisição e finalizando CSV...')
            self._work(self.controller.stop, lambda _: self.recording_label.setText('Aquisição encerrada.'))

    def _toggle_recording(self):
        if not self.controller or self._busy:
            return
        if self.controller.recording:
            self._work(self.controller.stop_recording, lambda p: self.recording_label.setText(f'Gravação encerrada. Arquivo: {p}'))
            return
        directory = Path(__file__).resolve().parents[2] / 'dados'
        path, _ = QFileDialog.getSaveFileName(self, 'Salvar dados', str(directory / f'experimento_{datetime.now():%Y%m%d_%H%M%S}.csv'), 'Arquivo CSV (*.csv)')
        if path:
            try:
                self.controller.start_recording(path)
                self.recording_label.setText(f'Gravando em {path}')
            except Exception as exc:
                self._show_error(exc)
        self._refresh_controls()

    def _show_error(self, exc):
        self.statusBar().showMessage(f'Erro: {exc}')
        QMessageBox.critical(self, 'Erro', str(exc))

    def _process_events(self):
        # Bound each batch so a large backlog cannot monopolize the UI loop.
        for _ in range(200):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind = event[0]
            if kind == 'data':
                if event[1] == self._session:
                    self.plot.append(event[2], event[3])
            elif kind == 'done':
                self._busy = False
                event[1](event[2])
            elif kind in ('error', 'failed'):
                if kind == 'failed':
                    self._busy = False
                self._show_error(event[1])
        if self.controller:
            lost = self.backend.samples_lost() if self.backend else 0
            self.elapsed.setText(f'{self.controller.total_samples} amostras | {lost} perdidas')
        self._refresh_controls()

    def closeEvent(self, event):
        if self._busy:
            event.ignore()
            self.statusBar().showMessage('Aguarde a operação terminar antes de fechar.')
            return
        if self.backend:
            event.ignore()
            def shutdown():
                if self.controller:
                    self.controller.stop()
                self.backend.disconnect()
            def closed(_):
                self.backend = self.controller = None
                self.close()
            self._work(shutdown, closed)
            return
        self.timer.stop()
        event.accept()


def run():
    app = QApplication.instance() or QApplication(sys.argv)
    window = Ads1800App()
    window.show()
    sys.exit(app.exec())
