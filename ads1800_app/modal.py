"""Roving-hammer acquisition and ensemble H1 accelerance (SI units)."""
from dataclasses import asdict, dataclass, field
from collections import deque
from pathlib import Path
import json
import math
import uuid

import numpy as np


@dataclass
class ModalConfig:
    sample_rate: float = 1000
    duration: float = 2
    pretrigger: float = .05
    threshold: float = 10
    polarity: str = 'Absoluto'
    force_window: str = 'Força'
    response_window: str = 'Exponencial'
    force_width: float = .03
    exponential_end: float = .01
    force_channel: int = 0
    response_channel: int = 1
    force_factor: float = 1
    response_factor: float = 1
    force_limits: tuple | None = None
    response_limits: tuple | None = None
    averages: int = 3
    outline: list = field(default_factory=lambda: [[0, 0], [1, 0], [1, .5], [0, .5]])
    points: list = field(default_factory=lambda: [['P1', .1, .25], ['P2', .5, .25], ['P3', .9, .25]])
    accelerometer: list = field(default_factory=lambda: [.5, .25])

    @property
    def n(self):
        return round(self.duration * self.sample_rate)

    @property
    def pre(self):
        return round(self.pretrigger * self.sample_rate)

    def validate(self):
        numbers = [self.sample_rate, self.duration, self.pretrigger, self.threshold,
                   self.force_width, self.exponential_end, self.force_factor, self.response_factor]
        if not all(math.isfinite(x) for x in numbers):
            raise ValueError('Parâmetros devem ser finitos.')
        if self.sample_rate <= 0 or not 16 <= self.n <= 2_000_000:
            raise ValueError('O registro deve ter entre 16 e 2 milhões de amostras.')
        if not 2 <= self.pre < self.n - 4 or self.threshold <= 0:
            raise ValueError('Use pré-trigger de pelo menos 2 amostras, menor que o registro, e trigger positivo.')
        if not 1 / self.sample_rate <= self.force_width < (self.n-self.pre) / self.sample_rate:
            raise ValueError('Duração da janela de força deve caber no pós-trigger.')
        if not 0 < self.exponential_end <= 1 or self.averages < 2:
            raise ValueError('Resíduo exponencial deve estar em (0, 1]; use pelo menos 2 médias.')
        if self.force_channel == self.response_channel or min(self.force_channel, self.response_channel) < 0:
            raise ValueError('Selecione canais distintos para força e aceleração.')
        if self.force_factor == 0 or self.response_factor == 0:
            raise ValueError('Fatores de conversão não podem ser zero.')
        if self.force_window not in ('Força', 'Retangular', 'Hann') or self.response_window not in ('Exponencial', 'Retangular', 'Hann'):
            raise ValueError('Janela desconhecida.')
        if self.polarity not in ('Absoluto', 'Positivo', 'Negativo'):
            raise ValueError('Polaridade desconhecida.')
        if len(self.outline) < 3 or not self.points or len(self.accelerometer) != 2:
            raise ValueError('Informe contorno com 3 vértices, pontos de impacto e acelerômetro XY.')
        ids = [str(p[0]).strip() for p in self.points]
        if any(not x for x in ids) or len(set(ids)) != len(ids):
            raise ValueError('Identificadores dos pontos devem ser preenchidos e únicos.')
        xy = [*self.outline, *[p[1:] for p in self.points], self.accelerometer]
        if any(len(p) != 2 or not all(math.isfinite(float(v)) for v in p) for p in xy):
            raise ValueError('Coordenadas XY devem ser finitas.')
        outline = np.asarray(self.outline, float)
        area = np.sum(outline[:, 0]*np.roll(outline[:, 1], -1)-outline[:, 1]*np.roll(outline[:, 0], -1))
        if abs(area) < 1e-12:
            raise ValueError('Contorno deve ter área diferente de zero, com vértices em ordem.')
        for limits in (self.force_limits, self.response_limits):
            if limits is not None and (len(limits) != 2 or not all(math.isfinite(v) for v in limits) or limits[0] >= limits[1]):
                raise ValueError('Limites de engenharia inválidos.')


