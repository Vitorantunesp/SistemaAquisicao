import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication
from ads1800_app.config import ExperimentConfig
from ads1800_app.sensors import SensorProfile, load_catalog, save_catalog
from ads1800_app.ui.sensors import SensorCatalogDialog, SensorEditor
from ads1800_app.ui.app import Ads1800App
from ads1800_app.controller import AcquisitionController


class SensorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def profile(self):
        return SensorProfile(name='Acelerômetro A', model='Modelo teste', serial_number='123',
                             input_type='IEPE / CCP', input_scale='±10 V',
                             sensitivity='100', sensitivity_unit='mV/g', unit='g', gain=10,
                             parameters={'Massa': '5 g', 'Faixa': '±50 g'})

    def test_catalog_roundtrip_and_validation_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'catalog.json'
            profile = self.profile()
            save_catalog(path, [profile])
            self.assertEqual(load_catalog(path), [profile])
            original = path.read_bytes()
            profile.gain = float('nan')
            with self.assertRaises(ValueError):
                save_catalog(path, [profile])
            self.assertEqual(path.read_bytes(), original)

    def test_editor_custom_fields_and_sensitivity_calculation(self):
        editor = SensorEditor(self.profile())
        editor._add_row('Data calibração', '2026-09-24')
        with patch('ads1800_app.ui.sensors.QInputDialog.getItem', return_value=('V', True)):
            editor._calculate_gain()
        result = editor.read_profile()
        self.assertEqual(result.gain, 10)
        self.assertEqual(result.parameters['Data calibração'], '2026-09-24')
        editor.fields['sensor_type'].setCurrentText('Martelo de impacto')
        editor.fields['sensitivity'].setText('2,5')
        editor.fields['sensitivity_unit'].setText('mV/N')
        editor.fields['unit'].setText('N')
        with patch('ads1800_app.ui.sensors.QInputDialog.getItem', return_value=('V', True)):
            editor._calculate_gain()
        self.assertEqual(editor.read_profile().gain, 400)
        with patch('ads1800_app.ui.sensors.QInputDialog.getItem', return_value=('mV', True)):
            editor._calculate_gain()
        self.assertEqual(editor.read_profile().gain, .4)
        editor._add_row('Massa', 'duplicado')
        with self.assertRaisesRegex(ValueError, 'único'):
            editor.read_profile()
        editor.close()

    def test_duplicate_sensor_gets_new_id_and_is_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sensors.json'
            save_catalog(path, [self.profile()])
            dialog = SensorCatalogDialog(path=path)
            dialog._duplicate()
            profiles = load_catalog(path)
            self.assertEqual(len(profiles), 2)
            self.assertNotEqual(profiles[0].id, profiles[1].id)
            self.assertEqual(profiles[0].parameters, profiles[1].parameters)
            dialog.close()

    def test_import_adds_profiles_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            source, dest = Path(directory) / 'source.json', Path(directory) / 'dest.json'
            save_catalog(source, [self.profile()])
            save_catalog(dest, load_catalog(source))
            dialog = SensorCatalogDialog(path=dest)
            with patch('ads1800_app.ui.sensors.QFileDialog.getOpenFileName', return_value=(str(source), '')):
                dialog._import()
            profiles = load_catalog(dest)
            self.assertEqual(len(profiles), 2)
            self.assertNotEqual(profiles[0].id, profiles[1].id)
            dialog.close()
