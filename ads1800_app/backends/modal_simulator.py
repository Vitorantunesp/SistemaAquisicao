"""Continuous force pulses and causal two-mode acceleration for modal UI testing."""
import numpy as np
from scipy.signal import cont2discrete, lfilter
from ads1800_app.backends.simulator import SimulatorBackend
from ads1800_app.backends.base import DeviceInfo
from ads1800_app.config import ADS1800_SAMPLE_RATES, ChannelConfig


class ModalSimulatorBackend(SimulatorBackend):
    period = 4.0

    def connect(self, ip):
        self._connected = True
        return DeviceInfo('Simulador modal — modos 35 e 90 Hz', ip, 8, list(ADS1800_SAMPLE_RATES), [
            ChannelConfig(0, name='Martelo', unit='N', engineering_min=-500, engineering_max=500),
            *[ChannelConfig(i, name=f'Acelerômetro {i}', unit='m/s²', engineering_min=-100, engineering_max=100) for i in range(1, 8)]])

    def start(self, *args, **kwargs):
        super().start(*args, **kwargs)
        self.filters = []
        self.rng = np.random.default_rng(42)
        for frequency, mass in [(35, 20), (90, 40)]:
            w = 2*np.pi*frequency
            b, a, _ = cont2discrete(([1/mass, 0, 0], [1, 2*.025*w, w*w]), 1/self._sample_rate)
            self.filters.append([b.ravel(), a, np.zeros(2)])

    def read(self):
        times, _ = super().read()
        if not times:
            return [], []
        phase = (np.asarray(times)-1) % self.period
        force = np.where(phase < .008, 100*np.sin(np.pi*phase/.008), 0)
        acceleration = np.zeros(len(times))
        for f in self.filters:
            response, f[2] = lfilter(f[0], f[1], force, zi=f[2])
            acceleration += response
        values = [force+self.rng.normal(0, .02, len(times)),
                  acceleration+self.rng.normal(0, .0002, len(times))]
        values.extend(((-1)**i)*(1+i*.2)*acceleration+self.rng.normal(0, .0002, len(times)) for i in range(1, 7))
        return times, [values[c.number].tolist() for c in self._channels]
