"""Connection, geometry and impact settings are separate configuration pages."""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGridLayout, QComboBox, QLineEdit, QLabel, QTabWidget, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit, QCheckBox, QSpinBox)

from ads1800_app.config import ADS1800_SAMPLE_RATES, DEFAULT_DEVICE_IP
from ads1800_app.modal import ModalConfig
from ads1800_app.ui.modal_sensors import SensorTable


def _page(tabs, title):
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    content = QWidget()
    scroll.setWidget(content)
    tabs.addTab(scroll, title)
    return QVBoxLayout(content)


def build_settings(owner, geometry_class):
    page = QWidget()
    root = QVBoxLayout(page)
    owner.tabs.addTab(page, 'Configuração do ensaio')
    owner.config_tabs = QTabWidget()
    root.addWidget(owner.config_tabs)
    owner.fields = {}
    c = ModalConfig()

    connection = _page(owner.config_tabs, 'Conexão e canais')
    row = QHBoxLayout()
    owner.mode = QComboBox()
    owner.mode.addItems(['Simulador modal', 'ADS 1800 real'])
    owner.ip = QLineEdit(DEFAULT_DEVICE_IP)
    row.addWidget(owner.mode)
    row.addWidget(QLabel('IP do equipamento'))
    row.addWidget(owner.ip)
    owner.connect_button = owner.button('Conectar', owner.connect_device, row)
    owner.connection = QLabel('Desconectado')
    row.addWidget(owner.connection, 1)
    connection.addLayout(row)
    connection.addWidget(QLabel('Parâmetros lidos do equipamento'))
    owner.channel_info = QTableWidget(0, 7)
    owner.channel_info.setHorizontalHeaderLabels(['Canal', 'Nome', 'Unidade', 'Limite inferior',
                                                  'Limite superior', 'Tipo de entrada', 'Faixa elétrica'])
    owner.channel_info.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    owner.channel_info.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    owner.channel_info.setMinimumHeight(210)
    connection.addWidget(owner.channel_info, 1)
    owner.channel_settings = QWidget()
    channel_layout = QVBoxLayout(owner.channel_settings)
    form = QFormLayout()
    owner.force_channel, owner.response_channel = QComboBox(), QComboBox()
    owner.fields['force_factor'] = owner.number(1, -1e9, 1e9, 6)
    owner.fields['response_factor'] = owner.number(1, -1e9, 1e9, 6)
    form.addRow('Canal do martelo', owner.force_channel)
    form.addRow('Conversão do martelo para N', owner.fields['force_factor'])
    form.addRow('Canal do acelerômetro fixo (A1)', owner.response_channel)
    form.addRow('Conversão de A1 para m/s²', owner.fields['response_factor'])
    channel_layout.addLayout(form)
    channel_layout.addWidget(QLabel('Acelerômetros adicionais — atribuição de canais'))
    owner.extra_sensors = SensorTable(separate_positions=True)
    channel_layout.addWidget(owner.extra_sensors)
    connection.addWidget(owner.channel_settings)
    note = QLabel('Os nomes, unidades e limites acima vêm da aquisição. Parâmetros não fornecidos aparecem '
                  'como “Não informado”. Faixa elétrica, IEPE e condicionamento são ajustados no Assistente LYNX. '
                  'As conversões para N e m/s² são aplicadas uma única vez.')
    note.setWordWrap(True)
    connection.addWidget(note)

    geometry = _page(owner.config_tabs, 'Geometria')
    owner.geometry_settings = QWidget()
    grid = QGridLayout(owner.geometry_settings)
    form = QFormLayout()
    owner.outline, owner.points = QTextEdit(), QTextEdit()
    owner.outline.setPlainText('0; 0\n1; 0\n1; 0.5\n0; 0.5')
    owner.points.setPlainText('P1; 0.1; 0.25\nP2; 0.5; 0.25\nP3; 0.9; 0.25')
    owner.outline.setMinimumHeight(130)
    owner.points.setMinimumHeight(170)
    form.addRow('Contorno: x; y [m]', owner.outline)
    form.addRow('Pontos de impacto: nome; x; y [m]', owner.points)
    owner.ax, owner.ay = owner.number(.5, -1e6, 1e6, 6), owner.number(.25, -1e6, 1e6, 6)
    form.addRow('Acelerômetro fixo A1 — X [m]', owner.ax)
    form.addRow('Acelerômetro fixo A1 — Y [m]', owner.ay)
    grid.addLayout(form, 0, 0)
    right = QVBoxLayout()
    owner.preview = geometry_class()
    right.addWidget(owner.preview, 1)
    owner.button('Atualizar desenho', owner.preview_geometry, right)
    right.addWidget(QLabel('Localização dos acelerômetros adicionais'))
    right.addWidget(owner.extra_sensors.position_table)
    grid.addLayout(right, 0, 1)
    grid.setColumnStretch(0, 1)
    grid.setColumnStretch(1, 1)
    geometry.addWidget(owner.geometry_settings)
    geometry.addWidget(QLabel('Os canais são escolhidos em Conexão e canais. As posições são definidas aqui, no plano XY.'))

    parameters = _page(owner.config_tabs, 'Parâmetros das batidas')
    intro = QLabel('Defina os parâmetros manualmente ou use duas batidas no assistente para medir e conferir a configuração.')
    intro.setWordWrap(True)
    parameters.addWidget(intro)
    owner.settings = QWidget()
    form = QFormLayout(owner.settings)
    owner.rate = QComboBox()
    owner.rate.addItems([str(v) for v in ADS1800_SAMPLE_RATES])
    owner.rate.setCurrentText('2000')
    form.addRow('Taxa de amostragem [Hz]', owner.rate)
    for key, label, low, high in [
        ('duration', 'Duração total do bloco [s]', .01, 600),
        ('pretrigger', 'Pré-trigger [s]', .001, 60),
        ('threshold', 'Trigger de força [N]', 1e-8, 1e9),
        ('force_width', 'Janela de força após trigger [s]', .0001, 60),
        ('exponential_end', 'Resíduo da exponencial (1 = sem atenuação)', .0001, 1)]:
        owner.fields[key] = owner.number(getattr(c, key), low, high, 8 if key == 'threshold' else 6)
        form.addRow(label, owner.fields[key])
    owner.block_summary = QLabel()
    form.addRow('Bloco calculado', owner.block_summary)
    owner.rate.currentTextChanged.connect(owner.update_block_summary)
    owner.fields['duration'].valueChanged.connect(owner.update_block_summary)
    owner.update_block_summary()
    for key, title, options in [('polarity', 'Polaridade do trigger', ['Absoluto', 'Positivo', 'Negativo']),
                                ('force_window', 'Janela do martelo', ['Força', 'Retangular', 'Hann']),
                                ('response_window', 'Janela da resposta', ['Exponencial', 'Retangular', 'Hann'])]:
        box = QComboBox()
        box.addItems(options)
        owner.fields[key] = box
        form.addRow(title, box)
    owner.averages = QSpinBox()
    owner.averages.setRange(2, 10000)
    owner.averages.setValue(3)
    form.addRow('Meta de batidas aceitas por ponto', owner.averages)
    owner.temperature = QLineEdit()
    owner.temperature.setPlaceholderText('Não medida (opcional)')
    form.addRow('Temperatura ambiente [°C]', owner.temperature)
    owner.bandpass = QCheckBox('Aplicar filtro passa-banda aos sinais')
    owner.bandpass.setChecked(True)
    form.addRow(owner.bandpass)
    for key, title, default in [('low_cut', 'Corte inferior [Hz]', 1), ('high_cut', 'Corte superior [Hz]', 500)]:
        owner.fields[key] = owner.number(default, .0001, 1e6)
        owner.bandpass.toggled.connect(owner.fields[key].setEnabled)
        form.addRow(title, owner.fields[key])
    parameters.addWidget(owner.settings)
    row = QHBoxLayout()
    owner.setup_button = owner.button('Assistente por batidas…', owner.configure_by_impacts, row)
    owner.manual_button = owner.button('Usar configuração manual', owner.clear_setup, row)
    owner.button('Salvar configuração…', owner.save_config, row)
    owner.button('Carregar configuração…', owner.load_config, row)
    parameters.addLayout(row)
    owner.setup_status = QLabel('Configuração manual. O assistente propõe os parâmetros a partir de duas batidas.')
    owner.setup_status.setWordWrap(True)
    parameters.addWidget(owner.setup_status)
    parameters.addStretch()
    actions = QHBoxLayout()
    owner.open_button = owner.button('Abrir ensaio salvo…', owner.open_session, actions)
    owner.import_button = owner.button('Importar trecho CSV…', owner.import_csv, actions)
    actions.addStretch()
    owner.start_button = owner.button('Iniciar novo ensaio…', owner.start, actions)
    root.addLayout(actions)


def populate_channel_info(owner):
    owner.channel_info.setRowCount(len(owner.channels))
    for row, c in enumerate(owner.channels):
        electrical = (f'{c.input_min:g} a {c.input_max:g} {c.input_unit}'
                      if c.input_min is not None and c.input_max is not None else c.input_scale)
        values = [f'CH {c.number+1}', c.name, c.unit,
                  'Não informado' if c.engineering_min is None else f'{c.engineering_min:g}',
                  'Não informado' if c.engineering_max is None else f'{c.engineering_max:g}',
                  c.input_type or 'Não informado', electrical or 'Não informado']
        for col, text in enumerate(values):
            owner.channel_info.setItem(row, col, QTableWidgetItem(text))
