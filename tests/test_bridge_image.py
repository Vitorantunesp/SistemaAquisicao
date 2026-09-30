import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QImage, QFontDatabase
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QDialogButtonBox

from ads1800_app.config import ChannelConfig
from ads1800_app.monitor_signal import MonitorConfig
from ads1800_app.ui.bridge import BridgeApp
from ads1800_app.ui.bridge_image import (BridgeMap, DEFAULT_IMAGE, PROJECT_ROOT, import_image,
                                        resolve_image, save_preferences, load_pixmap)


class BridgeImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')

    def test_default_asset_has_actual_transparency(self):
        image = QImage(str(resolve_image(DEFAULT_IMAGE)))
        self.assertFalse(image.isNull())
        self.assertTrue(image.hasAlphaChannel())
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
        opaque = sum(image.pixelColor(x, y).alpha() > 200
                     for x in range(0, image.width(), 20) for y in range(0, image.height(), 20))
        self.assertGreater(opaque, 100)

    def test_drag_resize_and_channel_identity(self):
        widget = BridgeMap(editable=True)
        widget.set_image(DEFAULT_IMAGE)
        widget.channels = [ChannelConfig(0), ChannelConfig(4)]
        widget.resize(1000, 550)
        widget.show()
        self.app.processEvents()
        start = widget.marker_position(4).toPoint()
        rect = widget.image_rect()
        finish = QPointF(rect.left() + .72 * rect.width(), rect.top() + .65 * rect.height()).toPoint()
        QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(widget, finish)
        QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=finish)
        self.assertAlmostEqual(widget.positions['4'][0], .72, delta=.003)
        saved = dict(widget.positions)
        widget.resize(600, 600)
        widget.channels = [ChannelConfig(4)]
        self.app.processEvents()
        rect = widget.image_rect()
        point = widget.marker_position(4)
        self.assertAlmostEqual((point.x() - rect.left()) / rect.width(), saved['4'][0])
        widget.editable = False
        QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=point.toPoint())
        QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=finish)
        self.assertEqual(widget.positions, saved)
        widget.close()

    def test_import_copy_and_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = root / 'original.png'
            image = QImage(100, 80, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            image.save(str(original))
            with patch('ads1800_app.ui.bridge_image.PROJECT_ROOT', root):
                imported = import_image(original)
                self.assertEqual((root / imported).read_bytes(), original.read_bytes())
                self.assertFalse(load_pixmap(imported).isNull())
                invalid = root / 'invalid.png'
                invalid.write_text('invalid')
                with self.assertRaises(ValueError):
                    import_image(invalid)
            config = MonitorConfig(bridge_image=imported, sensor_positions={'4': [.3, .6]})
            config.save(root / 'experiment.json')
            self.assertEqual(MonitorConfig.load(root / 'experiment.json'), config)
            config.sensor_positions = {'4': [float('nan'), .5]}
            with self.assertRaises(ValueError):
                config.validate()

    def test_preferences_reopen_editor_save_and_cancel(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            # App preference path is isolated from user settings; default assets remain real.
            with patch('ads1800_app.ui.bridge.PROJECT_ROOT', root):
                window = BridgeApp()
                channels = [ChannelConfig(0, enabled=True, engineering_min=-1, engineering_max=1)]
                window._show_device_channels(channels)
                window.show()
                self.app.processEvents()
                def cancel(dialog):
                    editor = dialog.findChild(BridgeMap)
                    editor.set_positions({'0': [.8, .2]})
                    return 0
                with patch.object(QDialog, 'exec', cancel):
                    window._edit_sensor_positions()
                self.assertEqual(window._sensor_positions, {})
                def accept(dialog):
                    editor = dialog.findChild(BridgeMap)
                    editor.set_positions({'0': [.3, .6]})
                    dialog.show()
                    self.app.processEvents()
                    dialog.findChild(QDialogButtonBox).accepted.emit()
                    return 1
                with patch.object(QDialog, 'exec', accept):
                    window._edit_sensor_positions()
                self.assertEqual(window._sensor_positions, {'0': [.3, .6]})
                window.tabs.setCurrentWidget(window.acquisition_tab)
                self.app.processEvents()
                window.tabs.setCurrentWidget(window.channels_tab)
                self.app.processEvents()
                window.close()
                reopened = BridgeApp()
                self.assertEqual(reopened._sensor_positions, {'0': [.3, .6]})
                self.assertFalse(reopened.bridge_map.pixmap.isNull())
                reopened.close()
