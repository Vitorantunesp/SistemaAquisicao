from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
import queue
import threading
from typing import Callable

from ads1800_app.backends.base import AcquisitionBackend
from ads1800_app.config import ExperimentConfig


class AcquisitionController:
    def __init__(
        self,
        backend: AcquisitionBackend,
        on_data: Callable[[list[float], list[list[float]]], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        self.backend = backend
        self.on_data = on_data
        self.on_error = on_error
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._writer_thread: threading.Thread | None = None
        self._write_queue: queue.Queue[object] = queue.Queue(maxsize=200)
        self._recording = False
        self._record_lock = threading.Lock()
        self._csv_path: Path | None = None
        self._config: ExperimentConfig | None = None
        self.total_samples = 0

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def recording(self) -> bool:
        return self._recording

    def start(self, config: ExperimentConfig) -> None:
        config.validate()
        if self.running:
            raise RuntimeError("A aquisicao anterior ainda esta ativa ou encerrando.")
        self.stop_recording()
        self._config = config
        self.total_samples = 0
        self._stop_event.clear()
        try:
            self.backend.start(
                config.sample_rate,
                config.enabled_channels,
                config.use_device_timestamp,
            )
        except Exception:
            try:
                self.backend.stop()
            except Exception as cleanup_error:
                self.on_error(cleanup_error)
            raise
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                timestamps, values = self.backend.read()
                if timestamps:
                    self.total_samples += len(timestamps)
                    self.on_data(timestamps, values)
                    with self._record_lock:
                        if self._recording:
                            try:
                                self._write_queue.put_nowait((timestamps, values))
                            except queue.Full as exc:
                                raise RuntimeError("Fila de gravacao cheia; o disco esta lento.") from exc
                self._stop_event.wait(0.02)
        except Exception as exc:
            self.on_error(exc)
        finally:
            try:
                self.backend.stop()
            except Exception as exc:
                self.on_error(exc)
            self.stop_recording()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                raise RuntimeError("A aquisicao ainda esta encerrando. Aguarde antes de reiniciar.")
        self._thread = None
        self.stop_recording()

    def start_recording(self, path: str | Path) -> None:
        if not self.running or self._config is None:
            raise RuntimeError("Inicie a aquisicao antes da gravacao.")
        if self._recording:
            return
        self._csv_path = Path(path)
        self._csv_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_queue = queue.Queue(maxsize=200)
        self._recording = True
        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._writer_thread.start()

    def _writer_loop(self) -> None:
        try:
            self._write_csv()
        except Exception as exc:
            with self._record_lock:
                self._recording = False
            self._stop_event.set()
            self.on_error(exc)

    def _write_csv(self) -> None:
        assert self._csv_path is not None and self._config is not None
        channels = self._config.enabled_channels
        with self._csv_path.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.writer(stream, delimiter=";")
            writer.writerow(["Experimento", self._config.name])
            writer.writerow(["Operador", self._config.operator])
            writer.writerow(["Descricao", self._config.description])
            writer.writerow(["Inicio", datetime.now().isoformat(timespec="seconds")])
            writer.writerow(["Frequencia_Hz", self._config.sample_rate])
            for channel in channels:
                if channel.engineering_min is not None:
                    writer.writerow(['Limites_engenharia_canal', channel.number + 1,
                                     channel.engineering_min, channel.engineering_max, channel.unit])
                if channel.input_type or channel.input_scale or channel.input_min is not None:
                    input_scale = (f'{channel.input_min:g} a {channel.input_max:g} {channel.input_unit}'
                                   if channel.input_min is not None else channel.input_scale)
                    writer.writerow(["Entrada_canal", channel.number + 1,
                                     channel.input_type, input_scale])
                if channel.sensor_profile:
                    writer.writerow(["Sensor_canal", channel.number + 1,
                                     json.dumps(channel.sensor_profile, ensure_ascii=False)])
                    writer.writerow(["Calibracao_canal", channel.number + 1,
                                     channel.gain, channel.offset, channel.unit])
            writer.writerow([])
            writer.writerow(
                ["tempo_s"] + [f"{ch.label()} [{ch.unit}]" for ch in channels]
            )
            while self._recording or not self._write_queue.empty():
                try:
                    item = self._write_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                timestamps, values = item  # type: ignore[misc]
                for index, timestamp in enumerate(timestamps):
                    writer.writerow(
                        [f"{timestamp:.9f}"]
                        + [f"{channel[index]:.12g}" for channel in values]
                    )
                stream.flush()

    def stop_recording(self) -> Path | None:
        with self._record_lock:
            self._recording = False
        if self._writer_thread and self._writer_thread is not threading.current_thread():
            self._writer_thread.join()
        self._writer_thread = None
        return self._csv_path
