"""Signal processing for the bridge display; acquisition/CSV remain untouched."""
from dataclasses import dataclass, field
import math
import numpy as np
from scipy.signal import butter, sosfilt, welch
from ads1800_app.config import ExperimentConfig


@dataclass(slots=True)
class MonitorConfig(ExperimentConfig):
    bandpass_enabled: bool = False
    low_cut: float = 1.0
    high_cut: float = 100.0
    bridge_image: str = 'assets/ponte_sem_fundo.png'
    sensor_positions: dict = field(default_factory=dict)

    def validate(self):
        ExperimentConfig.validate(self)
        if not isinstance(self.bridge_image, str) or not isinstance(self.sensor_positions, dict):
            raise ValueError('Configuração da imagem da ponte inválida.')
        for key, xy in self.sensor_positions.items():
            if (not isinstance(key, str) or not key.isdecimal() or not isinstance(xy, (list, tuple))
                    or len(xy) != 2 or any(not isinstance(v, (int, float)) or not math.isfinite(v)
                                          or not 0 <= v <= 1 for v in xy)):
                raise ValueError('Posições dos sensores inválidas.')
        if self.bandpass_enabled:
            validate_bandpass(self.sample_rate, self.low_cut, self.high_cut)


def validate_bandpass(fs, low, high):
    if not all(math.isfinite(x) for x in (fs, low, high)) or not 0 < low < high < fs / 2:
        raise ValueError('Filtro: use 0 < corte mínimo < corte máximo < frequência de aquisição / 2 (Nyquist).')


class StreamingBandpass:
    """Causal Butterworth, order 4 prototype (8 poles), persistent SOS state."""
    def __init__(self, fs, low, high, channels):
        validate_bandpass(fs, low, high)
        self.sos = butter(4, [low, high], btype='bandpass', fs=fs, output='sos')
        self.channels = channels
        self.reset()

    def reset(self):
        self.state = np.zeros((len(self.sos), self.channels, 2))

    def apply(self, values):
        values = np.asarray(values, dtype=float)
        result = np.full_like(values, np.nan)
        # Nonfinite samples break the filter history instead of poisoning it forever.
        valid = np.all(np.isfinite(values), axis=0)
        edges = np.flatnonzero(np.diff(np.r_[False, valid, False]))
        for start, stop in zip(edges[::2], edges[1::2]):
            if start:
                self.reset()
            result[:, start:stop], self.state = sosfilt(
                self.sos, values[:, start:stop], axis=1, zi=self.state)
        if len(valid) and not valid[-1]:
            self.reset()
        return result


def spectra(values, fs):
    """One-sided peak amplitude FFT and Welch PSD; Hann window, DC removed."""
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or len(x) < 8 or not np.all(np.isfinite(x)):
        return (np.array([]),) * 4
    x = x - x.mean()
    n = len(x)
    window = np.hanning(n)
    amplitude = np.abs(np.fft.rfft(x * window)) / window.sum()
    amplitude[1:-1 if n % 2 == 0 else None] *= 2
    frequency = np.fft.rfftfreq(n, 1 / fs)
    psd_frequency, psd = welch(x, fs=fs, window='hann', nperseg=min(n, 4096),
                               detrend='constant', scaling='density')
    return frequency, amplitude, psd_frequency, psd
