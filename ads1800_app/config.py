from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path

# ADS1800 manual rev. 13, pp. 16-17. Connected hardware takes precedence.
ADS1800_SAMPLE_RATES = (1, 5, 25, 50, 100, 200, 250, 400, 500, 800,
                       1000, 2000, 4000, 8000, 12000, 24000)

SENSOR_TYPES = (
    "Generico",
    "Celula de carga",
    "Extensometro",
    "Acelerometro",
    "Martelo de impacto",
    "Termopar",
    "Pressao",
    "Deslocamento",
    "Tensao",
)


@dataclass(slots=True)
class ChannelConfig:
    number: int
    enabled: bool = False
    sensor_type: str = "Generico"
    name: str = ""
    unit: str = "V"
    gain: float = 1.0
    offset: float = 0.0
    notes: str = ""
    sensor_profile: dict = field(default_factory=dict)
    input_type: str = ''
    input_scale: str = ''
    display_min: float = -1.0
    display_max: float = 1.0
    display_auto: bool = True
    input_min: float | None = None
    input_max: float | None = None
    input_unit: str = 'V'
    engineering_min: float | None = None
    engineering_max: float | None = None

    def label(self) -> str:
        return self.name.strip() or f"Canal {self.number + 1}"

    def apply_calibration(self, value: float) -> float:
        return value * self.gain + self.offset


@dataclass(slots=True)
class ExperimentConfig:
    name: str = "Experimento"
    operator: str = ""
    description: str = ""
    device_ip: str = "192.168.1.180"
    sample_rate: float = 1000.0
    use_device_timestamp: bool = False
    channels: list[ChannelConfig] = field(
        default_factory=lambda: [
            ChannelConfig(i, enabled=(i == 0), name=f"Canal {i + 1}")
            for i in range(8)
        ]
    )

    @property
    def enabled_channels(self) -> list[ChannelConfig]:
        return [channel for channel in self.channels if channel.enabled]

    def validate(self) -> None:
        if not self.enabled_channels:
            raise ValueError("Selecione pelo menos um canal.")
        if not math.isfinite(self.sample_rate) or self.sample_rate <= 0:
            raise ValueError("A frequencia deve ser maior que zero.")
        if not self.device_ip.strip():
            raise ValueError("Informe o endereco IP do ADS 1800.")
        for channel in self.channels:
            if channel.input_min is not None or channel.input_max is not None:
                if (channel.input_min is None or channel.input_max is None
                        or not math.isfinite(channel.input_min) or not math.isfinite(channel.input_max)
                        or channel.input_min >= channel.input_max or not channel.input_unit.strip()):
                    raise ValueError(f"Canal {channel.number + 1}: faixa elétrica inválida; informe mínimo, máximo e unidade.")
            if (not math.isfinite(channel.display_min) or not math.isfinite(channel.display_max)
                    or channel.display_min >= channel.display_max):
                raise ValueError(f"Canal {channel.number + 1}: mínimo deve ser menor que máximo, com valores finitos.")

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: str | Path) -> "ExperimentConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        data["channels"] = [ChannelConfig(**item) for item in data["channels"]]
        return cls(**data)
