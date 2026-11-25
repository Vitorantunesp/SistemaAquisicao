"""Property panel on the left, continuous hammer above, last hit below."""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QGroupBox, QScrollArea, QLabel, QComboBox, QDoubleSpinBox, QPushButton,
    QCheckBox, QTableWidget, QHeaderView, QSplitter)
from PyQt6.QtCore import Qt

from ads1800_app.ui.plots import ChannelCanvas
from ads1800_app.ui.modal_setup_plots import WindowCanvas, TriggerCanvas


def _group(layout, title):
    group = QGroupBox(title)
    form = QFormLayout(group)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    layout.addWidget(group)
    return form


def build_setup_layout(owner):
    root = QVBoxLayout(owner)
    title = QLabel('Configuração da aquisição por impacto')
    title.setStyleSheet('font-size: 15px; font-weight: 600;')
    root.addWidget(title)
    split = QSplitter(Qt.Orientation.Horizontal)
    root.addWidget(split, 1)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setMinimumWidth(290)
    scroll.setMaximumWidth(370)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    properties = QWidget()
    left = QVBoxLayout(properties)
    left.setContentsMargins(8, 8, 8, 8)
    scroll.setWidget(properties)
    split.addWidget(scroll)
    owner.property_panel = scroll
    form = _group(left, 'Aquisição e trigger')
    owner.fmin = owner.number(1, .01, 1e6)
    owner.fmax = owner.number(500, .02, 1e6)
    owner.observation = owner.number(8, .5, 120)
    owner.sensor = QComboBox()
    owner.sensor.addItems([f"{s['name']} · CH {s['channel']+1}" for s in owner.base.sensors])
    owner.point = QComboBox()
    owner.point.addItems([p[0] for p in owner.base.points])
    for title, control in [('Frequência mínima [Hz]', owner.fmin), ('Frequência máxima [Hz]', owner.fmax),
                           ('Observação máxima [s]', owner.observation), ('Acelerômetro', owner.sensor),
                           ('Ponto das batidas', owner.point)]:
        form.addRow(title, control)
    owner.restart_button = QPushButton('Recomeçar as duas batidas')
    owner.restart_button.clicked.connect(owner.restart)
    form.addRow(owner.restart_button)
    owner.plan_label = QLabel('Primeira batida: medir o pico e o decaimento.\nSegunda batida: conferir a configuração.')
    owner.plan_label.setWordWrap(True)
    form.addRow(owner.plan_label)
    quality = _group(left, 'Qualidade por coerência')
    owner.coherence_threshold = owner.number(.9, .01, 1)
    owner.coherence_threshold.setDecimals(2)
    owner.coherence_fraction = owner.number(80, 1, 100)
    owner.coherence_fraction.setDecimals(0)
    owner.coherence_fraction.setSuffix(' %')
    quality.addRow('Coerência mínima', owner.coherence_threshold)
    quality.addRow('Parcela da banda avaliável', owner.coherence_fraction)
    owner.quality_label = QLabel('Aguardando duas batidas do mesmo ponto.')
    owner.quality_label.setWordWrap(True)
    quality.addRow(owner.quality_label)
    win = _group(left, 'Janelamento da última batida')
    owner.force_window = QComboBox()
    owner.force_window.addItems(['Força', 'Retangular'])
    owner.force_width = owner.number(.03, .000001, 60)
    owner.force_width.setDecimals(6)
    owner.response_window = QComboBox()
    owner.response_window.addItems(['Retangular', 'Exponencial'])
    owner.exponential_end = owner.number(.01, .001, 1)
    owner.exponential_end.setDecimals(4)
    for title, control in [('Janela de força', owner.force_window), ('Duração após trigger [s]', owner.force_width),
                           ('Janela da resposta', owner.response_window), ('Resíduo exponencial', owner.exponential_end)]:
        win.addRow(title, control)
    owner.window_hint = QLabel('Região verde = peso da janela.\nAguardando a primeira batida.')
    owner.window_hint.setWordWrap(True)
    owner.window_hint.setMinimumHeight(70)
    win.addRow(owner.window_hint)
    display = _group(left, 'Exibição')
    owner.view = QComboBox()
    owner.view.addItems(['Última batida', 'Primeira batida', 'Segunda batida'])
    owner.psd_mode = QComboBox()
    owner.psd_mode.addItems(['PSD: magnitude', 'PSD: dB'])
    owner.response_function = QComboBox()
    owner.response_function.addItems(['PSD da aceleração', 'Coerência força × aceleração'])
    for combo in (owner.sensor, owner.point, owner.view, owner.psd_mode, owner.response_function,
                  owner.force_window, owner.response_window):
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(9)
    owner.force_zoom = QCheckBox('Ampliar pulso da força')
    owner.force_zoom.setChecked(True)
    display.addRow('Registro', owner.view)
    display.addRow('Função da resposta', owner.response_function)
    display.addRow('Escala dos espectros', owner.psd_mode)
    display.addRow(owner.force_zoom)
    owner.rate_hint = QLabel('Detecção inicial em 5% da entrada; trigger sugerido em 50% do pico.')
    owner.rate_hint.setWordWrap(True)
    owner.rate_hint.setStyleSheet('color: #475569; font-size: 11px;')
    left.addWidget(owner.rate_hint)
    left.addStretch()
    owner.plot_area = QWidget()
    right = QVBoxLayout(owner.plot_area)
    right.setContentsMargins(5, 0, 0, 0)
    split.addWidget(owner.plot_area)
    split.setStretchFactor(1, 1)
    split.setSizes([320, 1100])
    owner.plots, owner.plot_labels = {}, {}
    raw_title = QLabel('Martelo bruto · aquisição contínua · últimos 5 s')
    right.addWidget(raw_title)
    raw = TriggerCanvas()
    raw.setMinimumHeight(120)
    raw.setMaximumHeight(160)
    right.addWidget(raw)
    owner.plots['raw_force'] = raw
    owner.plot_labels['raw_force'] = raw_title
    owner.last_hit_label = QLabel('Última batida · aguardando impacto')
    owner.last_hit_label.setStyleSheet('font-weight: 600;')
    right.addWidget(owner.last_hit_label)
    panels = QGridLayout()
    for row, time_key, spectrum_key, time_title, spectrum_title in [
        (0, 'force', 'force_psd', 'Força original [N]', 'PSD da força [N²/Hz]'),
        (1, 'acceleration', 'acceleration_psd', 'Aceleração original [m/s²]', 'PSD da aceleração [(m/s²)²/Hz]')]:
        for col, key, title in [(0, time_key, time_title), (1, spectrum_key, spectrum_title)]:
            box = QVBoxLayout()
            label = QLabel(title)
            box.addWidget(label)
            canvas = (TriggerCanvas() if key in ('force', 'acceleration_psd') else WindowCanvas()
                      if col == 0 else ChannelCanvas('#16a34a'))
            if col == 1:
                canvas.color = '#16a34a'
            canvas.empty_message = 'Aguardando a última batida...'
            canvas.setMinimumSize(270, 155)
            canvas.x_label = 'Tempo [s]' if col == 0 else 'Frequência [Hz]'
            box.addWidget(canvas, 1)
            owner.plots[key], owner.plot_labels[key] = canvas, label
            panels.addLayout(box, row, col)
    right.addLayout(panels, 1)
    owner.results = QTableWidget(0, 4)
    owner.results.setHorizontalHeaderLabels(['Parâmetro', 'Primeira / sugestão', 'Segunda', 'Variação / qualidade'])
    owner.results.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    owner.results.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    owner.results.verticalHeader().setDefaultSectionSize(24)
    owner.results.verticalHeader().setMinimumSectionSize(24)
    owner.results.setMinimumHeight(115)
    owner.results.setMaximumHeight(145)
    right.addWidget(owner.results)
    owner.status = QLabel('Iniciando a visualização do martelo bruto…')
    owner.status.setWordWrap(True)
    root.addWidget(owner.status)
    actions = QHBoxLayout()
    owner.retry_button = QPushButton('Repetir segunda batida')
    owner.retry_button.clicked.connect(owner.begin_second)
    actions.addWidget(owner.retry_button)
    owner.export_button = QPushButton('Salvar diagnóstico…')
    owner.export_button.clicked.connect(owner.export)
    actions.addWidget(owner.export_button)
    actions.addStretch()
    close = QPushButton('Fechar')
    close.clicked.connect(owner.reject)
    actions.addWidget(close)
    owner.apply_button = QPushButton('Usar configuração confirmada')
    owner.apply_button.clicked.connect(owner.accept)
    actions.addWidget(owner.apply_button)
    root.addLayout(actions)
