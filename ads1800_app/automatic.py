"""Sample-accurate joint event capture and bounded complex Morlet analysis."""
from collections import deque
from dataclasses import dataclass
import json
import math
from pathlib import Path
import queue
import threading
import numpy as np
from scipy.signal import resample_poly


def channel_threshold(channel, config):
    explicit = config.trigger_thresholds.get(str(channel.number))
    if explicit is not None:
        threshold = float(explicit)
    elif channel.engineering_max is not None:
        threshold = config.trigger_percent * abs(channel.engineering_max) / 100
    else:
        raise ValueError(f'CH {channel.number + 1}: limite superior indisponível; informe o limiar do trigger.')
    if not math.isfinite(threshold) or threshold <= 0:
        raise ValueError(f'CH {channel.number + 1}: o limiar deve ser positivo e finito.')
    return threshold


def validate_automatic(config):
    fs = config.sample_rate
    numbers = (config.pre_trigger, config.capture_duration, config.wavelet_min,
               config.wavelet_max, config.trigger_percent)
    if not all(math.isfinite(v) for v in numbers):
        raise ValueError('Configuração automática: use valores finitos.')
    if not 0 <= config.pre_trigger < config.capture_duration <= 120:
        raise ValueError('Use 0 ≤ pré-trigger < duração total ≤ 120 s.')
    if round(config.capture_duration * fs) < 8 or round(config.pre_trigger * fs) >= round(config.capture_duration * fs):
        raise ValueError('A captura precisa de pelo menos 8 amostras e uma amostra após o pré-trigger.')
    if not 0 < config.wavelet_min < config.wavelet_max < fs / 2:
        raise ValueError('Escalogramas: use 0 < frequência mínima < máxima < fs/2.')
    if not 0 < config.trigger_percent <= 100:
        raise ValueError('O percentual do trigger deve estar entre 0 e 100%.')
    if not isinstance(config.trigger_thresholds, dict):
        raise ValueError('Limiares por canal inválidos.')
    for channel in config.enabled_channels:
        channel_threshold(channel, config)
    if config.capture_duration * fs * len(config.enabled_channels) * 8 > 64 * 1024 ** 2:
        raise ValueError('Captura acima de 64 MB: reduza a duração ou a frequência de aquisição.')
    analysis_fs = fs / max(1, int(fs / (4 * config.wavelet_max)))
    if math.ceil(round(config.capture_duration * fs) / max(1, int(fs / (4 * config.wavelet_max)))) < 8:
        raise ValueError('Aumente a duração: a faixa de frequências escolhida precisa de pelo menos 8 amostras na análise.')
    if 16 * analysis_fs / config.wavelet_min > 2_000_000:
        raise ValueError('Frequência mínima muito baixa para esta taxa. Aumente a frequência mínima do escalograma.')


@dataclass
class Capture:
    number: int
    trigger_time: float
    trigger_channels: list[int]
    pre_samples: int
    sample_rate: float
    values: np.ndarray

    @property
    def times(self):
        return (np.arange(self.values.shape[1]) - self.pre_samples) / self.sample_rate


class TriggerRecorder:
    """Any rising absolute threshold crossing starts all channels synchronously.

    Needs a full prehistory. Events cannot overlap. A sustained high level must
    first fall below threshold before another rising crossing is accepted.
    """
    def __init__(self, config):
        validate_automatic(config)
        self.config = config
        self.thresholds = np.array([channel_threshold(c, config) for c in config.enabled_channels])
        self.pre = round(config.pre_trigger * config.sample_rate)
        self.total = round(config.capture_duration * config.sample_rate)
        self.number = 0
        self.discarded = 0
        self.reset()

    def reset(self):
        self.history = deque()
        self.history_count = 0
        self.parts = None
        self.remaining = 0
        self.last_time = None
        self.previous_above = np.zeros(len(self.thresholds), dtype=bool)
        self.state = 'Preenchendo pré-trigger' if self.pre else 'Aguardando trigger'

    def _remember(self, values):
        if not self.pre or not values.shape[1]:
            return
        self.history.append(values[:, -self.pre:].copy())
        self.history_count += min(self.pre, values.shape[1])
        while self.history_count > self.pre:
            excess = self.history_count - self.pre
            first = self.history.popleft()
            removed = min(excess, first.shape[1])
            if removed < first.shape[1]:
                self.history.appendleft(first[:, removed:].copy())
            self.history_count -= removed

    def feed(self, times, values, allow_trigger=True):
        t, x = np.asarray(times, dtype=float), np.asarray(values, dtype=float)
        if not len(t):
            return []
        if x.shape != (len(self.thresholds), len(t)):
            raise ValueError('Bloco de aquisição desalinhado para o trigger.')
        valid = np.isfinite(t) & np.all(np.isfinite(x), axis=0)
        dt = 1 / self.config.sample_rate
        breaks = np.flatnonzero((np.abs(np.diff(t) - dt) > dt * .5) | ~valid[1:] | ~valid[:-1]) + 1
        events = []
        for indices in np.split(np.arange(len(t)), breaks):
            a, b = int(indices[0]), int(indices[-1]) + 1
            if not valid[a] or (self.last_time is not None and abs(t[a] - self.last_time - dt) > dt * .5):
                if self.parts is not None:
                    self.discarded += 1
                self.reset()
            if not valid[a]:
                continue
            above = np.abs(x[:, a:b]) >= self.thresholds[:, None]
            rising = above & ~np.column_stack((self.previous_above, above[:, :-1]))
            crossings = np.flatnonzero(np.any(rising, axis=0)) + a
            pos = a
            while pos < b:
                if self.parts is not None:
                    end = min(b, pos + self.remaining)
                    self.parts.append(x[:, pos:end].copy())
                    self.remaining -= end - pos
                    self._remember(x[:, pos:end])
                    pos = end
                    if self.remaining == 0:
                        self.number += 1
                        events.append(Capture(self.number, self.trigger_time, self.trigger_channels,
                                              self.pre, self.config.sample_rate, np.concatenate(self.parts, axis=1)))
                        self.parts = None
                        # At most one analysis at a time, but retain prehistory while busy.
                        allow_trigger = False
                    continue
                earliest = pos + max(0, self.pre - self.history_count)
                candidates = crossings[crossings >= earliest] if allow_trigger else []
                if len(candidates):
                    hit = int(candidates[0])
                    self._remember(x[:, pos:hit])
                    self.parts = list(self.history)
                    self.remaining = self.total - self.pre
                    self.trigger_time = float(t[hit])
                    self.trigger_channels = [c.number for c, crossed in
                                             zip(self.config.enabled_channels, rising[:, hit - a]) if crossed]
                    pos = hit
                else:
                    self._remember(x[:, pos:b])
                    pos = b
            self.last_time = float(t[b - 1])
            self.previous_above = above[:, -1].copy()
        self.state = ('Capturando sinal' if self.parts is not None else
                      'Preenchendo pré-trigger' if self.history_count < self.pre else 'Aguardando trigger')
        return events


