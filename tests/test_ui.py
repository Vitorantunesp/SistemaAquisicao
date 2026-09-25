import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication
from ads1800_app.ui.app import Ads1800App


class QtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_for(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertTrue(predicate())

    def test_connect_restart_record_config_and_close(self):
        window = Ads1800App()
        self.assertEqual(window.frequency.itemText(window.frequency.count() - 1), '24000')
        errors = []
        window._show_error = errors.append
        window.show()
        window.mode.setCurrentText('Simulador')
        window.connect_button.click()
        self.wait_for(lambda: not window._busy)
        self.assertTrue(window.backend.connected)
        self.assertIn('24000', window.frequency_limit.text())
        config = window._read_config()
        config.sample_rate = 24000
        config.channels[1].enabled = True
        config.channels[1].gain = 2
        config.channels[1].offset = 3
        config.description = 'Teste PyQt'
        window._apply_config(config)
        self.assertEqual(window._read_config(), config)
        window.tabs.setCurrentWidget(window.acquisition_tab)
        with tempfile.TemporaryDirectory() as directory:
            for cycle in range(3):
                window.start_button.click()
                self.wait_for(lambda: not window._busy)
                self.assertTrue(window.controller.running)
                self.assertFalse(window.channels_tab.isEnabled())
                path = Path(directory) / f'{cycle}.csv'
                with patch('ads1800_app.ui.app.QFileDialog.getSaveFileName', return_value=(str(path), '')):
                    window.record_button.click()
                samples_at_record_start = window.controller.total_samples
                window.plot.channel_checks[1].setChecked(False)
                self.assertTrue(window.plot.panels[1].isHidden())
                window.time_window.setValue(2)
                window.refresh_rate.setValue(5)
                window.plot_columns.setCurrentIndex(0)
                self.assertEqual(len(window.plot.panels), 2)
                self.assertEqual(window.plot.timer.interval(), 200)
                self.assertEqual(window.plot.buffer.seconds, 2)
                panel = window.plot.panels[0]
                panel.minimum.setValue(-2)
                panel.maximum.setValue(2)
                panel.auto.setChecked(False)
                self.assertEqual(panel.canvas.y_range, (-2, 2))
                self.wait_for(lambda: window.controller.total_samples > samples_at_record_start + 2400)
                self.wait_for(lambda: len(window.plot.panels[0].canvas.times) > 0)
                previous_end = window.plot.panels[0].canvas.x_range[1]
                self.wait_for(lambda: window.plot.panels[0].canvas.x_range[1] > previous_end)
                self.assertTrue(window.controller.running)
                self.assertTrue(window.controller.recording)
                window.plot.channel_checks[1].setChecked(True)
                self.assertFalse(window.plot.panels[1].isHidden())
                self.assertEqual(window.plot.panels[1].canvas.times[-1], window.plot.panels[0].canvas.times[-1])
                self.app.processEvents()
                self.assertFalse(window.grab().isNull())
                window.stop_button.click()
                self.wait_for(lambda: not window._busy)
                self.assertFalse(window.controller.running)
                self.assertTrue(window.start_button.isEnabled())
                self.assertTrue(window.backend.connected)
                content = path.read_text(encoding='utf-8-sig')
                self.assertIn('Canal 2 [V]', content)
                self.assertIn('Frequencia_Hz;24000', content)
                self.assertGreater(len(content.splitlines()), 10)
        window.close()
        self.wait_for(lambda: not window.isVisible())
        self.assertFalse(errors)
