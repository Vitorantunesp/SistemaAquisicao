"""Alternative bridge monitoring interface using the tested acquisition controller."""
from dataclasses import fields
from datetime import datetime
from pathlib import Path
import sys
import time
import json
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QApplication, QCheckBox, QDoubleSpinBox, QSpinBox, QComboBox,
                            QFormLayout, QGroupBox, QHBoxLayout, QVBoxLayout, QLabel,
                            QPushButton, QFileDialog, QDialog, QDialogButtonBox, QMessageBox,
                            QWidget, QSplitter)
from ads1800_app.config import ExperimentConfig
from ads1800_app.monitor_signal import MonitorConfig
from ads1800_app.ui.app import Ads1800App
from ads1800_app.ui.bridge_plots import BridgeDashboard, BridgeMap
from ads1800_app.ui.bridge_image import (DEFAULT_IMAGE, PROJECT_ROOT, import_image,
                                        load_pixmap, save_preferences, validate_positions)


class BridgeApp(Ads1800App):
    def __init__(self):
        self._active_rate = 1000
        self._last_received = None
        self._bridge_image = DEFAULT_IMAGE
        self._sensor_positions = {}
        self._visual_preferences = PROJECT_ROOT / 'configuracoes' / 'ponte_visual.json'
        super().__init__()
        self._restore_visual_preferences()
        self.setWindowTitle('Monitoramento em Tempo Real — Ponte em Miniatura')
        self.resize(1500, 980)
        header = self.centralWidget().layout().itemAt(0).layout()
        header.itemAt(0).widget().setText('Monitoramento em Tempo Real')
        header.itemAt(1).widget().setText('Ponte em Miniatura · Laboratório de Estruturas')
        self.tabs.setTabText(1, '2. Configurações')
        self.tabs.setTabText(2, '3. Monitoramento')
        self.exp_name.setText('Monitoramento da ponte')
        self.setStyleSheet('''
            QMainWindow, QTabWidget::pane {background: #0e1d29;}
            QWidget {font-family: "Segoe UI"; font-size: 12px; color: #edf3f8; background: #0e1d29;}
            QGroupBox QLabel, QGroupBox QWidget {background: transparent;}
            MonitorPanel, MonitorPanel QWidget {background: #f7f9fc; color: #172b40;}
            QGroupBox {background: #1a2d3d; border: 1px solid #354e61; border-radius: 7px;
                       margin-top: 15px; padding: 12px; padding-top: 18px; font-weight: 600;}
            QGroupBox::title {subcontrol-origin: margin; left: 12px;}
            QPushButton {background: #294257; border: 1px solid #405f77; border-radius: 5px; padding: 10px 14px;}
            QPushButton:hover, QPushButton:checked {background: #176cc0;}
            QPushButton:disabled {color: #718595; background: #21313e;}
            QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {background: #203749; padding: 5px; border: 1px solid #476074;}
            QComboBox QAbstractItemView {background: #203749; color: white;}
            QTabBar::tab {background: #1b3040; padding: 10px 22px;}
            QTabBar::tab:selected {background: #176cc0;}
            QScrollArea {border: 0; background: #102331;}
            QSplitter::handle:vertical {background: #354e61; border-radius: 3px;}
            QSplitter::handle:vertical:hover {background: #176cc0;}
            QMessageBox {background: #203749;}
        ''')
        self.start_button.setStyleSheet('background: #09995b; color: white; font-weight: bold;')
        self.stop_button.setStyleSheet('background: #c73b42; color: white; font-weight: bold;')

    def _make_channels(self):
        super()._make_channels()
        selected_rate = self.frequency.currentText()
        self.frequency.setEditable(False)
        self.frequency.setCurrentText(selected_rate)
        group = QGroupBox('Tratamento dos resultados')
        form = QFormLayout(group)
        self.filter_enabled = QCheckBox('Ativar filtro passa-banda Butterworth')
        self.low_cut, self.high_cut = QDoubleSpinBox(), QDoubleSpinBox()
        for field, value in ((self.low_cut, 1), (self.high_cut, 100)):
            field.setRange(.001, 1e7)
            field.setDecimals(3)
            field.setValue(value)
            field.setSuffix(' Hz')
            field.setEnabled(False)
            self.filter_enabled.toggled.connect(field.setEnabled)
        form.addRow(self.filter_enabled)
        form.addRow('Frequência mínima de corte', self.low_cut)
        form.addRow('Frequência máxima de corte', self.high_cut)
        note = QLabel('Aplicado ao tempo, RMS, pico, média, FFT e PSD. CSV mantém dados originais sem filtro.\n'
                      'Filtro causal: há atraso de fase e transiente inicial. Cortes devem estar abaixo de Nyquist (fs/2).')
        note.setWordWrap(True)
        form.addRow(note)
        self.channels_tab.layout().insertWidget(1, group)
        image_controls = QHBoxLayout()
        self._button('Selecionar imagem da ponte…', self._choose_bridge_image, image_controls)
        self._button('Posicionar sensores…', self._edit_sensor_positions, image_controls)
        self.channels_tab.layout().insertLayout(2, image_controls)
        self.bridge_image_label = QLabel('Imagem: ponte_sem_fundo.png')
        self.channels_tab.layout().insertWidget(3, self.bridge_image_label)
        self._button('Abrir monitoramento', lambda: self.tabs.setCurrentWidget(self.acquisition_tab), self.channels_tab.layout())

    def _make_acquisition(self):
        layout = QVBoxLayout(self.acquisition_tab)
        self.monitor_splitter = QSplitter(Qt.Orientation.Vertical)
        self.monitor_splitter.setChildrenCollapsible(False)
        self.monitor_splitter.setHandleWidth(9)
        layout.addWidget(self.monitor_splitter, 1)
        upper_panel = QWidget()
        top = QHBoxLayout(upper_panel)
        top.setContentsMargins(0, 0, 0, 0)
        bridge = QGroupBox('Posição dos sensores — ponte do laboratório')
        bridge_layout = QVBoxLayout(bridge)
        self.bridge_map = BridgeMap()
        self.bridge_map.setMinimumHeight(100)
        bridge_layout.addWidget(self.bridge_map)
        top.addWidget(bridge, 5)
        info = QGroupBox('Informações da aquisição')
        info_layout = QVBoxLayout(info)
        self.clock = QLabel()
        self.rate_label = QLabel('Taxa de amostragem: —')
        self.duration_label = QLabel('Tempo adquirido: 00:00:00')
        self.elapsed = QLabel('0 amostras | 0 perdidas')
        self.state_label = QLabel('● Desconectado')
        for label in (self.clock, self.rate_label, self.duration_label, self.elapsed, self.state_label):
            info_layout.addWidget(label)
        top.addWidget(info, 3)
        controls = QGroupBox('Controles')
        control_layout = QVBoxLayout(controls)
        row = QHBoxLayout()
        self.start_button = self._button('▶ Iniciar aquisição', self._start_acquisition, row)
        self.stop_button = self._button('■ Parar', self._stop_acquisition, row)
        control_layout.addLayout(row)
        row = QHBoxLayout()
        self._button('Limpar gráficos', lambda: self.plot.clear(), row)
        self._button('Configurações', lambda: self.tabs.setCurrentWidget(self.channels_tab), row)
        control_layout.addLayout(row)
        self.record_button = self._button('Iniciar gravação CSV', self._toggle_recording, control_layout)
        top.addWidget(controls, 3)
        self.monitor_splitter.addWidget(upper_panel)
        lower_panel = QWidget()
        self.monitor_splitter.addWidget(lower_panel)
        layout = QVBoxLayout(lower_panel)
        layout.setContentsMargins(0, 0, 0, 0)
        self.monitor_splitter.setStretchFactor(0, 0)
        self.monitor_splitter.setStretchFactor(1, 1)
        self.monitor_splitter.setSizes([300, 560])
        self.monitor_splitter.handle(1).setToolTip('Arraste para ajustar a altura do painel superior e dos gráficos')
        display = QHBoxLayout()
        self.time_window = QDoubleSpinBox()
        self.time_window.setRange(.1, 60)
        self.time_window.setValue(20)
        self.time_window.setSuffix(' s')
        self.refresh_rate = QSpinBox()
        self.refresh_rate.setRange(1, 30)
        self.refresh_rate.setValue(10)
        self.plot_columns = QComboBox()
        self.plot_columns.addItems(['1 coluna', '2 colunas'])
        self.plot_columns.setCurrentIndex(1)
        for name, field in [('Janela', self.time_window), ('Atualização visual (Hz)', self.refresh_rate), ('Gráficos', self.plot_columns)]:
            display.addWidget(QLabel(name))
            display.addWidget(field)
        display.addStretch()
        layout.addLayout(display)
        self.plot = BridgeDashboard()
        self.plot.setMinimumHeight(150)
        self.time_window.valueChanged.connect(self.plot.set_window)
        self.refresh_rate.valueChanged.connect(self.plot.set_refresh_rate)
        self.plot_columns.currentIndexChanged.connect(lambda i: self.plot.set_columns(i + 1))
        layout.addWidget(self.plot, 1)
        modes = QHBoxLayout()
        modes.addWidget(QLabel('Visualização'))
        self.mode_buttons = {}
        for mode in ('Tempo', 'FFT', 'Espectro', 'Todos'):
            button = QPushButton('Espectro (PSD)' if mode == 'Espectro' else mode)
            button.setCheckable(True)
            button.setChecked(mode == 'Tempo')
            button.clicked.connect(lambda checked=False, m=mode: self._set_mode(m))
            modes.addWidget(button)
            self.mode_buttons[mode] = button
        modes.addStretch()
        layout.addLayout(modes)
        layout.addWidget(self.plot.live_status)
        self.recording_label = QLabel('Aquisição parada. Selecione os canais na guia Configurações.')
        layout.addWidget(self.recording_label)

    def _set_mode(self, mode):
        for name, button in self.mode_buttons.items():
            button.setChecked(name == mode)
        self.plot.set_mode(mode)

    def _show_device_channels(self, channels):
        super()._show_device_channels(channels)
        for widgets in self.channel_widgets:
            widgets['enabled'].toggled.connect(self._update_map)
        self._update_map()

    def _update_map(self):
        self.bridge_map.channels = [ch for ch, w in zip(self.device_channels, self.channel_widgets) if w['enabled'].isChecked()]
        self.bridge_map.update()

    def _set_visual(self, image, positions):
        validate_positions(positions)
        self.bridge_map.set_image(image)
        self.bridge_map.set_positions(positions)
        self._bridge_image = image
        self._sensor_positions = {key: list(xy) for key, xy in positions.items()}
        self.bridge_image_label.setText(f'Imagem: {Path(image).name}')

    def _restore_visual_preferences(self):
        try:
            if self._visual_preferences.exists():
                data = json.loads(self._visual_preferences.read_text(encoding='utf-8'))
                self._set_visual(data['bridge_image'], data['sensor_positions'])
            else:
                self._set_visual(DEFAULT_IMAGE, {})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            try:
                self._set_visual(DEFAULT_IMAGE, {})
            except ValueError:
                pass
            self.statusBar().showMessage(f'Não foi possível restaurar a imagem/posições: {exc}')

    def _choose_bridge_image(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Selecionar imagem da ponte', '', 'Imagens (*.png *.jpg *.jpeg)')
        if not path:
            return
        try:
            image = import_image(path)
            # A different photograph has different coordinates: never silently reuse markers.
            positions = self._sensor_positions if image == self._bridge_image else {}
            save_preferences(self._visual_preferences, image, positions)
            self._set_visual(image, positions)
            self.statusBar().showMessage('Imagem salva. Use Posicionar sensores para conferir os canais.')
        except (OSError, ValueError) as exc:
            self._show_error(exc)

    def _edit_sensor_positions(self):
        channels = [ch for ch, w in zip(self.device_channels, self.channel_widgets) if w['enabled'].isChecked()]
        if not channels:
            QMessageBox.information(self, 'Posicionar sensores', 'Conecte ao equipamento e selecione os canais primeiro.')
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Posições dos sensores — arraste os círculos sobre a ponte')
        dialog.resize(1100, 650)
        layout = QVBoxLayout(dialog)
        note = QLabel('Arraste cada círculo até a posição real do sensor. CH corresponde ao canal do equipamento.')
        note.setWordWrap(True)
        layout.addWidget(note)
        editor = BridgeMap(editable=True)
        editor.channels = channels
        try:
            editor.set_image(self._bridge_image)
        except ValueError as exc:
            self._show_error(exc)
            return
        editor.set_positions(self._sensor_positions)
        layout.addWidget(editor, 1)
        buttons = QDialogButtonBox()
        buttons.addButton('Salvar posições', QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton('Cancelar', QDialogButtonBox.ButtonRole.RejectRole)
        buttons.rejected.connect(dialog.reject)
        def save():
            try:
                save_preferences(self._visual_preferences, self._bridge_image, editor.positions)
                self._set_visual(self._bridge_image, editor.positions)
                dialog.accept()
            except (OSError, ValueError) as exc:
                self._show_error(exc)
        buttons.accepted.connect(save)
        layout.addWidget(buttons)
        dialog.exec()

    def _read_config(self):
        base = super()._read_config()
        config = MonitorConfig(**{f.name: getattr(base, f.name) for f in fields(ExperimentConfig)},
                               bandpass_enabled=self.filter_enabled.isChecked(),
                               low_cut=self.low_cut.value(), high_cut=self.high_cut.value(),
                               bridge_image=self._bridge_image,
                               sensor_positions={key: list(xy) for key, xy in self._sensor_positions.items()})
        config.validate()
        rates = [float(self.frequency.itemText(i)) for i in range(self.frequency.count())]
        if config.sample_rate not in rates:
            raise ValueError('Selecione uma frequência disponível no equipamento.')
        return config

    def _apply_config(self, config):
        config.validate()
        if self.frequency.findText(f'{config.sample_rate:g}') < 0:
            raise ValueError('A frequência salva não está disponível na lista atual. Conecte ao equipamento correspondente.')
        image = getattr(config, 'bridge_image', DEFAULT_IMAGE)
        positions = getattr(config, 'sensor_positions', {})
        validate_positions(positions)
        load_pixmap(image)
        save_preferences(self._visual_preferences, image, positions)
        super()._apply_config(config)
        self._set_visual(image, positions)
        self.filter_enabled.setChecked(getattr(config, 'bandpass_enabled', False))
        self.low_cut.setValue(getattr(config, 'low_cut', 1))
        self.high_cut.setValue(getattr(config, 'high_cut', 100))
        self._update_map()

    def _load_config(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Carregar configuração da ponte', '', 'Configuração JSON (*.json)')
        if path:
            try:
                self._apply_config(MonitorConfig.load(path))
            except Exception as exc:
                self._show_error(exc)

    def _save_config(self):
        try:
            config = self._read_config()
            path, _ = QFileDialog.getSaveFileName(self, 'Salvar configuração da ponte', 'ponte.json', 'Configuração JSON (*.json)')
            if path:
                config.save(path)
        except Exception as exc:
            self._show_error(exc)

    def _start_acquisition(self):
        if not self.controller or self._busy or self.controller.running:
            return
        try:
            config = self._read_config()
            self.plot.configure(config)
        except Exception as exc:
            self._show_error(exc)
            return
        self._active_rate = config.sample_rate
        self._last_received = None
        self.rate_label.setText(f'Taxa de amostragem: {config.sample_rate:g} Hz')
        super()._start_acquisition()

    def _on_data(self, times, values):
        self._last_received = time.monotonic()
        super()._on_data(times, values)

    def _process_events(self):
        super()._process_events()
        self.clock.setText(datetime.now().strftime('%d/%m/%Y  %H:%M:%S'))
        connected = bool(self.backend and self.backend.connected)
        running = bool(self.controller and self.controller.running)
        recent = self._last_received is not None and time.monotonic() - self._last_received < max(2, 2 / self._active_rate)
        state = ('Recebendo dados' if recent else 'Aguardando dados') if running else ('Aquisição parada' if connected else 'Desconectado')
        self.state_label.setText('● ' + state)
        self.state_label.setStyleSheet(f'color: {"#41dc82" if running and recent else "#e6bb6a"}')
        samples = self.controller.total_samples if self.controller else 0
        seconds = int(samples / self._active_rate)
        self.duration_label.setText(f'Tempo adquirido: {seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}')


def run():
    app = QApplication.instance() or QApplication(sys.argv)
    window = BridgeApp()
    window.show()
    sys.exit(app.exec())
