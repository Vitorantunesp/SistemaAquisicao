import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
from PyQt6.QtWidgets import QApplication, QDialog
from ads1800_app.backends.modal_simulator import ModalSimulatorBackend
from ads1800_app.modal import ModalConfig
from ads1800_app.ui.modal import ModalApp
from ads1800_app.ui.modal_setup import ModalSetupDialog


class FastModalBackend(ModalSimulatorBackend):
    def read(self):
        self._last_read = time.perf_counter()-.25
        return super().read()


class SetupUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait(self, condition, timeout=15):
        deadline = time.monotonic()+timeout
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertTrue(condition())

    def close_dialog(self, dialog):
        self.wait(lambda: not dialog.busy)
        dialog.reject()
        self.wait(lambda: not dialog.timer.isActive())

    def test_sidebar_configuration_pages_and_hardware_table(self):
        window = ModalApp()
        try:
            self.assertEqual(window.tabs.count(), 3)
            self.assertEqual([window.tabs.sidebar.item(i).text() for i in range(3)],
                             ['Configuração do ensaio', 'Monitor de impactos', 'Pós-processamento'])
            self.assertEqual(window.config_tabs.count(), 3)
            connection, geometry, parameters = [window.config_tabs.widget(i) for i in range(3)]
            self.assertTrue(connection.isAncestorOf(window.force_channel))
            self.assertTrue(connection.isAncestorOf(window.extra_sensors))
            self.assertTrue(geometry.isAncestorOf(window.ax))
            self.assertTrue(geometry.isAncestorOf(window.extra_sensors.position_table))
            self.assertTrue(parameters.isAncestorOf(window.fields['threshold']))
            window.connect_device()
            self.wait(lambda: not window.busy)
            self.assertEqual(window.channel_info.rowCount(), 8)
            self.assertEqual(window.channel_info.item(0, 1).text(), 'Martelo')
            self.assertEqual(window.channel_info.item(0, 3).text(), '-500')
            self.assertEqual(window.channel_info.item(0, 5).text(), 'Não informado')
            window.extra_sensors.set_sensors([dict(name='A2', channel=3, position=[.8, .2], factor=1)])
            self.assertTrue(window.extra_sensors.table.isColumnHidden(2))
            window.extra_sensors.position_table.cellWidget(0, 2).setValue(.73)
            self.assertEqual(window.read_config(True).additional_accelerometers[0]['position'], [.73, .2])
            window.tabs.setCurrentIndex(2)
            self.assertEqual(window.tabs.stack.currentIndex(), 2)
        finally:
            window.close()
            self.wait(lambda: window.backend is None)

    def test_assistant_can_replace_invalid_manual_bandpass_configuration(self):
        window = ModalApp()
        errors = []
        window.error = errors.append
        try:
            window.connect_device()
            self.wait(lambda: not window.busy)
            window.rate.setCurrentText('1000')
            with patch('ads1800_app.ui.modal.ModalSetupDialog') as dialog:
                dialog.return_value.exec.return_value = QDialog.DialogCode.Rejected
                window.configure_by_impacts()
                self.assertTrue(dialog.called)
                dialog.call_args.args[1].validate()
            self.assertFalse(errors, errors)
        finally:
            window.close()
            self.wait(lambda: window.backend is None)

    def test_raw_hammer_live_and_lower_plots_wait_for_first_complete_hit(self):
        class QuietBackend(FastModalBackend):
            def read(self):
                self.impacts_enabled = False
                return super().read()
        backend = QuietBackend()
        info = backend.connect('')
        c = ModalConfig(force_limits=(-500, 500), additional_accelerometers=[
            dict(name='A2', channel=3, position=[.8, .25], factor=2, limits=(-200, 200))])
        dialog = ModalSetupDialog(backend, c, info.channels, info.available_sample_rates)
        try:
            dialog.show()
            self.wait(lambda: dialog.phase == 'first' and len(dialog.plots['raw_force'].values) > 0)
            self.assertFalse(dialog.study.pilots)
            self.assertGreater(len(dialog.plots['raw_force'].values), 16)
            self.assertEqual(len(dialog.plots['force'].values), 0)
            self.assertEqual(len(dialog.plots['acceleration_psd'].values), 0)
            self.assertTrue(dialog.property_panel.isAncestorOf(dialog.fmin))
            self.assertTrue(dialog.property_panel.isAncestorOf(dialog.force_window))
            self.assertEqual(dialog.property_panel.horizontalScrollBar().maximum(), 0)
            self.assertLess(max(abs(v) for v in dialog.plots['raw_force'].y_range), 1)
            self.assertAlmostEqual(dialog.stream_config.threshold, .10*500, delta=.02)
            dialog.sensor.setCurrentIndex(1)
            self.wait(lambda: dialog.phase == 'changed')
            dialog.redraw()
            self.assertFalse(dialog.apply_button.isEnabled())
        finally:
            self.close_dialog(dialog)
            backend.disconnect()

    def test_startup_read_failure_stops_without_measuring_false_noise(self):
        class BrokenBackend(FastModalBackend):
            def read(self):
                raise RuntimeError('Falha simulada na comunicação')
        backend = BrokenBackend()
        info = backend.connect('')
        dialog = ModalSetupDialog(backend, ModalConfig(), info.channels, info.available_sample_rates)
        try:
            self.wait(lambda: not dialog.busy and 'Falha simulada' in dialog.status.text())
            self.assertFalse(dialog.controller.running)
            self.assertIsNone(dialog.study.noise)
            self.assertFalse(dialog.apply_button.isEnabled())
        finally:
            self.close_dialog(dialog)
            backend.disconnect()

    def test_automatic_two_hit_flow_and_saved_session(self):
        with patch('ads1800_app.ui.modal.ModalSimulatorBackend', FastModalBackend):
            window = ModalApp()
            errors = []
            window.error = errors.append
            dialog = None
            try:
                window.connect_device()
                self.wait(lambda: not window.busy)
                dialog = ModalSetupDialog(window.backend, window.read_config(True, for_setup=True), window.channels,
                    [float(window.rate.itemText(i)) for i in range(window.rate.count())], window)
                dialog.show()
                self.wait(lambda: dialog.study and dialog.study.validated and not dialog.busy and dialog.phase == 'monitor')
                self.assertEqual(len(dialog.study.pilots), 1)
                self.assertEqual(dialog.study.required_hits, 4)
                self.assertEqual(len(dialog.study.series), 4)
                self.assertGreaterEqual(len(dialog.study.confirmations), 3)
                self.assertEqual(dialog.results.rowCount(), len(dialog.study.confirmations)+3)
                self.assertTrue(dialog.apply_button.isEnabled(), dialog.status.text())
                self.assertTrue(dialog.study.coherence_result['summary']['passed'])
                rec = dialog.study.recommendation
                self.assertAlmostEqual(rec.config.threshold, .5*min(h['metrics']['peak_N'] for h in dialog.study.series))
                self.assertEqual(rec.config.sample_rate, 2000)
                self.assertLess(rec.config.duration, 8)
                dialog.redraw()
                self.assertTrue(np.all(dialog.plots['force_psd'].values >= 0))
                self.assertEqual(dialog.view.currentIndex(), 0)
                last_force = dialog.plots['force'].values.copy()
                previous_time = dialog.last_time
                self.wait(lambda: dialog.last_time is not None and dialog.last_time != previous_time)
                dialog.redraw()
                np.testing.assert_equal(dialog.plots['force'].values, last_force)
                self.assertGreater(len(dialog.plots['raw_force'].values), 0)
                dialog.response_function.setCurrentIndex(1)
                dialog.redraw()
                curve = dialog.plots['acceleration_psd'].values.copy()
                finite = curve[np.isfinite(curve)]
                self.assertGreater(len(finite), 8)
                self.assertTrue(np.all((finite >= 0) & (finite <= 1)))
                self.assertEqual(dialog.plots['acceleration_psd'].y_range, (0, 1.05))
                dialog.psd_mode.setCurrentIndex(1)
                dialog.redraw()
                np.testing.assert_allclose(dialog.plots['acceleration_psd'].values, curve, equal_nan=True)
                original = dialog.study.pilots[0]['data'].copy()
                dialog.response_window.setCurrentText('Exponencial')
                dialog.redraw()
                from ads1800_app.modal import windows
                wf, wa = windows(dialog.study.recommendation.config)
                np.testing.assert_allclose(dialog.plots['force'].window_weights, wf)
                np.testing.assert_allclose(dialog.plots['acceleration'].window_weights, wa)
                self.assertEqual(len(dialog.plots['raw_force'].window_weights), 0)
                np.testing.assert_equal(original, dialog.study.pilots[0]['data'])
                expo_preview = os.environ.get('MODAL_SETUP_PREVIEW_DIR')
                if expo_preview:
                    Path(expo_preview).mkdir(parents=True, exist_ok=True)
                    self.app.processEvents()
                    dialog.grab().save(str(Path(expo_preview)/'janelas_exponenciais.png'))
                dialog.response_window.setCurrentText('Retangular')
                dialog.redraw()
                self.assertEqual(len(dialog.plots['acceleration'].window_weights), 0)
                self.assertTrue(dialog.study.validated, dialog.quality_label.text())
                self.assertGreater(len(dialog.plots['force'].window_weights), 0)
                correct_width = dialog.force_width.value()
                dialog.force_width.setValue(60)
                self.assertTrue(dialog.window_error)
                self.assertFalse(dialog.apply_button.isEnabled())
                dialog.coherence_threshold.setValue(.89)
                self.assertFalse(dialog.apply_button.isEnabled())
                dialog.force_width.setValue(correct_width)
                self.assertFalse(dialog.window_error)
                self.assertTrue(dialog.study.validated)
                dialog.coherence_threshold.setValue(.9)
                dialog.psd_mode.setCurrentIndex(0)
                preview = os.environ.get('MODAL_SETUP_PREVIEW_DIR')
                if preview:
                    Path(preview).mkdir(parents=True, exist_ok=True)
                    self.app.processEvents()
                    dialog.grab().save(str(Path(preview)/'duas_batidas.png'))
                    dialog.response_function.setCurrentIndex(0)
                    self.app.processEvents()
                    dialog.grab().save(str(Path(preview)/'psd_ultima_batida.png'))
                    window.show()
                    for tab, name in [(0, 'conexao'), (1, 'geometria'), (2, 'parametros')]:
                        window.config_tabs.setCurrentIndex(tab)
                        self.app.processEvents()
                        window.grab().save(str(Path(preview)/f'{name}.png'))
                dialog.accept()
                self.wait(lambda: not dialog.timer.isActive())
                with patch('ads1800_app.ui.modal.ModalSetupDialog', return_value=dialog), \
                     patch.object(dialog, 'exec', return_value=QDialog.DialogCode.Accepted):
                    window.configure_by_impacts()
                c = window.read_config(True)
                self.assertTrue(window.setup_study.matches(c))
                # Geometry and target averages may change after applying the assistant.
                window.averages.setValue(5)
                window.points.setPlainText('P1; 0.1; 0.25\nP2; 0.5; 0.25\nP3; 0.9; 0.25\nP4; 0.7; 0.3')
                c = window.read_config(True)
                self.assertEqual((c.averages, len(c.points)), (5, 4))
                self.assertEqual(c.threshold, dialog.study.recommendation.config.threshold)
                self.assertFalse(window.setup_study.matches(c))
                from ads1800_app.ui.modal import SETUP_KEYS
                self.assertTrue(window.setup_study.matches(c, SETUP_KEYS))
                window.automatic.setChecked(False)
                with tempfile.TemporaryDirectory() as folder:
                    with patch('ads1800_app.ui.modal.QFileDialog.getExistingDirectory', return_value=folder):
                        window.start()
                    self.wait(lambda: not window.busy)
                    self.assertFalse(errors, errors)
                    session = window.session
                    manifest = json.loads((session.directory/'session.json').read_text(encoding='utf-8'))
                    self.assertTrue(manifest['acquisition']['modal_setup']['validated'])
                    self.assertEqual(manifest['acquisition']['modal_setup']['recommendation']['metrics']['strategy'], 'multiple_hits')
                    self.assertEqual(len(list((session.directory/'configuracao').glob('exploracao_*.npz'))), 1)
                    self.assertEqual(len(list((session.directory/'configuracao').glob('confirmacao_*.npz'))),
                                     len(dialog.study.confirmations))
                    self.assertTrue((session.directory/'configuracao/coerencia.npz').exists())
                    self.assertEqual(len(session.records), 0)
                    window.stop()
                    self.wait(lambda: not window.busy)
            finally:
                if dialog and dialog.timer.isActive():
                    self.close_dialog(dialog)
                window.close()
                self.wait(lambda: window.backend is None)


if __name__ == '__main__':
    unittest.main()
