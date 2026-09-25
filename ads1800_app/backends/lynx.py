from __future__ import annotations

from pathlib import Path
import sys

from ads1800_app.backends.base import DeviceInfo
from ads1800_app.config import ChannelConfig


class LynxBackend:
    """Adaptador para o driver Python/LDTP fornecido pela LYNX."""

    def __init__(self) -> None:
        self._driver = None
        self._ip = ""
        self._channels: list[ChannelConfig] = []
        self._available_sample_rates: list[float] = []

    @property
    def connected(self) -> bool:
        return self._driver is not None

    @staticmethod
    def _load_driver():
        project_root = Path(__file__).resolve().parents[2]
        vendor_dir = project_root / "vendor" / "lynx_driver"
        if not vendor_dir.exists():
            raise RuntimeError(f"Driver LYNX nao encontrado em {vendor_dir}")
        if str(vendor_dir) not in sys.path:
            sys.path.insert(0, str(vendor_dir))
        try:
            import LDTP_Const  # type: ignore
            import LynxDriver  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "Nao foi possivel carregar o driver LYNX. Instale o pacote numpy."
            ) from exc
        return LynxDriver, LDTP_Const

    def connect(self, ip: str) -> DeviceInfo:
        LynxDriver, _ = self._load_driver()
        driver = LynxDriver.LynxDriverV1()
        if not driver.ConnectTo(ip):
            raise ConnectionError(
                f"O ADS 1800 nao respondeu em {ip}. Verifique cabo, IP, rota e firewall."
            )
        self._driver = driver
        self._ip = ip
        rates = [float(value) for value in driver.GetAvailableSampFreq()]
        self._available_sample_rates = sorted(set(rates))
        analog_channels = [item for item in driver.ChInfo[0] if not item.IsDig][:8]
        tag = getattr(driver.Module.GetDevInfo(0), "Tag", "")
        return DeviceInfo(
            f"ADS 1800 {tag}".strip(), ip, len(analog_channels) or 8, rates
        )

    def disconnect(self) -> None:
        if self._driver is not None:
            try:
                self._driver.DisconnectFrom(self._ip)
            finally:
                self._driver = None
                self._ip = ""
                self._available_sample_rates = []

    def start(
        self,
        sample_rate: float,
        channels: list[ChannelConfig],
        use_device_timestamp: bool = False,
    ) -> None:
        if self._driver is None:
            raise RuntimeError("ADS 1800 nao conectado.")
        if self._available_sample_rates and sample_rate not in self._available_sample_rates:
            raise ValueError(
                f"Frequencia {sample_rate:g} Hz nao informada pelo equipamento. "
                f"Selecione uma das taxas disponiveis (maxima: {max(self._available_sample_rates):g} Hz)."
            )
        _, constants = self._load_driver()
        lynx_channels = [
            [self._ip, constants.LDTP_CHTYPE_ANIN, channel.number]
            for channel in channels
        ]
        if not self._driver.StartAcq(
            sample_rate, lynx_channels, useDeviceTimestamp=use_device_timestamp
        ):
            raise RuntimeError(
                "O ADS 1800 recusou a aquisicao. Confirme a frequencia e os canais."
            )
        self._channels = list(channels)

    def read(self) -> tuple[list[float], list[list[float]]]:
        if self._driver is None:
            return [], []
        samples = self._driver.GetAllSamples()
        if not samples:
            return [], []
        timestamps = [float(value) for value in samples[0]]
        calibrated = []
        for channel, raw_values in zip(self._channels, samples[1:]):
            calibrated.append(
                [channel.apply_calibration(float(value)) for value in raw_values]
            )
        return timestamps, calibrated

    def stop(self) -> None:
        if self._driver is not None:
            if self._driver.StopAcq() is False:
                raise RuntimeError("O ADS 1800 nao confirmou o encerramento da aquisicao.")

    def samples_lost(self) -> int:
        if self._driver is None or not self._channels:
            return 0
        return int(self._driver.GetSamplesLost(0))
