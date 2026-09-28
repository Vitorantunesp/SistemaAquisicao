from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ads1800_app.config import ChannelConfig


@dataclass(slots=True)
class DeviceInfo:
    name: str
    ip: str
    channel_count: int
    available_sample_rates: list[float]
    channels: list[ChannelConfig] = field(default_factory=list)


class AcquisitionBackend(Protocol):
    @property
    def connected(self) -> bool: ...

    def connect(self, ip: str) -> DeviceInfo: ...

    def disconnect(self) -> None: ...

    def start(
        self,
        sample_rate: float,
        channels: list[ChannelConfig],
        use_device_timestamp: bool = False,
    ) -> None: ...

    def read(self) -> tuple[list[float], list[list[float]]]: ...

    def stop(self) -> None: ...

    def samples_lost(self) -> int: ...
