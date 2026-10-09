import tempfile
from pathlib import Path
import json
import unittest
import numpy as np

from ads1800_app.modal_ema import identify_ema, reconstruct_ema
from ads1800_app.modal_post import PostSettings, StabilitySettings, classify_stability, export_results
from test_modal_post import analytic_data


class EmaTests(unittest.TestCase):
    def test_library_recovers_complex_modes_and_corrects_exponential(self):
        for alpha in [0, 4]:
            data = analytic_data(alpha=alpha, noise=.0001)
            result = identify_ema(data, PostSettings(fmin=20, fmax=115, max_modes=2), [40, 85], order=16)
            self.assertEqual(result['library']['name'], 'sdypy-EMA')
            np.testing.assert_allclose([m['frequency_hz'] for m in result['modes']], [40, 85], atol=.02)
            np.testing.assert_allclose([m['damping_ratio'] for m in result['modes']], [.012, .025], atol=.0001)
            self.assertLess(max(result['relative_fit_error'].values()), .005)
            np.testing.assert_allclose([list(m['shape'].values()) for m in result['modes']],
                                       [[1, 1/3, -2/3], [-.5, 1, -.75]], atol=.01)
            np.testing.assert_allclose(np.diag(result['auto_mac']), 1)
            stable = [m for row in result['stabilization']['orders'] for m in row['modes'] if m['stability'] == 'estavel']
            self.assertTrue(any(abs(m['frequency_hz']-40) < .1 for m in stable))
            self.assertTrue(any(abs(m['frequency_hz']-85) < .1 for m in stable))

    def test_manual_selection_export_and_rejected_duplicate(self):
        result = identify_ema(analytic_data(), PostSettings(fmin=20, fmax=115, max_modes=2), order=12)
        self.assertEqual(len(result['modes']), 2)
        one = reconstruct_ema(result['_ema_context'], result['selected_poles'][:1])
        self.assertEqual(len(one['modes']), 1)
        with self.assertRaises(ValueError):
            reconstruct_ema(result['_ema_context'], [result['selected_poles'][0]]*2)
        with self.assertRaises(ValueError):
            reconstruct_ema(result['_ema_context'], [[999, 999]])
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)/'result'
            export_results(result, folder)
            saved = json.loads((folder/'modos.json').read_text(encoding='utf-8'))
            self.assertNotIn('_ema_context', saved)
            self.assertIn('stabilization', saved)
            self.assertTrue((folder/'estabilizacao.csv').exists())

    def test_no_stable_candidate_returns_diagram_for_manual_review(self):
        settings = PostSettings(fmin=20, fmax=115, prominence_db=100)
        result = identify_ema(analytic_data(), settings, order=8)
        self.assertEqual(result['modes'], [])
        self.assertEqual(len(result['stabilization']['orders']), 8)
        self.assertTrue(all(v is None for v in result['relative_fit_error'].values()))

    def test_missing_data_and_incompatible_order_are_explained(self):
        data = analytic_data()
        data.frfs[:, 200:220] = np.nan
        with self.assertRaisesRegex(ValueError, 'Nenhuma FRF'):
            identify_ema(data, PostSettings(fmin=20, fmax=115), order=8)
        with self.assertRaises(ValueError):
            identify_ema(analytic_data(), PostSettings(fmin=40, fmax=41), order=60)

    def test_stability_matching_is_one_to_one_and_mac_is_sign_invariant(self):
        old = {'frequency_hz': 40., 'damping_ratio': .02, 'shape': {'P1': 1, 'P2': -1}, 'shape_imag': {'P1': .2, 'P2': -.2}}
        current = dict(old, frequency_hz=40.1, shape={'P1': -1, 'P2': 1}, shape_imag={'P1': -.2, 'P2': .2})
        result = classify_stability([current, dict(current, frequency_hz=40.2)], [old], StabilitySettings())
        self.assertEqual([m['stability'] for m in result], ['estavel', 'novo'])
        current['shape'] = {'P1': 1}
        old['shape'] = {'P1': 1}
        self.assertEqual(classify_stability([current], [old], StabilitySettings())[0]['stability'], 'frequencia_amortecimento')
