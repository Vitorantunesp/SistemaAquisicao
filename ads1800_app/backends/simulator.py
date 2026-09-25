from __future__ import annotations

import math
import random
import time

from ads1800_app.backends.base import DeviceInfo
from ads1800_app.config import ADS1800_SAMPLE_RATES, ChannelConfig


class SimulatorBackend:
    def __init__(self) -> None:
        self._connected = False
        self._running = False
        self._sample_rate = 1000.0
        self._channels: list[ChannelConfig] = []
        self._sample_index = 0
        self._last_read = 0.0

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self, ip: str) -> DeviceInfo:
        self._connected = True
        return DeviceInfo(
            "ADS 1800 (simulador)", ip, 8,
            list(ADS1800_SAMPLE_RATES),
        )

    def disconnect(self) -> None:
        self.stop()
        self._connected = False

    def start(
        self,
        sample_rate: float,
        channels: list[ChannelConfig],
        use_device_timestamp: bool = False,
    ) -> None:
        if not self._connected:
            raise RuntimeError("Simulador nao conectado.")
        if sample_rate not in ADS1800_SAMPLE_RATES:
            raise ValueError("Selecione uma frequencia da lista do ADS 1800 (ate 24000 Hz).")
        self._sample_rate = sample_rate
        self._channels = list(channels)
        self._sample_index = 0
        self._last_read = time.perf_counter()
        self._running = True

    def read(self) -> tuple[list[float], list[list[float]]]:
        if not self._running:
            return [], []
        now = time.perf_counter()
        count = min(5000, max(0, int((now - self._last_read) * self._sample_rate)))
        if count == 0:
            return [], []
        start = self._sample_index
        timestamps = [(start + i) / self._sample_rate for i in range(count)]
        values: list[list[float]] = []
        for channel in self._channels:
            frequency = 0.7 + channel.number * 0.35
            raw = [
                math.sin(2 * math.pi * frequency * t)
                + random.gauss(0.0, 0.015)
                for t in timestamps
            ]
            values.append([channel.apply_calibration(value) for value in raw])
        self._sample_index += count
        self._last_read += count / self._sample_rate
        return timestamps, values

    def stop(self) -> None:
        self._running = False

    def samples_lost(self) -> int:
        return 0
