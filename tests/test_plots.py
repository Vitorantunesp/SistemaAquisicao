import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
import time
import numpy as np
from PyQt6.QtWidgets import QApplication
from ads1800_app.config import ChannelConfig
from ads1800_app.ui.plots import DisplayBuffer, PlotDashboard, envelope_indices


class PlotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_time_window_at_24khz_is_not_limited_to_100000_points(self):
        buffer = DisplayBuffer(10)
        times = np.arange(288001) / 24000
        buffer.append(times, [times])
        t, values = buffer.snapshot()
        self.assertAlmostEqual(t[0], 2)
        self.assertAlmostEqual(t[-1] - t[0], 10)
        self.assertEqual(len(t), 240001)
        np.testing.assert_array_equal(values[0], t)
        buffer.seconds = .5
        buffer.trim()
        self.assertEqual(len(buffer.snapshot()[0]), 12001)

    def test_resize_maximize_and_close_preserve_live_plot(self):
        plot = PlotDashboard()
        plot.resize(1000, 700)
        plot.show()
        self.app.processEvents()
        plot.reset([ChannelConfig(0), ChannelConfig(1)])
        self.app.processEvents()
        window = plot.windows[0]
        window.resize(420, 320)
        self.app.processEvents()
        original = window.size()
        window.resize(520, 400)
        self.app.processEvents()
        self.assertGreater(window.width(), original.width())
        self.assertGreater(window.height(), original.height())
        enlarged = window.size()
        window.resize(480, 370)
        self.app.processEvents()
        self.assertLess(window.width(), enlarged.width())
        self.assertLess(window.height(), enlarged.height())
        resized = window.size()
        plot.append([0, 1], [[1, 2], [3, 4]])
        plot.refresh()
        self.assertEqual(window.size(), resized)
        window.showMaximized()
        self.assertTrue(window.isMaximized())
        window.showNormal()
        window.close()
        self.assertFalse(plot.channel_checks[0].isChecked())
        plot.append([2], [[5], [6]])
        plot.channel_checks[0].setChecked(True)
        self.assertEqual(plot.panels[0].canvas.values[-1], 5)
        plot.set_columns(1)
        self.assertEqual(plot.windows[1].x(), 0)
        plot.timer.stop()
        plot.close()

    def test_visibility_reflows_and_restores_latest_data_and_scale(self):
        plot = PlotDashboard()
        channels = [ChannelConfig(i) for i in range(3)]
        plot.reset(channels)
        first = plot.panels[0]
        first.minimum.setValue(-10)
        first.maximum.setValue(10)
        first.auto.setChecked(False)
        plot.append([0, 1], [[1, 2], [3, 4], [5, 6]])
        plot.channel_checks[0].setChecked(False)
        self.assertTrue(first.isHidden())
        self.assertEqual((plot.windows[1].x(), plot.windows[1].y()), (0, 0))
        plot.append([2, 3], [[7, 8], [9, 10], [11, 12]])
        plot.channel_checks[0].setChecked(True)
        self.assertFalse(first.isHidden())
        self.assertEqual(first.canvas.values[-1], 8)
        self.assertEqual(first.canvas.y_range, (-10, 10))
        for check in plot.channel_checks:
            check.setChecked(False)
        self.assertFalse(plot.placeholder.isHidden())
        self.assertEqual(plot.buffer.snapshot()[1].shape, (3, 4))
        plot.reset(channels)
        self.assertTrue(all(not check.isChecked() for check in plot.channel_checks))
        plot.timer.stop()
        plot.close()

    def test_timer_follows_latest_sample_without_manual_refresh(self):
        plot = PlotDashboard()
        plot.reset([ChannelConfig(0)])
        plot.set_window(2)
        plot.set_refresh_rate(30)
        plot.show()
        for timestamps in ([100, 100.5], [101, 101.5], [104, 104.5]):
            plot.append(timestamps, [[1, timestamps[-1]]])
            deadline = time.monotonic() + 2
            while plot.dirty and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(.005)
            self.assertFalse(plot.dirty)
            latest = timestamps[-1] - 100
            self.assertEqual(plot.panels[0].canvas.x_range, (latest - 2, latest))
            self.assertEqual(plot.panels[0].canvas.times[-1], latest)
            self.assertEqual(plot.panels[0].current_value.text(), f'{timestamps[-1]:g}'.replace('.', ',') + ' V')
        plot.timer.stop()
        plot.close()

    def test_reduction_preserves_positive_and_negative_narrow_peaks(self):
        values = np.zeros(100000)
        values[50123], values[50678] = 500, -800
        reduced = envelope_indices(values, 300)
        self.assertIn(50123, reduced)
        self.assertIn(50678, reduced)
        self.assertLess(len(reduced), 1000)

    def test_numeric_readouts_show_latest_calibrated_sample_units_and_invalid_data(self):
        plot = PlotDashboard()
        acceleration = ChannelConfig(0, unit='m/s²', gain=2, offset=1)
        force = ChannelConfig(1, unit='N')
        plot.reset([acceleration, force])
        self.assertEqual(plot.panels[0].current_value.text(), '—')
        plot.append([0, .1], [[acceleration.apply_calibration(100), acceleration.apply_calibration(-1.25)], [900, 12.5]])
        plot.refresh()
        self.assertEqual(plot.panels[0].current_value.text(), '-1,5 m/s²')
        self.assertEqual(plot.panels[1].current_value.text(), '12,5 N')
        self.assertIn('0,100 s', plot.panels[0].value_time.text())
        plot.panels[0].auto.setChecked(False)
        self.assertEqual(plot.panels[0].current_value.text(), '-1,5 m/s²')
        plot.set_channel_visible(1, False)
        plot.append([.2], [[float('nan')], [-42]])
        plot.refresh()
        self.assertEqual(plot.panels[0].current_value.text(), 'Inválido m/s²')
        plot.set_channel_visible(1, True)
        self.assertEqual(plot.panels[1].current_value.text(), '-42 N')
        plot.reset([acceleration, force])
        self.assertEqual(plot.panels[1].current_value.text(), '—')
        plot.timer.stop()
        plot.close()

    def test_independent_axes_manual_scale_and_reset(self):
        plot = PlotDashboard()
        plot.reset([ChannelConfig(0, name='Força', unit='N'), ChannelConfig(1, name='Tensão', unit='V')])
        plot.set_window(2)
        plot.set_refresh_rate(5)
        self.assertEqual(plot.timer.interval(), 200)
        plot.append([1700000000, 1700000001, 1700000002], [[100, 200, 300], [-.1, 0, .1]])
        plot.refresh()
        first, second = plot.panels
        self.assertGreater(first.canvas.y_range[1], 300)
        self.assertLess(second.canvas.y_range[1], 1)
        self.assertEqual(first.canvas.x_range, (0, 2))
        np.testing.assert_array_equal(second.canvas.times, [0, 1, 2])
        second.minimum.setValue(-10)
        second.maximum.setValue(10)
        second.auto.setChecked(False)
        plot.append([1700000003], [[900], [.2]])
        plot.refresh()
        self.assertEqual(second.canvas.y_range, (-10, 10))
        self.assertEqual(first.canvas.x_range, (1, 3))
        second.minimum.setValue(20)
        self.assertEqual(second.canvas.y_range, (-10, 10))
        self.assertIn('menor', second.message.text())
        plot.set_columns(1)
        self.assertGreater(plot.windows[1].y(), plot.windows[0].y())
        plot.reset([ChannelConfig(2)])
        self.assertEqual(len(plot.panels), 1)
        self.assertIsNone(plot.origin)
        self.assertFalse(plot.buffer.blocks)
        plot.timer.stop()
        plot.close()
