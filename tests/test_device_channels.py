import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from PyQt6.QtWidgets import QApplication
from ads1800_app.config import ChannelConfig, ExperimentConfig
from ads1800_app.ui.app import Ads1800App
from ads1800_app.controller import AcquisitionController


class DeviceChannelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_hardware_metadata_wins_over_legacy_file_and_axes_do_not_calibrate(self):
        window = Ads1800App()
        self.addCleanup(window.close)
        self.assertFalse(hasattr(window, 'limits_tab'))
        self.assertFalse(hasattr(window, 'sensor_choice'))
        with self.assertRaisesRegex(ValueError, 'Conecte'):
            window._read_config()
        window._show_device_channels([ChannelConfig(0, name='Martelo', unit='N',
                                                    engineering_min=-100, engineering_max=300)])
        old = ExperimentConfig(channels=[ChannelConfig(0, enabled=True, gain=400, offset=20,
                                                       name='Antigo', unit='V', input_min=-10,
                                                       input_max=10, sensor_profile={'name': 'antigo'})])
        window._apply_config(old)
        config = window._read_config()
        channel = config.channels[0]
        self.assertEqual((channel.name, channel.unit, channel.gain, channel.offset), ('Martelo', 'N', 1, 0))
        self.assertEqual((channel.engineering_min, channel.engineering_max), (-100, 300))
        self.assertFalse(channel.sensor_profile)
        self.assertIsNone(channel.input_min)
        self.assertEqual(set(window.channel_widgets[0]), {'enabled'})
        window.plot.reset(config.enabled_channels)
        panel = window.plot.panels[0]
        panel.minimum.setValue(-50)
        panel.maximum.setValue(50)
        panel.auto.setChecked(False)
        window.plot.append([0, 1], [[250, -250]])
        window.plot.refresh()
        self.assertEqual(panel.canvas.values[-1], -250)
        self.assertEqual(window._read_config().channels[0].display_min, -50)
        self.assertEqual(window._read_config().channels[0].engineering_min, -100)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'experiment.json'
            window._read_config().save(path)
            window._apply_config(ExperimentConfig.load(path))
            self.assertEqual(window._read_config().channels[0].display_max, 50)
            controller = AcquisitionController(None, lambda t, v: None, lambda e: None)
            controller._config = config
            controller._csv_path = Path(directory) / 'samples.csv'
            controller._write_csv()
            content = controller._csv_path.read_text(encoding='utf-8-sig')
            self.assertIn('Limites_engenharia_canal;1;-100;300;N', content)
            self.assertIn('Martelo [N]', content)
            self.assertNotIn('Calibracao_canal', content)

    def test_selection_survives_reconnect_with_fresh_metadata(self):
        window = Ads1800App()
        self.addCleanup(window.close)
        channels = [ChannelConfig(i, name=f'Canal {i}', unit='g', engineering_min=-5,
                                  engineering_max=5) for i in range(2)]
        window._show_device_channels(channels)
        window.channel_widgets[0]['enabled'].setChecked(False)
        window.channel_widgets[1]['enabled'].setChecked(True)
        window._show_device_channels([])
        channels[1].unit = 'm/s²'
        channels[1].engineering_max = 50
        window._show_device_channels(channels)
        config = window._read_config()
        self.assertEqual([c.number for c in config.enabled_channels], [1])
        self.assertEqual(config.enabled_channels[0].unit, 'm/s²')
        self.assertEqual(config.enabled_channels[0].engineering_max, 50)
