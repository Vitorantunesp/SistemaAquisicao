import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication
from ads1800_app.config import ChannelConfig, ExperimentConfig
from ads1800_app.ui.app import Ads1800App
from ads1800_app.sensors import SensorProfile, save_catalog


class LimitsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_electrical_and_display_limits_are_separate_synced_and_saved(self):
        window = Ads1800App()
        window.channel_widgets[0]['unit'].setText('m/s²')
        row = window.limits_tab.rows[0]
        row['input_low'].setValue(-10)
        row['input_high'].setValue(10)
        row['input_unit'].setText('V')
        row['defined'].setChecked(True)
        row['low'].setValue(-100)
        row['high'].setValue(100)
        row['auto'].setChecked(False)
        config = window._read_config()
        window.plot.reset(config.enabled_channels)
        panel = window.plot.panels[0]
        self.assertEqual(panel.canvas.y_range, (-100, 100))
        self.assertEqual(window.channel_widgets[0]['input_scale'].text(), '-10 a 10 V')
        panel.minimum.setValue(-200)
        panel.maximum.setValue(200)
        self.assertEqual(row['low'].value(), -200)
        self.assertEqual(row['high'].value(), 200)
        self.assertEqual(row['input_low'].value(), -10)
        row['low'].setValue(-50)
        row['high'].setValue(50)
        self.assertEqual(panel.canvas.y_range, (-50, 50))
        # Samples remain calibrated measurements, never clipped by either range.
        window.plot.append([0, 1], [[250, -250]])
        window.plot.refresh()
        self.assertEqual(panel.canvas.values[-1], -250)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'experiment.json'
            window._read_config().save(path)
            saved = ExperimentConfig.load(path)
            self.assertEqual(saved.channels[0].input_min, -10)
            self.assertEqual(saved.channels[0].display_min, -50)
            window._apply_config(saved)
            window.plot.reset(saved.enabled_channels)
            self.assertEqual(window.plot.panels[0].canvas.y_range, (-50, 50))
        row['input_high'].setValue(-20)
        with self.assertRaisesRegex(ValueError, 'elétrica'):
            window._read_config()
        window.close()

    def test_catalog_numeric_input_range_applies_to_tab(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sensors.json'
            save_catalog(path, [SensorProfile(name='Martelo', input_min=4, input_max=20, input_unit='mA')])
            with patch('ads1800_app.ui.app.CATALOG_PATH', path):
                window = Ads1800App()
                window.sensor_channel.setCurrentIndex(3)
                window._apply_sensor()
                channel = window._read_config().channels[3]
                self.assertEqual((channel.input_min, channel.input_max, channel.input_unit), (4, 20, 'mA'))
                self.assertEqual(channel.input_scale, '4 a 20 mA')
                window.close()

    def test_old_configuration_keeps_auto_and_no_unknown_electrical_range(self):
        config = ExperimentConfig(channels=[ChannelConfig(0, enabled=True, input_scale='±100 mV')])
        window = Ads1800App()
        window._apply_config(config)
        self.assertFalse(window.limits_tab.rows[0]['defined'].isChecked())
        self.assertTrue(window.limits_tab.rows[0]['auto'].isChecked())
        self.assertEqual(window._read_config().channels[0].input_scale, '±100 mV')
        window.close()