def morlet_scalograms(capture, config, cancelled=None):
    import pywt
    fs = capture.sample_rate
    factor = max(1, int(fs / (4 * config.wavelet_max)))
    analysis_fs = fs / factor
    frequencies = np.linspace(config.wavelet_min, config.wavelet_max, 96)
    wavelet = 'cmor1.5-1.0'
    scales = pywt.frequency2scale(wavelet, frequencies / analysis_fs)
    powers = []
    plot_times = None
    for signal in capture.values:
        if cancelled and cancelled.is_set():
            return None
        reduced = resample_poly(signal, 1, factor) if factor > 1 else signal
        reduced = reduced - reduced.mean()
        edges = np.linspace(0, len(reduced), min(len(reduced), 1200) + 1).astype(int)
        power = np.empty((len(scales), len(edges) - 1), dtype=np.float32)
        # One frequency at a time bounds peak memory for 24 kHz captures.
        for i, scale in enumerate(scales):
            if cancelled and cancelled.is_set():
                return None
            coef, _ = pywt.cwt(reduced, [scale], wavelet, sampling_period=1 / analysis_fs, method='fft')
            # Keep brief energy peaks when reducing the heatmap to screen columns.
            power[i] = np.maximum.reduceat(np.abs(coef[0]) ** 2, edges[:-1])
        powers.append(power)
        plot_times = np.linspace(-capture.pre_samples / fs,
                                 (capture.values.shape[1] - 1 - capture.pre_samples) / fs,
                                 len(edges) - 1)
    return {'frequencies': frequencies, 'times': plot_times,
            'power': np.asarray(powers), 'analysis_rate': analysis_fs, 'wavelet': wavelet}


class CaptureAnalysis:
    """One bounded background job; result publication never touches Qt widgets."""
    def __init__(self, config, directory):
        self.config, self.directory = config, Path(directory)
        self.cancelled = threading.Event()
        self.busy = threading.Event()
        self.results = queue.Queue(maxsize=1)

    def submit(self, capture):
        if self.busy.is_set() or self.cancelled.is_set():
            return False
        self.busy.set()
        threading.Thread(target=self._run, args=(capture,), daemon=True).start()
        return True

    def _run(self, capture):
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self.directory / f'evento_{capture.number:04d}.npz'
            metadata = {'trigger_time': capture.trigger_time, 'trigger_channels': capture.trigger_channels,
                        'sample_rate': capture.sample_rate, 'pre_samples': capture.pre_samples,
                        'thresholds': [channel_threshold(c, self.config) for c in self.config.enabled_channels],
                        'channels': [{'number': c.number, 'name': c.label(), 'unit': c.unit,
                                      'engineering_min': c.engineering_min, 'engineering_max': c.engineering_max}
                                     for c in self.config.enabled_channels]}
            # Save the original engineering samples before starting costly analysis.
            np.savez(path, times=capture.times, values=capture.values,
                     metadata=json.dumps(metadata, ensure_ascii=False))
            self.config.save(self.directory / 'configuracao.json')
            result = morlet_scalograms(capture, self.config, self.cancelled)
            if result is not None and not self.cancelled.is_set():
                np.savez(path.with_name(path.stem + '_morlet.npz'), **result)
                self.results.put(('ready', capture, result, path))
        except Exception as exc:
            if not self.cancelled.is_set():
                self.results.put(('error', str(exc)))
        # Busy is cleared by the UI only after consuming the bounded result.

    def close(self):
        self.cancelled.set()
