import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from PyQt6.QtWidgets import QApplication
from ads1800_app.config import ChannelConfig
from ads1800_app.modal import ModalConfig
from ads1800_app.ui.modal_sensors import SensorTable


class SensorSelectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_selection_uses_hardware_identity_and_preserves_on_reconnect(self):
        widget = SensorTable()
        channels = [ChannelConfig(3, name='Ponta', unit='g'), ChannelConfig(6, name='Centro', unit='m/s²')]
        widget.set_channels(channels)
        widget.add_sensor()
        with self.assertRaises(ValueError):
            widget.sensors()
        combo = widget.table.cellWidget(0, 1)
        combo.setCurrentIndex(combo.findData(6))
        self.assertEqual(widget.sensors()[0]['channel'], 6)
        widget.set_channels(channels[::-1])
        self.assertEqual(combo.currentData(), 6)
        widget.set_channels(channels[:1])
        self.assertIn('indisponível', combo.currentText())
        with self.assertRaises(ValueError):
            widget.sensors()
        widget.set_channels(channels)
        self.assertEqual(widget.sensors()[0]['channel'], 6)
        widget.deleteLater()

    def test_saved_configuration_roundtrip_duplicate_validation_and_remove(self):
        widget = SensorTable()
        widget.set_channels([ChannelConfig(i) for i in range(4)])
        sensor = dict(name='A2', channel=3, position=[.8, -.25], factor=9.80665, limits=None)
        widget.set_sensors([sensor])
        self.assertEqual(widget.sensors(), [sensor])
        widget.add_sensor()
        self.assertEqual(widget.table.cellWidget(1, 0).text(), 'A3')
        combo = widget.table.cellWidget(1, 1)
        combo.setCurrentIndex(combo.findData(3))
        with self.assertRaises(ValueError):
            ModalConfig(additional_accelerometers=widget.sensors()).validate()
        widget.table.removeRow(1)
        ModalConfig(additional_accelerometers=widget.sensors()).validate()
        widget.deleteLater()
