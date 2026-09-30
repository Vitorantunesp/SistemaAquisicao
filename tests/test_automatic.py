import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from dataclasses import replace
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import numpy as np
from PyQt6.QtWidgets import QApplication, QDialog
from ads1800_app.config import ChannelConfig
from ads1800_app.monitor_signal import MonitorConfig
from ads1800_app.automatic import TriggerRecorder, Capture, CaptureAnalysis, channel_threshold, morlet_scalograms
from ads1800_app.ui.automatic import TriggerDialog
from ads1800_app.ui.bridge import BridgeApp


def configuration(**kwargs):
    defaults = dict(automatic_enabled=True, sample_rate=1000, pre_trigger=.01,
                    capture_duration=.05, wavelet_min=10, wavelet_max=100,
                    channels=[ChannelConfig(0, enabled=True, unit='g', engineering_min=-10, engineering_max=10),
                              ChannelConfig(3, enabled=True, unit='g', engineering_min=-20, engineering_max=20)])
    defaults.update(kwargs)
    return MonitorConfig(**defaults)


class TriggerTests(unittest.TestCase):
    def test_negative_trigger_captures_all_channels_exactly_across_blocks(self):
        recorder = TriggerRecorder(configuration())
        signal = np.zeros((2, 100))
        signal[1, 30] = -2  # Exactly 10% of channel 4 upper scale, negative polarity.
        result = []
        for a, b in ((0, 17), (17, 31), (31, 54), (54, 100)):
            result += recorder.feed(np.arange(a, b) / 1000, signal[:, a:b])
        self.assertEqual(len(result), 1)
        event = result[0]
        self.assertEqual(event.trigger_channels, [3])
        self.assertEqual(event.values.shape, (2, 50))
        np.testing.assert_array_equal(event.values, signal[:, 20:70])
        self.assertAlmostEqual(event.times[0], -.01)
        self.assertEqual(event.times[10], 0)
        self.assertAlmostEqual(event.trigger_time, .03)

    def test_full_prehistory_required_and_sustained_level_does_not_retrigger(self):
        recorder = TriggerRecorder(configuration())
        x = np.ones((2, 80)) * 3
        self.assertFalse(recorder.feed(np.arange(80) / 1000, x))
        x[:, :5] = 0
        events = recorder.feed(np.arange(80, 160) / 1000, x)
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0].trigger_time, .085)
        self.assertFalse(recorder.feed(np.arange(160, 240) / 1000, np.ones((2, 80)) * 3))

    def test_each_channel_can_cross_while_another_remains_high(self):
        recorder = TriggerRecorder(configuration(pre_trigger=0))
        x = np.zeros((2, 60))
        x[0] = 3
        self.assertEqual(len(recorder.feed(np.arange(60) / 1000, x)), 1)
        x[1, 5:] = 3
        events = recorder.feed(np.arange(60, 120) / 1000, x)
        self.assertEqual(events[0].trigger_channels, [3])
        self.assertAlmostEqual(events[0].trigger_time, .065)

    def test_gap_and_nan_discard_partial_capture_then_recover(self):
        for gap in (True, False):
            recorder = TriggerRecorder(configuration())
            x = np.zeros((2, 30))
            x[0, 20] = 1
            recorder.feed(np.arange(30) / 1000, x)
            self.assertIsNotNone(recorder.parts)
            t = np.arange(30, 130) / 1000 + (1 if gap else 0)
            x = np.zeros((2, 100))
            if not gap:
                x[:, 0] = np.nan
            x[1, 20] = 2
            events = recorder.feed(t, x)
            self.assertEqual(recorder.discarded, 1)
            self.assertEqual(len(events), 1)
            self.assertTrue(np.isfinite(events[0].values).all())

    def test_busy_suppresses_triggers_but_retains_pretrigger(self):
        recorder = TriggerRecorder(configuration())
        x = np.zeros((2, 50))
        x[0, 20] = 2
        self.assertFalse(recorder.feed(np.arange(50) / 1000, x, allow_trigger=False))
        x[0, 0] = 2
        events = recorder.feed(np.arange(50, 100) / 1000, x)
        self.assertAlmostEqual(events[0].trigger_time, .05)
        self.assertEqual(events[0].pre_samples, 10)

    def test_validation_persistence_and_default_from_hardware(self):
        config = configuration()
        self.assertEqual(channel_threshold(config.channels[1], config), 2)
        self.assertEqual(channel_threshold(config.channels[1], replace(config, trigger_thresholds={'3': .5})), .5)
        for changes in ({'capture_duration': .005}, {'wavelet_max': 500}, {'pre_trigger': float('nan')},
                        {'trigger_thresholds': {'0': 0}}, {'capture_duration': 120, 'sample_rate': 96000}):
            with self.assertRaises(ValueError):
                replace(config, **changes).validate()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            config.save(path)
            self.assertEqual(MonitorConfig.load(path), config)

    def test_morlet_frequency_localization_and_24khz_analysis(self):
        for fs in (1000, 24000):
            config = configuration(sample_rate=fs, capture_duration=1, pre_trigger=.2,
                                   wavelet_min=10, wavelet_max=100)
            t = np.arange(fs) / fs
            event = Capture(1, .2, [0], round(.2 * fs), fs,
                            np.array([np.sin(2 * np.pi * 40 * t), np.zeros(fs)]))
            result = morlet_scalograms(event, config)
            average = result['power'][0, :, 80:-80].mean(axis=1)
            self.assertAlmostEqual(result['frequencies'][average.argmax()], 40, delta=2)
            self.assertEqual(result['wavelet'], 'cmor1.5-1.0')
            self.assertLessEqual(result['power'].shape[-1], 1200)
            self.assertAlmostEqual(result['times'][0], -.2)
            self.assertEqual(np.max(result['power'][1]), 0)
            np.testing.assert_allclose(event.values[0], np.sin(2 * np.pi * 40 * t))


class AutomaticUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_for(self, predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertTrue(predicate())

    def test_dialog_threshold_override_and_validation(self):
        dialog = TriggerDialog(configuration())
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.rows[1][2].value(), 2)
        dialog.percent.setValue(20)
        self.assertEqual(dialog.rows[1][2].value(), 4)
        dialog.rows[1][1].setChecked(False)
        dialog.rows[1][2].setValue(.5)
        self.assertEqual(dialog.read_config().trigger_thresholds, {'3': .5})
        dialog.pre.setValue(dialog.duration.value())
        dialog.apply()
        self.assertTrue(dialog.error.text())
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_automatic_simulator_save_display_restart_and_stop(self):
        with tempfile.TemporaryDirectory() as folder, patch('ads1800_app.ui.bridge.PROJECT_ROOT', Path(folder)):
            window = BridgeApp()
            errors = []
            window._show_error = errors.append
            window.show()
            window.mode.setCurrentText('Simulador')
            window.connect_button.click()
            self.wait_for(lambda: not window._busy)
            window.channel_widgets[1]['enabled'].setChecked(True)
            window.automatic_enabled.setChecked(True)
            window._automatic_options.update(pre_trigger=.02, capture_duration=.15, wavelet_min=10)
            try:
                for rate in (1000, 24000):
                    window.frequency.setCurrentText(str(rate))
                    window.start_button.click()
                    self.wait_for(lambda: not window._busy)
                    self.assertTrue(window.controller.running)
                    self.assertFalse(window.trigger_button.isEnabled())
                    self.wait_for(lambda: bool(window.event_viewer.history))
                    capture, result, path, channels = window.event_viewer.history[-1]
                    self.assertEqual(len(channels), 2)
                    self.assertEqual(capture.values.shape, (2, round(rate * .15)))
                    self.assertEqual(window.view_stack.currentWidget(), window.event_viewer)
                    self.assertTrue(window.controller.running)
                    with np.load(path) as saved:
                        np.testing.assert_array_equal(saved['values'], capture.values)
                    self.assertTrue(path.with_name(path.stem + '_morlet.npz').exists())
                    window.mode_buttons['Tempo'].click()
                    self.assertEqual(window.view_stack.currentWidget(), window.plot)
                    window.stop_button.click()
                    self.wait_for(lambda: not window._busy)
                    self.assertTrue(window.trigger_button.isEnabled())
                self.assertFalse(errors, errors)
            finally:
                self.wait_for(lambda: not window._busy)
                window.close()
                self.wait_for(lambda: not window.isVisible())

    def test_background_storage_failure_is_reported(self):
        config = configuration()
        event = Capture(1, .01, [0], 10, 1000, np.zeros((2, 50)))
        with tempfile.TemporaryDirectory() as folder:
            occupied = Path(folder) / 'file'
            occupied.write_text('not a folder')
            service = CaptureAnalysis(config, occupied)
            self.assertTrue(service.submit(event))
            self.assertFalse(service.submit(event))
            self.wait_for(lambda: not service.results.empty())
            self.assertEqual(service.results.get_nowait()[0], 'error')
            service.close()
