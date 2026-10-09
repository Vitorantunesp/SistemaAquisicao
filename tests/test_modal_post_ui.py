import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import time
import unittest
import numpy as np
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication
from ads1800_app.ui.modal import ModalApp
from test_modal_post import raw_session


class PostUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait(self, predicate):
        deadline = time.monotonic()+10
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertTrue(predicate())

    def test_saved_session_fit_display_animation_export_and_invalidation(self):
        with tempfile.TemporaryDirectory() as folder:
            session = raw_session(folder)
            window = ModalApp()
            errors = []
            window.error = errors.append
            window.show()
            try:
                with patch('ads1800_app.ui.modal.QFileDialog.getExistingDirectory', return_value=str(session.directory)):
                    window.open_session()
                self.assertEqual(window.tabs.count(), 3)
                window.tabs.setCurrentIndex(2)
                post = window.post
                post.fields['fmin'].setValue(20)
                post.fields['fmax'].setValue(115)
                post.fields['max_modes'].setValue(2)
                post.compute()
                self.wait(lambda: not window.busy)
                self.assertFalse(errors, errors)
                self.assertEqual(post.table.rowCount(), 2)
                self.assertEqual(post.result['library']['name'], 'sdypy-EMA')
                self.assertEqual(len(post.stability_canvas.result['stabilization']['orders']), 20)
                self.assertEqual(len(window.plots['frf'].frequency_markers), 2)
                self.assertEqual(len(post.comparison.frequency_markers), 2)
                self.assertTrue(post.export.isEnabled())
                original_result = post.result
                for mode in range(3):
                    post.frf_view.setCurrentIndex(mode)
                    window.frf_view.setCurrentIndex(mode)
                    frequency = post.result['frequency']
                    visible = (frequency >= 20) & (frequency <= 115)
                    measured = post.result['measured'][0, visible]
                    fitted = post.result['fitted'][0, visible]
                    np.testing.assert_allclose(post.comparison.values, abs(measured) if mode == 0 else measured.real)
                    np.testing.assert_allclose(post.comparison_secondary.values,
                                               measured.imag if mode == 2 else np.angle(measured, deg=True))
                    np.testing.assert_allclose(post.comparison_secondary.model,
                                               fitted.imag if mode == 2 else np.angle(fitted, deg=True))
                    from ads1800_app.modal import ensemble
                    _, h, _ = ensemble(session.config, session.hits(window.point.currentText()))
                    np.testing.assert_allclose(window.plots['frf'].values, abs(h) if mode == 0 else h.real)
                    np.testing.assert_allclose(window.plots['phase'].values,
                                               h.imag if mode == 2 else np.angle(h, deg=True))
                    if mode < 2:
                        self.assertEqual(post.comparison_secondary.y_range, (-180, 180))
                    self.assertIs(post.result, original_result)
                    self.assertEqual(len(post.comparison_secondary.frequency_markers), 2)
                post.frf_view.setCurrentIndex(0)
                window.frf_view.setCurrentIndex(0)
                post.select_mode(1)
                self.assertLess(post.view.shape['P1'], 0)
                self.assertGreater(post.view.shape['P2'], 0)
                phase = post.view.phase
                post.view.tick()
                self.assertNotEqual(post.view.phase, phase)
                post.toggle_animation()
                self.assertFalse(post.view.playing)
                post.point.setCurrentIndex(1)
                self.assertGreater(len(post.comparison.model), 10)
                post.save()
                self.assertEqual(len(list(session.directory.glob('pos_processamento_*/modos.json'))), 1)
                # Review from the original acquisition tab invalidates the fit.
                window.inspect(0)
                window.review(False)
                self.assertIsNone(post.result)
                self.assertEqual(window.plots['frf'].frequency_markers, [])
                self.assertIsNone(post.stability_canvas.result)
                self.assertFalse(post.export.isEnabled())
                post.fields['min_hits'].setValue(100)
                post.compute()
                self.wait(lambda: not window.busy)
                self.assertEqual(len(errors), 1)
                self.assertIn('não concluído', post.summary.text())
                self.assertFalse(post.export.isEnabled())
            finally:
                window.close()
