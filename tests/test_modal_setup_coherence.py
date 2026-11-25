import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from ads1800_app.modal_coherence import assess_setup_coherence, project_setup_record, spectrum_density
from test_modal_two_hits import first_study, confirm
from test_modal_setup import mechanical_record


class SetupCoherenceTests(unittest.TestCase):
    def test_single_hit_is_unavailable_not_unity(self):
        study = first_study()
        result = study.coherence_result
        self.assertEqual(result['summary']['hit_count'], 1)
        self.assertFalse(result['summary']['passed'])
        self.assertIsNone(result['summary']['median'])
        self.assertTrue(np.isnan(result['coherence']).all())
        self.assertFalse(study.validated)

    def test_common_rate_trigger_and_block_for_independent_hits(self):
        study = first_study()
        confirm(study)
        result, c = study.coherence_result, study.recommendation.config
        self.assertTrue(result['summary']['passed'], result['summary'])
        self.assertEqual(result['summary']['hit_count'], 2)
        self.assertGreater(result['summary']['fraction_above'], .8)
        self.assertNotEqual(study.pilots[0]['config']['sample_rate'], c.sample_rate)
        for record in [study.pilots[0], study.confirmations[-1]]:
            projected = project_setup_record(record, c)
            self.assertEqual(projected.shape, (c.n, 3))
        curve = result['coherence'][result['usable']]
        self.assertTrue(np.all((curve >= 0) & (curve <= 1)))

    def test_inverted_response_fails_coherence_while_peak_and_decay_are_consistent(self):
        study = first_study()
        confirm(study)
        c = study.confirmation_config()
        data = mechanical_record(c)
        data[:, 2] = .04-data[:, 2]
        record = study.add_confirmation('P1', data, c)
        self.assertFalse(record['base_issues'], record['base_issues'])
        self.assertFalse(study.coherence_result['summary']['passed'])
        self.assertFalse(study.validated)
        self.assertFalse(record['accepted'])
        self.assertTrue(any('Coerência' in text for text in record['issues']), record['issues'])

    def test_noise_only_bins_are_excluded(self):
        study = first_study()
        confirm(study)
        records = [study.pilots[0], study.confirmations[-1]]
        noisy = [dict(sigma=[1e6, 1e6]), dict(sigma=[1e6, 1e6])]
        result = assess_setup_coherence(records, study.recommendation.config, noisy)
        self.assertEqual(result['summary']['usable_bins'], 0)
        self.assertEqual(result['summary']['status'], 'insuficiente')
        self.assertTrue(np.isnan(result['coherence']).all())

    def test_different_points_and_physically_bad_records_cannot_validate(self):
        study = first_study()
        confirm(study)
        first, second = study.pilots[0], dict(study.confirmations[-1])
        profiles = [study.noise, second['noise']]
        second['point'] = 'P2'
        result = assess_setup_coherence([first, second], study.recommendation.config, profiles)
        self.assertFalse(result['summary']['passed'])
        second['point'] = 'P1'
        second['spectrally_valid'] = False
        result = assess_setup_coherence([first, second], study.recommendation.config, profiles)
        self.assertTrue(np.isnan(result['coherence']).all())

    def test_no_zero_padding_when_a_common_record_is_missing(self):
        study = first_study()
        confirm(study)
        first, second = study.pilots[0], dict(study.confirmations[-1])
        second['data'] = second['data'][:50].copy()
        self.assertIsNone(project_setup_record(second, study.recommendation.config))
        result = assess_setup_coherence([first, second], study.recommendation.config, [study.noise, second['noise']])
        self.assertFalse(result['summary']['passed'])
        self.assertTrue(any('bloco' in text for text in result['summary']['reasons']))

    def test_force_window_that_cuts_contact_invalidates_quality(self):
        study = first_study()
        confirm(study)
        c = study.recommendation.config
        old_width = c.force_width
        c.force_width = 2/c.sample_rate
        study.evaluate_quality()
        self.assertFalse(study.validated)
        self.assertTrue(any('janela de força' in text for text in study.coherence_result['summary']['reasons']))
        c.force_width = old_width
        study.evaluate_quality()
        self.assertTrue(study.validated)

    def test_even_and_odd_spectral_density_integrals_match_window_energy(self):
        rng = np.random.default_rng(141)
        for n in [1023, 1024]:
            signal = rng.normal(size=n)
            window = np.hanning(n)
            fft = np.fft.rfft(signal*window)
            density = spectrum_density(fft, window, 2000)
            expected = np.sum((signal*window)**2)/np.sum(window**2)
            self.assertAlmostEqual(float(np.sum(density)*2000/n), float(expected), places=12)

    def test_report_and_saved_curve_include_coherence_quality(self):
        study = first_study()
        confirm(study)
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'diagnostico'
            study.save(target)
            report = json.loads((target/'configuracao.json').read_text(encoding='utf-8'))
            quality = report['recommendation']['metrics']['coherence_quality']
            self.assertTrue(quality['passed'])
            self.assertEqual(quality['threshold'], .9)
            with np.load(target/'coerencia.npz') as curve:
                np.testing.assert_allclose(curve['coherence'], study.coherence_result['coherence'], equal_nan=True)


if __name__ == '__main__':
    unittest.main()
