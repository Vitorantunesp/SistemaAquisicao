import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
from pathlib import Path
import numpy as np
import time
import unittest
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication
from ads1800_app.ui.modal import ModalApp
from ads1800_app.modal import ModalConfig, ModalSession, ImpactCapture


class ModalUiTests(unittest.TestCase):
    def test_multiple_accelerometers_live_selector_saved_and_exported(self):
        window = ModalApp()
        errors = []
        window.error = errors.append
        try:
            window.connect_device()
            self.wait(lambda: not window.busy)
            window.fields['duration'].setValue(.5)
            # Noncontiguous hardware channels must follow the configured sensor order.
            window.extra_sensors.setPlainText('A2; 4; 0.8; 0.25; 2\nA3; 3; 0.2; 0.25; 1')
            with tempfile.TemporaryDirectory() as folder:
                with patch('ads1800_app.ui.modal.QFileDialog.getExistingDirectory', return_value=folder):
                    window.start()
                self.wait(lambda: not window.busy)
                window.arm()
                self.wait(lambda: window.pending is not None)
                record = window.pending
                with np.load(window.session.directory/record['file']) as saved:
                    self.assertEqual(saved['accelerations_m_s2'].shape, (window.session.config.n, 3))
                    np.testing.assert_allclose(saved['accelerations_m_s2'][:, 0], saved['acceleration_m_s2'])
                window.sensor.setCurrentIndex(1)
                self.assertEqual(window.sensor.currentText(), 'A2')
                window.review(True)
                self.assertTrue(window.capture.armed)
                window.stop()
                self.wait(lambda: not window.busy)
                window.sensor.setCurrentIndex(2)
                self.assertTrue(np.isfinite(window.plots['frf'].values).any())
                window.post.reference.setCurrentIndex(2)
                self.assertEqual(window.post.view.config.accelerometer, [.2, .25])
                csv = Path(folder)/'signals.csv'
                with patch('ads1800_app.ui.modal.QFileDialog.getSaveFileName', return_value=(str(csv), '')):
                    window.export_hit()
                self.assertEqual(np.loadtxt(csv, delimiter=';', skiprows=1).shape[1], 9)
                window.adopt_session(ModalSession.load(window.session.directory))
                self.assertEqual(window.sensor.count(), 3)
                self.assertEqual(window.post.reference.count(), 3)
                self.assertFalse(errors, errors)
        finally:
            window.close()
            self.wait(lambda: window.backend is None)

    def test_ready_beep_adjustment_and_exit_with_missing_session_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            c = ModalConfig(sample_rate=1000, bandpass_enabled=False, duration=.2, pretrigger=.02, force_width=.01)
            session = ModalSession(Path(directory)/'run', c)
            window = ModalApp()
            try:
                window.adopt_session(session)
                window.capture = ImpactCapture(c)
                window.apply_trigger_settings(25, 'Negativo', .004)
                self.assertEqual(ModalSession.load(session.directory).config.threshold, 25)
                window.capture.arm('P1')
                with patch('ads1800_app.ui.modal.QApplication.beep') as beep:
                    window.announce_ready()
                    beep.assert_not_called()
                    window.capture.feed(np.arange(30)/1000, np.zeros(30), np.zeros(30))
                    window.announce_ready()
                    window.announce_ready()
                    beep.assert_called_once()
                window.capture.cancel()
                data = np.zeros((c.n, 3))
                data[:, 0] = np.arange(c.n)/1000
                data[c.pre, 1:] = [-40, 3]
                record, _ = session.capture('P1', data)
                self.assertEqual(record['trigger']['threshold_N'], 25)
                window.pending = record
                # Moving the test folder reproduces a missing path without deletion.
                session.directory.rename(Path(directory)/'moved')
                with self.assertRaises(OSError):
                    session.review(record, True)
                self.assertEqual(record['status'], 'pendente')
                window.leave_session()
                self.assertIsNone(window.session)
                self.assertIsNone(window.pending)
                self.assertTrue(window.open_button.isEnabled())
                self.assertEqual(window.tabs.currentIndex(), 0)
            finally:
                window.close()

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait(self, predicate, timeout=8):
        deadline = time.monotonic()+timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertTrue(predicate())

    def test_simulated_capture_review_export_and_stop(self):
        window = ModalApp()
        self.assertTrue(window.bandpass.isChecked())
        self.assertEqual(window.fields['low_cut'].value(), 1)
        self.assertEqual(window.fields['high_cut'].value(), 500)
        window.bandpass.setChecked(False)
        self.assertFalse(window.fields['high_cut'].isEnabled())
        window.bandpass.setChecked(True)
        errors = []
        window.error = errors.append
        window.show()
        try:
            window.connect_device()
            self.wait(lambda: not window.busy)
            self.assertIsNotNone(window.backend)
            window.fields['duration'].setValue(.5)
            with tempfile.TemporaryDirectory() as directory:
                settings_path = Path(directory)/'config.json'
                with patch('ads1800_app.ui.modal.QFileDialog.getSaveFileName', return_value=(str(settings_path), '')):
                    window.save_config()
                window.bandpass.setChecked(False)
                window.fields['high_cut'].setValue(300)
                with patch('ads1800_app.ui.modal.QFileDialog.getOpenFileName', return_value=(str(settings_path), '')):
                    window.load_config()
                self.assertTrue(window.bandpass.isChecked())
                self.assertEqual(window.fields['high_cut'].value(), 500)
                with patch('ads1800_app.ui.modal.QFileDialog.getExistingDirectory', return_value=directory):
                    window.start()
                self.wait(lambda: not window.busy)
                self.assertTrue(window.controller.running)
                window.arm()
                self.assertFalse(window.point.isEnabled())
                self.wait(lambda: window.pending is not None)
                self.assertEqual(window.pending['point'], 'P1')
                self.assertTrue(window.accept_button.isEnabled())
                window.review(True)
                self.assertEqual(len(window.session.hits('P1')), 1)
                self.assertTrue(window.capture.armed)
                self.wait(lambda: window.pending is not None)
                window.review(True)
                self.assertEqual(len(window.session.hits('P1')), 2)
                self.assertTrue(any(v == v for v in window.plots['coherence'].values))
                csv = Path(directory)/'hit.csv'
                with patch('ads1800_app.ui.modal.QFileDialog.getSaveFileName', return_value=(str(csv), '')):
                    window.export_hit()
                self.assertEqual(np.loadtxt(csv, delimiter=';', skiprows=1).shape, (window.session.config.n, 5))
                window.stop()
                self.wait(lambda: not window.busy)
                self.assertFalse(window.controller.running)
                self.assertTrue(window.session.config.bandpass_enabled)
                saved_folder = str(window.session.directory)
                with patch('ads1800_app.ui.modal.QFileDialog.getExistingDirectory', return_value=saved_folder):
                    window.open_session()
                self.assertEqual(len(window.session.hits('P1')), 2)
                window.inspect(0)
                window.review(False)
                self.assertEqual(len(window.session.hits('P1')), 1)
                self.assertFalse(errors, errors)
        finally:
            window.close()
            self.wait(lambda: window.backend is None)