class ImpactCapture:
    """One explicitly armed hit; continuity and pretrigger survive block boundaries."""
    def __init__(self, config):
        config.validate()
        self.config = config
        self.history = deque(maxlen=config.pre)
        self.pending = None
        self.armed = False
        self.point = None
        self.last_time = None
        self.below = False

    def arm(self, point):
        if point not in [p[0] for p in self.config.points]:
            raise ValueError('Ponto desconhecido.')
        self.point = point
        self.pending = None
        self.armed = True
        self.below = False

    def cancel(self):
        self.armed = False
        self.pending = None

    def feed(self, times, force, acceleration):
        if not (len(times) == len(force) == len(acceleration)):
            self.cancel()
            raise ValueError('Bloco com tamanhos de canais diferentes.')
        result = None
        c = self.config
        for t, f, a in zip(times, force, acceleration):
            if not all(np.isfinite([t, f, a])) or (self.last_time is not None and
                    not .5 / c.sample_rate < t-self.last_time < 1.5 / c.sample_rate):
                self.cancel()
                self.history.clear()
                self.last_time = None
                raise ValueError('Descontinuidade ou amostras inválidas: batida cancelada; rearme.')
            self.last_time = t
            row = (t, f, a)
            if self.pending is not None:
                self.pending.append(row)
                if len(self.pending) == c.n:
                    result = (self.point, np.asarray(self.pending))
                    self.cancel()
            elif self.armed and len(self.history) == c.pre:
                level = abs(f) if c.polarity == 'Absoluto' else f if c.polarity == 'Positivo' else -f
                if level < c.threshold * .5:
                    self.below = True
                if self.below and level >= c.threshold:
                    self.pending = list(self.history) + [row]
            self.history.append(row)
        return result


def windows(c):
    force = np.ones(c.n)
    response = np.ones(c.n)
    if c.force_window == 'Hann':
        force = np.hanning(c.n)
    elif c.force_window == 'Força':
        # Keep the pulse onset preceding the threshold, then taper the last 20%.
        end = min(c.n, c.pre + round(c.force_width*c.sample_rate))
        taper = max(1, round((end-c.pre)*.2))
        force[end:] = 0
        force[end-taper:end] = .5*(1+np.cos(np.linspace(0, np.pi, taper)))
    if c.response_window == 'Hann':
        response = np.hanning(c.n)
    elif c.response_window == 'Exponencial':
        response[c.pre:] = np.exp(np.linspace(0, np.log(c.exponential_end), c.n-c.pre))
    return force, response


