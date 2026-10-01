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


class ModalUiTests(unittest.TestCase):
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
                window.arm()
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
