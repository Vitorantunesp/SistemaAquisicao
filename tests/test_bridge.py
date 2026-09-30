import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import numpy as np
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFontDatabase
from ads1800_app.monitor_signal import MonitorConfig, StreamingBandpass, spectra, validate_bandpass
from ads1800_app.ui.bridge import BridgeApp


class SignalTests(unittest.TestCase):
    def test_fft_amplitude_and_psd_energy(self):
        fs = 1000
        for n in (4000, 4001):
            t = np.arange(n) / fs
            f, a, pf, p = spectra(3 + 2 * np.sin(2 * np.pi * 50 * t), fs)
            self.assertAlmostEqual(f[np.argmax(a)], 50, delta=fs / n)
            self.assertAlmostEqual(max(a), 2, delta=.02)
            self.assertAlmostEqual(np.sum((p[1:] + p[:-1]) * np.diff(pf) / 2), 2, delta=.03)
        self.assertEqual(len(spectra([1, 2], fs)[0]), 0)

    def test_stream_filter_continuity_and_attenuation(self):
        fs = 1000
        t = np.arange(10000) / fs
        x = (np.sin(2 * np.pi * 3 * t) + np.sin(2 * np.pi * 40 * t) + np.sin(2 * np.pi * 200 * t))[None, :]
        whole = StreamingBandpass(fs, 20, 80, 1).apply(x)
        stream = StreamingBandpass(fs, 20, 80, 1)
        parts = np.concatenate([stream.apply(p) for p in np.array_split(x, 57, axis=1)], axis=1)
        np.testing.assert_allclose(parts, whole, atol=1e-12)
        f, a, _, _ = spectra(whole[0, 2000:], fs)
        self.assertGreater(a[np.argmin(abs(f - 40))], .95)
        self.assertLess(a[np.argmin(abs(f - 3))], .01)
        self.assertLess(a[np.argmin(abs(f - 200))], .02)
        broken = np.ones((1, 40))
        broken[0, 5] = np.nan
        result = stream.apply(broken)
        self.assertTrue(np.isfinite(result[0, 6:]).all())

    def test_validation_and_persistence(self):
        for low, high in [(0, 5), (4, 4), (10, 501), (1, float('nan'))]:
            with self.assertRaises(ValueError):
                validate_bandpass(1000, low, high)
        config = MonitorConfig(bandpass_enabled=True, low_cut=2, high_cut=90)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'ponte.json'
            config.save(path)
            self.assertEqual(MonitorConfig.load(path), config)


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        font = Path('C:/Windows/Fonts/segoeui.ttf')
        if font.exists():
            QFontDatabase.addApplicationFont(str(font))

    def wait_for(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertTrue(predicate())

    def test_full_simulator_workflow(self):
        window = BridgeApp()
        errors = []
        window._show_error = errors.append
        window.show()
        try:
            self.assertFalse(window.start_button.isEnabled())
            window.mode.setCurrentText('Simulador')
            window.connect_button.click()
            self.wait_for(lambda: not window._busy)
            for widgets in window.channel_widgets:
                widgets['enabled'].setChecked(True)
            self.assertEqual(len(window.bridge_map.channels), 8)
            window.filter_enabled.setChecked(True)
            window.high_cut.setValue(500)
            window.start_button.click()
            self.assertEqual(len(errors), 1)
            errors.clear()
            window.high_cut.setValue(100)
            window.tabs.setCurrentWidget(window.acquisition_tab)
            with tempfile.TemporaryDirectory() as folder:
                for rate in (1000, 24000):
                    window.frequency.setCurrentText(str(rate))
                    window.start_button.click()
                    self.wait_for(lambda: not window._busy)
                    self.assertTrue(window.controller.running)
                    self.assertFalse(window.channels_tab.isEnabled())
                    self.wait_for(lambda: window.controller.total_samples > rate // 2)
                    for mode in ('FFT', 'Espectro', 'Todos', 'Tempo'):
                        window.mode_buttons[mode].click()
                        self.app.processEvents()
                        self.assertEqual(window.plot.mode, mode)
                    self.assertGreater(len(window.plot.panels[0].plots[1][1].values), 0)
                    path = Path(folder) / f'{rate}.csv'
                    with patch('ads1800_app.ui.app.QFileDialog.getSaveFileName', return_value=(str(path), '')):
                        window.record_button.click()
                    at_start = window.controller.total_samples
                    self.wait_for(lambda: window.controller.total_samples > at_start + rate // 4)
                    origin = window.plot.origin
                    window.plot.clear()
                    self.assertEqual(window.plot.origin, origin)
                    window.stop_button.click()
                    self.wait_for(lambda: not window._busy)
                    self.assertTrue(window.start_button.isEnabled())
                    self.assertIn('Canal 8 [V]', path.read_text(encoding='utf-8-sig'))
            self.assertFalse(errors, errors)
        finally:
            self.wait_for(lambda: not window._busy)
            window.close()
            self.wait_for(lambda: not window.isVisible())

    def test_discontinuity_and_clear_do_not_reuse_old_spectra(self):
        from ads1800_app.ui.bridge_plots import BridgeDashboard
        plot = BridgeDashboard()
        config = MonitorConfig(bandpass_enabled=True)
        plot.configure(config)
        plot.reset(config.enabled_channels)
        plot.set_mode('Todos')
        plot.append(np.arange(100) / 1000, np.ones((1, 100)))
        plot.refresh()
        self.assertGreater(len(plot.panels[0].plots[1][1].values), 0)
        plot.append(1 + np.arange(10) / 1000, np.ones((1, 10)))
        self.assertEqual(len(plot.buffer.snapshot()[0]), 10)
        plot.clear()
        self.assertEqual(len(plot.panels[0].plots[1][1].values), 0)
        self.assertEqual(plot.origin, 0)
        plot.timer.stop()
        plot.deleteLater()

    def test_frequency_axes_follow_active_filter_and_return_to_nyquist(self):
        from ads1800_app.ui.bridge_plots import BridgeDashboard
        plot = BridgeDashboard()
        self.addCleanup(plot.deleteLater)
        self.addCleanup(plot.timer.stop)
        for active, expected in ((True, 80), (False, 500)):
            config = MonitorConfig(bandpass_enabled=active, low_cut=5, high_cut=80)
            plot.configure(config)
            plot.reset(config.enabled_channels)
            plot.set_mode('Todos')
            t = np.arange(1000) / 1000
            plot.append(t, [np.sin(2 * np.pi * 30 * t)])
            plot.refresh()
            for _, canvas in plot.panels[0].plots[1:]:
                self.assertEqual(canvas.x_range, (0, expected))
                # Axis clipping must not alter the computed spectrum.
                self.assertEqual(canvas.times[-1], 500)

    def test_engineering_limits_and_independent_zoom_survive_new_samples(self):
        from ads1800_app.config import ChannelConfig
        from ads1800_app.ui.bridge_plots import BridgeDashboard
        plot = BridgeDashboard()
        self.addCleanup(plot.deleteLater)
        self.addCleanup(plot.timer.stop)
        channels = [ChannelConfig(0, enabled=True, unit='g', engineering_min=-20, engineering_max=80),
                    ChannelConfig(1, enabled=True, unit='m/s²', engineering_min=-500, engineering_max=500)]
        plot.configure(MonitorConfig(channels=channels))
        plot.reset(channels)
        plot.set_mode('Todos')
        panel = plot.panels[0]
        time_canvas = panel.plots[0][1]
        self.assertEqual(time_canvas.y_range, (-20, 80))
        panel.scale_buttons[0]['+'].click()
        self.assertEqual(time_canvas.y_range, (5, 55))
        t = np.arange(1000) / 1000
        plot.append(t, [200 * np.sin(2 * np.pi * 30 * t), np.ones(1000)])
        plot.refresh()
        self.assertEqual(time_canvas.y_range, (5, 55))
        self.assertEqual(plot.panels[1].plots[0][1].y_range, (-500, 500))
        self.assertGreater(np.max(time_canvas.values), 190)
        fft = panel.plots[1][1]
        original = fft.y_range
        panel.scale_buttons[1]['+'].click()
        self.assertAlmostEqual(fft.y_range[1] - fft.y_range[0], (original[1] - original[0]) / 2)
        panel.scale_buttons[0]['−'].click()
        self.assertEqual(time_canvas.y_range, (-20, 80))
        panel.scale_buttons[0]['+'].click()
        panel.scale_buttons[0]['Restaurar'].click()
        panel.scale_buttons[1]['Restaurar'].click()
        self.assertEqual(time_canvas.y_range, (-20, 80))
        self.assertEqual(fft.y_range, original)


if __name__ == '__main__':
    unittest.main()