def analyze_hit(c, data):
    if data.shape != (c.n, 3) or not np.isfinite(data).all():
        raise ValueError('Registro incompleto ou inválido.')
    # Use early pretrigger only so the rising pulse does not bias the baseline.
    baseline = max(1, c.pre//2)
    f = data[:, 1] - np.mean(data[:baseline, 1])
    a = data[:, 2] - np.mean(data[:baseline, 2])
    wf, wa = windows(c)
    F, A = np.fft.rfft(f*wf), np.fft.rfft(a*wa)
    issues = []
    peak = float(np.max(abs(f)))
    # Count separate contact regions, not local maxima inside one contact pulse.
    contacts = abs(f[c.pre:]) > max(c.threshold, .2*peak)
    starts = np.flatnonzero(contacts & ~np.r_[False, contacts[:-1]])
    if len(starts) > 1:
        issues.append('Possível impacto duplo')
    noise = float(np.std(f[:baseline]))
    snr = float(20*np.log10(max(peak, 1e-30)/max(noise, 1e-15)))
    if snr < 20:
        issues.append('Força com baixo sinal/ruído (<20 dB)')
    for label, signal, limits in [('Força', data[:, 1], c.force_limits), ('Aceleração', data[:, 2], c.response_limits)]:
        if limits is not None:
            low, high = limits
            margin = .005*(high-low)
            if np.any(signal <= low+margin) or np.any(signal >= high-margin):
                issues.append(f'{label}: próximo ao limite / possível saturação')
    tail = np.sqrt(np.mean(a[-max(2, c.n//10):]**2))
    rms = np.sqrt(np.mean(a[c.pre:]**2))
    decay = float(tail/max(rms, 1e-30))
    if decay > .2:
        issues.append('Resposta não decaiu (RMS final >20% do RMS pós-trigger)')
    if c.force_window == 'Força':
        end = c.pre + round(c.force_width*c.sample_rate)
        if np.max(abs(f[max(c.pre, end-2):])) > .05*max(peak, 1e-30):
            issues.append('Força fora da janela (>5% do pico)')
    return {'F': F, 'A': A, 'force': f*wf, 'acceleration': a*wa,
            'peak_N': peak, 'snr_dB': snr, 'tail_ratio': decay, 'issues': issues}


def ensemble(c, hits):
    freq = np.fft.rfftfreq(c.n, 1/c.sample_rate)
    if not hits:
        return freq, np.full(len(freq), np.nan, complex), np.full(len(freq), np.nan)
    F = np.asarray([h['F'] for h in hits])
    A = np.asarray([h['A'] for h in hits])
    ff = np.mean(abs(F)**2, axis=0)
    aa = np.mean(abs(A)**2, axis=0)
    af = np.mean(A*np.conj(F), axis=0)
    valid = (ff > max(float(ff.max())*1e-10, 1e-30)) & (aa > 1e-30)
    h1 = np.full(len(freq), np.nan, complex)
    h1[valid] = af[valid]/ff[valid]
    coherence = np.full(len(freq), np.nan)
    if len(hits) >= 2:
        coherence[valid] = np.clip(abs(af[valid])**2/(ff[valid]*aa[valid]), 0, 1)
    return freq, h1, coherence


class ModalSession:
    """Immutable configuration per run; every capture persisted before review."""
    def __init__(self, directory, config, acquisition_metadata=None):
        config.validate()
        self.config = ModalConfig(**json.loads(json.dumps(asdict(config))))
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.records = []
        self.metadata = acquisition_metadata or {}
        self.save_manifest()

    @classmethod
    def load(cls, directory):
        directory = Path(directory).resolve()
        payload = json.loads((directory/'session.json').read_text(encoding='utf-8'))
        if payload.get('schema') != 1:
            raise ValueError('Versão de ensaio não suportada.')
        config = ModalConfig(**payload['config'])
        config.validate()
        records = payload['records']
        for record in records:
            path = (directory/record['file']).resolve()
            if path.parent != directory or path.suffix != '.npz':
                raise ValueError('Caminho de captura inválido.')
            if record['point'] not in [p[0] for p in config.points] or record['status'] not in ('pendente', 'aceita', 'rejeitada'):
                raise ValueError('Registro de captura inválido.')
            with np.load(path, allow_pickle=False) as data:
                for name in ('time', 'force_N', 'acceleration_m_s2', 'F', 'A'):
                    expected = config.n//2+1 if name in ('F', 'A') else config.n
                    if data[name].shape != (expected,) or not np.isfinite(data[name]).all():
                        raise ValueError('Arquivo de captura incompleto ou inválido.')
        session = cls.__new__(cls)
        session.directory, session.config = directory, config
        session.records, session.metadata = records, payload.get('acquisition', {})
        return session

    def save_manifest(self):
        payload = {'schema': 1, 'strategy': 'roving hammer', 'axis': '+Z (normal ao plano XY)',
                   'config': asdict(self.config), 'acquisition': self.metadata, 'records': self.records}
        temporary = self.directory/'session.tmp'
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        temporary.replace(self.directory/'session.json')

    def capture(self, point, data):
        analysis = analyze_hit(self.config, data)
        filename = f'impacto_{uuid.uuid4().hex}.npz'
        np.savez_compressed(self.directory/filename, time=data[:, 0], force_N=data[:, 1],
                            acceleration_m_s2=data[:, 2], F=analysis['F'], A=analysis['A'])
        record = {'point': point, 'file': filename, 'status': 'pendente',
                  **{key: analysis[key] for key in ('peak_N', 'snr_dB', 'tail_ratio', 'issues')}}
        self.records.append(record)
        self.save_manifest()
        return record, analysis

    def hits(self, point):
        hits = []
        for record in self.records:
            if record['point'] == point and record['status'] == 'aceita':
                with np.load(self.directory/record['file']) as data:
                    hits.append({'F': data['F'], 'A': data['A']})
        return hits

    def review(self, record, accept):
        record['status'] = 'aceita' if accept else 'rejeitada'
        self.save_manifest()
        freq, h1, coherence = ensemble(self.config, self.hits(record['point']))
        # Filenames use numeric indices, never user-supplied point names.
        index = [p[0] for p in self.config.points].index(record['point']) + 1
        np.savetxt(self.directory/f'frf_ponto_{index}.csv',
                   np.column_stack([freq, h1.real, h1.imag, abs(h1), np.angle(h1, deg=True), coherence]),
                   delimiter=';', header='Hz;H1_real_m_s2_N;H1_imag_m_s2_N;H1_modulo_m_s2_N;fase_graus;coerencia', comments='')
