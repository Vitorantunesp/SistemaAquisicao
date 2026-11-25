from dataclasses import replace
import unittest

import numpy as np

from ads1800_app.config import ADS1800_SAMPLE_RATES
from ads1800_app.modal import ModalConfig, ImpactCapture
from ads1800_app.modal_setup import SetupSettings, TwoHitStudy, two_hit_metrics
from ads1800_app.modal_coherence import spectrum_density
from test_modal_setup import mechanical_record


def first_study(decay=5, observation=4):
    base = ModalConfig(bandpass_enabled=False, force_limits=(-500, 500))
    settings = SetupSettings(fmin=10, fmax=200, noise_seconds=.5,
        observation_seconds=observation, minimum_hits=1, minimum_points=1, confirmation_hits=1)
    study = TwoHitStudy(base, ADS1800_SAMPLE_RATES, settings)
    rng = np.random.default_rng(53)
    study.set_noise(rng.normal(size=(round(.5*study.pilot_rate), 2))*[.01, .0001]+[.3, .02])
    c = study.pilot_config()
    study.add_pilot('P1', mechanical_record(c, decay=decay), c)
    study.suggest()
    return study


def confirm(study, *, scale=1, decay=5):
    c = study.recommendation.config
    rng = np.random.default_rng(6)
    study.set_confirmation_noise(rng.normal(size=(round(.5*c.sample_rate), 2))*[.01, .0001]+[.3, .02])
    c = study.confirmation_config()
    return study.add_confirmation('P1', mechanical_record(c, decay=decay, scale=scale), c)


class TwoHitTests(unittest.TestCase):
    def test_first_hit_sets_half_peak_and_exact_five_percent_decay_margin(self):
        study = first_study()
        rec, m = study.recommendation, study.first_metrics
        self.assertAlmostEqual(rec.config.threshold, .5*m['peak_N'])
        expected = np.ceil((rec.config.pretrigger+1.05*m['decay_s'])*rec.config.sample_rate)
        self.assertEqual(rec.config.n, expected)
        self.assertEqual(rec.config.sample_rate, 800)
        self.assertAlmostEqual(study.initial_threshold(), .05*(500+abs(study.noise['offset'][0])))
        self.assertEqual(rec.config.response_window, 'Retangular')
        self.assertFalse(study.validated)

    def test_one_consistent_second_hit_confirms_and_keeps_initial_trigger(self):
        study = first_study()
        threshold = study.recommendation.config.threshold
        result = confirm(study)
        self.assertTrue(result['accepted'], result['issues'])
        self.assertTrue(study.validated)
        self.assertEqual(len(study.pilots), 1)
        self.assertEqual(len(study.confirmations), 1)
        self.assertEqual(study.recommendation.config.threshold, threshold)
        self.assertTrue(study.matches(study.recommendation.config))

    def test_peak_or_decay_inconsistency_prevents_confirmation(self):
        for kwargs, text in [({'scale': 1.3}, 'Pico variou'), ({'decay': 3}, 'Decaimento variou')]:
            study = first_study()
            result = confirm(study, **kwargs)
            self.assertFalse(study.validated)
            self.assertTrue(any(text in s for s in result['issues']), result['issues'])

    def test_retry_retains_rejected_raw_measurement(self):
        study = first_study()
        bad = confirm(study, scale=1.4)
        self.assertFalse(bad['accepted'])
        good = confirm(study)
        self.assertTrue(good['accepted'], good['issues'])
        self.assertEqual(len(study.confirmations), 2)
        self.assertTrue(study.validated)

    def test_incomplete_decay_automatically_indicates_exponential(self):
        study = first_study(decay=.1, observation=2)
        self.assertTrue(study.recommendation.blockers)
        self.assertEqual(study.recommendation.config.response_window, 'Exponencial')
        self.assertIn('Exponencial', study.recommendation.metrics['windowing']['response'])

    def test_quiet_observation_is_excluded_from_measured_decay(self):
        study = first_study()
        h = study.pilots[0]
        c = ModalConfig.from_dict(h['config'])
        m = two_hit_metrics(h['data'], c, study.noise)
        self.assertTrue(m['settled'])
        self.assertGreater(m['quiet_s'], .25)
        self.assertLess(study.recommendation.config.duration, c.duration)

    def test_psd_units_frequency_and_integral_match_mean_square(self):
        fs = 2000
        t = np.arange(10000)/fs
        for frequency, amplitude in [(35, 3), (90, .04)]:
            y = amplitude*np.sin(2*np.pi*frequency*t)
            window = np.hanning(len(y))
            f = np.fft.rfftfreq(len(y), 1/fs)
            density = spectrum_density(np.fft.rfft(y*window), window, fs)
            self.assertAlmostEqual(f[np.argmax(density)], frequency)
            self.assertTrue(np.all(density >= 0))
            self.assertAlmostEqual(float(np.sum(density)*(f[1]-f[0])), amplitude**2/2, places=9)

    def test_rising_pulse_does_not_veto_its_own_acceleration_trigger(self):
        c = ModalConfig(sample_rate=10000, bandpass_enabled=False, duration=.5,
                        pretrigger=.02, threshold=50, rearm_noise_limits=(.001,), quiet_duration=.1)
        capture = ImpactCapture(c)
        capture.arm('P1')
        times = np.arange(8000)/c.sample_rate
        force = np.zeros(len(times))
        force[2000:2100] = np.arange(1, 101)
        result = capture.feed(times, force, .1*force)
        self.assertIsNotNone(result)
        self.assertEqual(result[1][c.pre, 1], 50)
