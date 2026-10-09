"""Read-only import of ADS CSV recordings. Point/series assignment is explicit."""
from dataclasses import dataclass, replace
from pathlib import Path
import csv
import re

import numpy as np

from ads1800_app.modal import ModalSession


@dataclass
class Recording:
    path: Path
    samples: np.ndarray  # time, force N, acceleration m/s²
    sample_rate: float
    units: list
    factors: list


def read_recording(path):
    path = Path(path)
    try:
        text = path.read_text(encoding='utf-8-sig')
    except UnicodeDecodeError:
        text = path.read_text(encoding='cp1252')
    rows = list(csv.reader(text.splitlines(), delimiter=';'))
    units = None
    start = None
    header_rate = None
    for i, row in enumerate(rows[:100]):
        if not row:
            continue
        if row[0] == 'Unit' and len(row) >= 3:
            units = row[1:3]
        if row[0] == 'Frequencia_Hz':
            header_rate = float(row[1].replace(',', '.'))
        if 'SampFreq:' in row:
            value = row[row.index('SampFreq:')+1]
            header_rate = float(value.lower().replace('hz', '').replace(',', '.'))
        if row[0].strip() in ('Time (s)', 'tempo_s'):
            start = i+1
            if len(row) >= 3 and row[0].strip() == 'tempo_s':
                found = [re.search(r'\[([^]]+)\]', column) for column in row[1:3]]
                if all(found):
                    units = [match.group(1) for match in found]
            break
    if start is None or units is None:
        raise ValueError('CSV deve conter cabeçalho ADS com tempo, força e aceleração, incluindo unidades.')
    force_units = {'n': 1, 'lbf': 4.4482216152605}
    acceleration_units = {'g': 9.80665, 'm/s²': 1, 'm/s2': 1, 'm/s^2': 1}
    try:
        factors = [force_units[units[0].strip().lower()], acceleration_units[units[1].strip().lower()]]
    except KeyError as exc:
        raise ValueError(f'Unidades não reconhecidas ou canais fora da ordem força/aceleração: {units}.') from exc
    values = []
    for line, row in enumerate(rows[start:], start+1):
        if not row or not any(v.strip() for v in row):
            continue
        if len(row) != 3:
            raise ValueError(f'Linha {line}: este importador requer exatamente tempo, martelo e acelerômetro.')
        try:
            values.append([float(v.replace(',', '.')) for v in row])
        except ValueError as exc:
            raise ValueError(f'Linha {line}: amostra inválida.') from exc
    data = np.asarray(values, float)
    if data.ndim != 2 or len(data) < 16 or not np.isfinite(data).all():
        raise ValueError('CSV sem amostras suficientes ou com valores inválidos.')
    dt = np.diff(data[:, 0])
    measured_rate = 1/float(np.median(dt))
    sample_rate = header_rate or measured_rate
    if np.any(dt <= 0) or not np.allclose(dt, 1/sample_rate, rtol=.005, atol=1e-8):
        raise ValueError('Registro descontínuo, com timestamps repetidos ou taxa incompatível com o cabeçalho.')
    data[:, 1:] *= factors
    return Recording(path, data, sample_rate, units, factors)


def candidate_impacts(recording, config, start_time, end_time):
    """Propose complete records within a user-selected, single-point time interval.

    A second pulse inside the response is retained for review by analyze_hit;
    no impact is accepted automatically and no groups-of-ten are inferred.
    """
    config.validate()
    if abs(recording.sample_rate-config.sample_rate) > config.sample_rate*1e-6:
        raise ValueError('Taxa do arquivo difere da configuração; não há reamostragem implícita.')
    if not np.isfinite([start_time, end_time]).all() or start_time >= end_time:
        raise ValueError('Intervalo de importação inválido.')
    data = recording.samples
    selected = data[(data[:, 0] >= start_time) & (data[:, 0] <= end_time)]
    if len(selected) < config.n:
        raise ValueError('O trecho é menor que a duração de uma captura.')
    f = selected[:, 1]
    level = abs(f) if config.polarity == 'Absoluto' else f if config.polarity == 'Positivo' else -f
    crosses = np.flatnonzero((level >= config.threshold) & ~np.r_[True, level[:-1] >= config.threshold])
    captures = []
    end_last = -1
    for index in crosses:
        first, last = index-config.pre, index-config.pre+config.n
        if first < 0 or last > len(selected) or index < end_last:
            continue
        captures.append(selected[first:last].copy())
        end_last = last
    return captures


def import_interval(recording, config, directory, point, start_time, end_time):
    if point not in [p[0] for p in config.points]:
        raise ValueError('Associe explicitamente o trecho a um ponto da geometria.')
    captures = candidate_impacts(recording, config, start_time, end_time)
    if not captures:
        raise ValueError('Nenhuma batida completa acima do trigger nesse trecho.')
    config = replace(config, sample_rate=recording.sample_rate, force_factor=1, response_factor=1,
                     force_limits=None, response_limits=None)
    metadata = {'mode': 'CSV importado; revisar batidas individualmente', 'source': str(recording.path),
                'interval_s': [start_time, end_time], 'point_assignment': 'Informada pelo usuário para este trecho',
                'source_units': recording.units, 'conversion_to_SI': recording.factors,
                'quality_note': 'Limites elétricos não importados; verificar saturação no arquivo original.'}
    session = ModalSession(directory, config, metadata)
    for data in captures:
        session.capture(point, data)
    return session
