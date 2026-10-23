import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
import tempfile
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from scipy.signal import periodogram
from ads1800_app.modal import ModalConfig, acceleration_psd, windows
from ads1800_app.modal_post import ModalData, PostSettings, export_results
from ads1800_app.modal_ema import identify_ema, reconstruct_ema, modal_shapes


def mimo_data():
    freq = np.arange(0, 150.25, .25)
    s = 2+2j*np.pi*freq
    inputs = np.array([[1, .3, -.7], [-.4, 1, .5]])
    outputs = np.array([[1, 0], [0, 1]])  # Each sensor is blind to a different mode.
    h = np.zeros((2, 3, len(freq)), complex)
    for k, (fn, zeta) in enumerate([(40, .012), (85, .025)]):
        w = 2*np.pi*fn
        h += np.outer(outputs[k], inputs[k])[:, :, None]*s*s/(s*s+2*zeta*w*s+w*w)
    pairs = [(a, p) for a in ['A1', 'A2'] for p in ['P1', 'P2', 'P3']]
    return ModalData(freq, h.reshape(6, -1), np.full((6, len(freq)), .99),
                     [f'{a} ← {p}' for a, p in pairs], [3]*6, 2, [], [], pairs)


class MimoTests(unittest.TestCase):
    def test_ui_mimo_disables_single_reference_and_uses_shared_engine(self):
        from PyQt6.QtWidgets import QApplication
        from ads1800_app.ui.modal import ModalApp
        app = QApplication.instance() or QApplication([])
        window = ModalApp()
        try:
            c = ModalConfig(additional_accelerometers=[dict(name='A2', channel=2, position=[.8, .25], factor=1)])
            window.post.set_session(SimpleNamespace(config=c))
            post = window.post
            post.reference.setCurrentIndex(1)
            self.assertEqual(post.view.config.accelerometer, [.8, .25])
            post.identification.setCurrentIndex(1)
            self.assertFalse(post.reference.isEnabled())
            self.assertFalse(post.engine.isEnabled())
            self.assertEqual(post.engine.currentIndex(), 0)
            self.assertEqual(len(post.view.config.sensors), 2)
            self.assertIn('PSD', window.plot_labels['fft_acceleration'].text())
            post.identification.setCurrentIndex(0)
            self.assertTrue(post.reference.isEnabled())
            self.assertEqual(post.reference.currentIndex(), 1)
        finally:
            window.close()
            app.processEvents()

    def test_joint_poles_blind_references_shapes_and_manual_reconstruction(self):
        data = mimo_data()
        result = identify_ema(data, PostSettings(fmin=20, fmax=115, max_modes=2), [40, 85], order=12)
        self.assertEqual(result['identification'], 'MIMO')
        self.assertEqual(result['measured'].shape[0], 6)
        np.testing.assert_allclose([m['frequency_hz'] for m in result['modes']], [40, 85], atol=.02)
        np.testing.assert_allclose([m['damping_ratio'] for m in result['modes']], [.012, .025], atol=.0001)
        np.testing.assert_allclose([list(m['shape'].values()) for m in result['modes']], [[1, .3, -.7], [-.4, 1, .5]], atol=.01)
        self.assertLess(max(result['relative_fit_error'].values()), .01)
        self.assertLess(max(m['residue_rank_one_error'] for m in result['modes']), .01)
        selected = reconstruct_ema(result['_ema_context'], result['selected_poles'])
        self.assertEqual(selected['frf_pairs'], result['frf_pairs'])
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)/'mimo'
            export_results(selected, folder)
            saved = json.loads((folder/'modos.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['identification'], 'MIMO')
            self.assertEqual(len(saved['frf_pairs']), 6)
            self.assertTrue((folder/'formas_acelerometros.csv').exists())
            self.assertIn('P3', (folder/'formas_modais.csv').read_text(encoding='utf-8-sig'))

    def test_complex_residue_factorization_and_incomplete_matrix(self):
        data = mimo_data()
        left = np.array([1, .5j])
        right = np.array([1, .3+.2j, -.7])
        result = modal_shapes(np.outer(left, right).ravel(), data, list(range(6)))
        np.testing.assert_allclose([result['shape'][p]+1j*result['shape_imag'][p] for p in ['P1', 'P2', 'P3']], right)
        self.assertLess(result['residue_rank_one_error'], 1e-12)
        with self.assertRaisesRegex(ValueError, 'incompleta'):
            modal_shapes(np.ones(5), data, list(range(5)))

    def test_psd_matches_scipy_for_even_odd_and_all_windows(self):
        rng = np.random.default_rng(27)
        for n in [300, 301]:
            for window_name in ['Retangular', 'Hann', 'Exponencial']:
                c = ModalConfig(sample_rate=1000, bandpass_enabled=False, duration=n/1000, response_window=window_name)
                _, window = windows(c)
                signal = rng.normal(size=n)
                _, expected = periodogram(signal, fs=1000, window=window, detrend=False, scaling='density')
                actual = acceleration_psd(c, np.fft.rfft(signal*window))
                np.testing.assert_allclose(actual, expected, atol=1e-14)
