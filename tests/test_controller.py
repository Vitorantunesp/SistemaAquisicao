from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from ads1800_app.backends.simulator import SimulatorBackend
from ads1800_app.config import ExperimentConfig
from ads1800_app.controller import AcquisitionController


class ControllerTests(unittest.TestCase):
    def test_writer_failure_stops_acquisition_and_can_restart(self):
        backend = SimulatorBackend()
        backend.connect("127.0.0.1")
        errors = []
        controller = AcquisitionController(backend, lambda t, v: None, errors.append)
        with tempfile.TemporaryDirectory() as directory:
            controller.start(ExperimentConfig())
            with patch.object(controller, '_write_csv', side_effect=OSError('disk full')):
                controller.start_recording(Path(directory) / 'failed.csv')
                deadline = time.monotonic() + 2
                while controller.running and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertFalse(controller.running)
            self.assertFalse(controller.recording)
            self.assertEqual(str(errors[0]), 'disk full')
            controller.start(ExperimentConfig())
            controller.start_recording(Path(directory) / 'recovered.csv')
            time.sleep(.06)
            controller.stop()
            self.assertIn('tempo_s', (Path(directory) / 'recovered.csv').read_text(encoding='utf-8-sig'))

    def test_restart_same_backend_and_controller(self):
        backend = SimulatorBackend()
        backend.connect("127.0.0.1")
        errors = []
        received = []
        controller = AcquisitionController(backend, lambda t, v: received.extend(t), errors.append)
        for _ in range(3):
            received.clear()
            controller.start(ExperimentConfig())
            time.sleep(.08)
            controller.stop()
            self.assertFalse(controller.running)
            self.assertTrue(backend.connected)
            self.assertEqual(received[0], 0)
        self.assertFalse(errors)

    def test_stop_timeout_keeps_worker_reference_and_blocks_restart(self):
        backend = Mock()
        controller = AcquisitionController(backend, lambda t, v: None, lambda e: None)
        worker = Mock()
        worker.is_alive.return_value = True
        controller._thread = worker
        with self.assertRaises(RuntimeError):
            controller.stop()
        self.assertIs(controller._thread, worker)
        with self.assertRaises(RuntimeError):
            controller.start(ExperimentConfig())
        backend.start.assert_not_called()

    def test_failed_start_cleans_backend(self):
        backend = Mock()
        backend.start.side_effect = ValueError('start failed')
        controller = AcquisitionController(backend, lambda t, v: None, lambda e: None)
        with self.assertRaises(ValueError):
            controller.start(ExperimentConfig())
        backend.stop.assert_called_once()
        self.assertFalse(controller.running)

    def test_records_csv(self):
        backend = SimulatorBackend()
        backend.connect("127.0.0.1")
        errors = []
        controller = AcquisitionController(backend, lambda _t, _v: None, errors.append)
        config = ExperimentConfig(name="Teste CSV", sample_rate=500.0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dados.csv"
            controller.start(config)
            controller.start_recording(path)
            time.sleep(0.12)
            controller.stop()
            content = path.read_text(encoding="utf-8-sig")
        self.assertFalse(errors)
        self.assertIn("Experimento;Teste CSV", content)
        self.assertIn("tempo_s;Canal 1 [V]", content)
        self.assertGreater(controller.total_samples, 0)


if __name__ == "__main__":
    unittest.main()
