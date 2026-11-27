import unittest

import numpy as np

from ads1800_app.frf_phase import excitation_mask, reliable_bins, unwrap_deg, wrap_breaks
from ads1800_app.ui.frf_view import FRF_VIEWS, frf_components


class FrfPhaseTest(unittest.TestCase):
    def test_noise_near_180_degrees_is_not_a_jump_when_unwrapped(self):
        rng = np.random.default_rng(0)
        h = -np.exp(1j*np.radians(rng.normal(0, 3, 400)))  # true phase ±180°
        wrapped = np.angle(h, deg=True)
        self.assertGreater(len(wrap_breaks(wrapped)), 20)
        phase = unwrap_deg(h)
        self.assertEqual(len(wrap_breaks(phase)), 0)
        self.assertLess(np.ptp(phase), 40)

    def test_unwrap_follows_several_modes_and_skips_masked_bins(self):
        true = np.linspace(0, -700, 500)
        h = np.exp(1j*np.radians(true))
        keep = np.ones(500, bool)
        keep[200:210] = False
        phase = unwrap_deg(h, keep)
        self.assertTrue(np.isnan(phase[200:210]).all())
        np.testing.assert_allclose(phase[keep], true[keep], atol=1e-9)

    def test_principal_range_and_first_value(self):
        h = np.exp(1j*np.radians(np.linspace(170, 900, 50)))
        self.assertTrue(-180 < unwrap_deg(h)[0] <= 180)

    def test_excitation_and_coherence_masks(self):
        force = np.array([1, 1, .5, .005, np.nan, 1])
        np.testing.assert_array_equal(excitation_mask(force, 20), [1, 1, 1, 0, 0, 1])
        h = np.ones(6, complex)
        coherence = np.array([.9, .7, .95, .99, .99, np.nan])
        np.testing.assert_array_equal(reliable_bins(h, coherence, .8, excitation_mask(force)), [1, 0, 1, 0, 0, 0])
        # Fewer than two hits: coherence is all NaN and must not hide every bin.
        self.assertTrue(reliable_bins(h, np.full(6, np.nan)).all())

    def test_views_keep_previous_indices(self):
        self.assertEqual(FRF_VIEWS[:3], ['Magnitude + Fase', 'Parte real + Fase', 'Parte real + Parte imaginária'])
        h = np.exp(1j*np.radians(np.linspace(0, -400, 100)))
        _, (wrapped, _, fixed) = frf_components(h, 0)
        _, (unwrapped, label, free) = frf_components(h, 3)
        self.assertEqual(fixed, (-180, 180))
        self.assertIsNone(free)
        self.assertIn('desdobrada', label)
        self.assertAlmostEqual(unwrapped[-1], -400)
        _, (shifted, _, _) = frf_components(h, 3, reference=unwrapped+360)
        np.testing.assert_allclose(shifted, unwrapped+360)


if __name__ == '__main__':
    unittest.main()
