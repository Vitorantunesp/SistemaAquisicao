"""Reusable operator-defined sensor profiles, independent from channel wiring."""
from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
import uuid


@dataclass
class SensorProfile:
    name: str = ''
    sensor_type: str = 'Acelerometro'
    manufacturer: str = ''
    model: str = ''
    serial_number: str = ''
    input_type: str = ''
    input_scale: str = ''
    input_min: float | None = None
    input_max: float | None = None
    input_unit: str = 'V'
    sensitivity: str = ''
    sensitivity_unit: str = 'mV/g'
    unit: str = 'g'
    gain: float = 1.0
    offset: float = 0.0
    notes: str = ''
    parameters: dict[str, str] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def validate(self):
        if self.input_min is not None or self.input_max is not None:
            if (self.input_min is None or self.input_max is None
                    or not math.isfinite(self.input_min) or not math.isfinite(self.input_max)
                    or self.input_min >= self.input_max or not self.input_unit.strip()):
                raise ValueError('Informe mínimo elétrico menor que máximo e a unidade da entrada.')
        if not self.name.strip():
            raise ValueError('Informe o nome do sensor.')
        if not self.id or not isinstance(self.id, str):
            raise ValueError('Identificador do sensor inválido.')
        if not self.unit.strip():
            raise ValueError('Informe a unidade de saída.')
        if not math.isfinite(self.gain) or not math.isfinite(self.offset):
            raise ValueError('Ganho e offset devem ser números finitos.')
        if self.sensitivity.strip():
            sensitivity = float(self.sensitivity.replace(',', '.'))
            if not math.isfinite(sensitivity) or sensitivity <= 0:
                raise ValueError('A sensibilidade deve ser positiva.')
        if not isinstance(self.parameters, dict) or any(not isinstance(k, str) or not k.strip() or not isinstance(v, str) for k, v in self.parameters.items()):
            raise ValueError('Parâmetros adicionais devem conter nomes e valores de texto.')

    def snapshot(self):
        self.validate()
        return asdict(self)


def load_catalog(path):
    path = Path(path)
    document = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(document, dict) or document.get('version') != 1 or not isinstance(document.get('sensors'), list):
        raise ValueError('Lista de sensores inválida. Use um catálogo JSON exportado pelo programa.')
    profiles = [SensorProfile(**item) for item in document['sensors']]
    ids = set()
    for profile in profiles:
        profile.validate()
        if profile.id in ids:
            raise ValueError('A lista contém identificadores de sensores duplicados.')
        ids.add(profile.id)
    return profiles


def save_catalog(path, profiles):
    # Validate the complete document before replacing an existing catalog.
    data = {'version': 1, 'sensors': [profile.snapshot() for profile in profiles]}
    if len({p.id for p in profiles}) != len(profiles):
        raise ValueError('Identificadores de sensores duplicados.')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)
