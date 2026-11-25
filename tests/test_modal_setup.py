"""Independent damped oscillator records exercise measured acquisition setup."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from scipy.signal import cont2discrete, lfilter

from ads1800_app.config import ADS1800_SAMPLE_RATES
from ads1800_app.modal import ModalConfig, ImpactCapture, analyze_hit, windows, exponential_alpha, ensemble
from ads1800_app.modal_post import PostSettings, prepare_data
from ads1800_app.modal_setup import (CalibrationStudy, SetupSettings, inspect_decay,
                                    noise_profile, select_sample_rate)


def mechanical_record(c, decay=5, second_hit=False, scale=1, seed=12):
    rng = np.random.default_rng(seed)
    t = (np.arange(c.n)-c.pre)/c.sample_rate
    force = np.zeros(c.n)
    pulse = (t >= 0) & (t < .006)
    force[pulse] = 100*scale*np.sin(np.pi*t[pulse]/.006)
    if second_hit:
        pulse = (t >= .1) & (t < .106)
        force[pulse] += 50*np.sin(np.pi*(t[pulse]-.1)/.006)
    w = 2*np.pi*35
    b, a, _ = cont2discrete(([1, 0, 0], [1, 2*decay, w*w]), 1/c.sample_rate)
    response = lfilter(b.ravel(), a, force)*.05
    force += .3+rng.normal(0, .01, c.n)
    response += .02+rng.normal(0, .0001, c.n)
    return np.column_stack([np.arange(c.n)/c.sample_rate, force, response])


def ready_study(decay=5, observation=4, exponential=False):
    base = ModalConfig(bandpass_enabled=False)
    settings = SetupSettings(fmin=10, fmax=200, noise_seconds=.2,
                             observation_seconds=observation, allow_exponential=exponential)
    study = CalibrationStudy(base, ADS1800_SAMPLE_RATES, settings)
    rng = np.random.default_rng(15)
    noise = rng.normal(size=(round(.2*study.pilot_rate), 2))*[.01, .0001]+[.3, .02]
    study.set_noise(noise)
    for i in range(6):
        study.add_pilot('P1' if i < 3 else 'P2', mechanical_record(study.pilot_config(), decay=decay, seed=i))
    return study


class SetupTests(unittest.TestCase):
    def test_minimum_advertised_rate_and_unavailable_band(self):
        for band, expected in [(50, 200), (100, 400), (200, 800), (500, 2000), (1000, 4000)]:
            self.assertEqual(select_sample_rate(ADS1800_SAMPLE_RATES, band), expected)
        self.assertEqual(select_sample_rate([96000, 48000, 12000], 5000), 48000)
        for rates, band in [([], 100), ([1000], 500), ([1000], float('nan'))]:
            with self.assertRaises(ValueError):
                select_sample_rate(rates, band)

    def test_noise_rejects_impact_and_removes_dc(self):
        rng = np.random.default_rng(1)
        values = rng.normal(0, .01, (4000, 2))+[10, -3]
        np.testing.assert_allclose(noise_profile(values)['offset'], [10, -3], atol=.001)
        values[100, 0] += 100
        with self.assertRaisesRegex(ValueError, 'impacto'):
            noise_profile(values)

    def test_decay_extends_for_light_damping_and_detects_truncation(self):
        fs = 2000
        t = (np.arange(24000)-100)/fs
        def signal(rate):
            return np.where(t >= 0, np.exp(-rate*t)*np.sin(2*np.pi*35*t), 0)
        fast = inspect_decay(signal(5), fs, 100, .0001)
        slow = inspect_decay(signal(1), fs, 100, .0001)
        self.assertTrue(fast['settled'])
        self.assertTrue(slow['settled'])
        self.assertGreater(slow['seconds'], 2*fast['seconds'])
        self.assertFalse(inspect_decay(signal(.01), fs, 100, .0001)['settled'])
        self.assertFalse(inspect_decay(np.zeros_like(t), fs, 10, .001)['observable'])

    def test_weak_slow_mode_is_not_hidden_by_strong_fast_mode(self):
        fs, pre = 1000, 100
        t = (np.arange(10000)-pre)/fs
        y = np.where(t >= 0, np.exp(-8*t)*np.sin(2*np.pi*70*t)
                     +.002*np.exp(-.5*t)*np.sin(2*np.pi*12*t), 0)
        result = inspect_decay(y, fs, pre, .00002)
        self.assertTrue(result['settled'])
        self.assertGreater(result['seconds'], 6)

    def test_suggestion_measured_duration_block_ranges_and_raw_preservation(self):
        study = ready_study()
        original = study.pilots[0]['data'].copy()
        rec = study.suggest()
        self.assertFalse(rec.blockers, rec.blockers)
        self.assertEqual(rec.config.sample_rate, 800)
        self.assertLess(rec.config.duration, study.settings.observation_seconds)
        self.assertEqual(rec.config.n, round(rec.config.duration*800))
        self.assertEqual(rec.config.response_window, 'Retangular')
        self.assertFalse(rec.config.bandpass_enabled)
        self.assertGreater(rec.ranges[0]['recommended_max'], 130)
        self.assertFalse(rec.ranges[0]['automatic'])
        self.assertEqual(rec.config.points, study.base.points)
        np.testing.assert_equal(original, study.pilots[0]['data'])
        self.assertFalse(study.validated)

    def test_light_damping_requires_longer_pilot_unless_exponential_requested(self):
        study = ready_study(decay=.1, observation=2)
        self.assertTrue(any('ainda ativa' in s for s in study.suggest().blockers))
        study = ready_study(decay=.1, observation=2, exponential=True)
        rec = study.suggest()
        self.assertFalse(rec.blockers, rec.blockers)
        self.assertLess(rec.config.exponential_end, 1)

    def test_double_hit_discontinuity_and_insufficient_point_coverage(self):
        study = ready_study()
        bad = study.add_pilot('P1', mechanical_record(study.pilot_config(), second_hit=True))
        self.assertFalse(bad['accepted'])
        data = mechanical_record(study.pilot_config())
        data[10:, 0] += .1
        with self.assertRaisesRegex(ValueError, 'descontinuidade'):
            study.add_pilot('P1', data)
        for h in study.pilots:
            h['point'] = 'P1'
        self.assertTrue(any('pontos distintos' in s for s in study.suggest().blockers))

    def test_confirmation_raw_archive_and_parameter_change(self):
        study = ready_study()
        c = study.suggest().config
        rng = np.random.default_rng(7)
        noise = rng.normal(size=(round(study.settings.noise_seconds*c.sample_rate), 2))*[.01, .0001]+[.3, .02]
        study.set_confirmation_noise(noise)
        c = study.recommendation.config
        for i in range(3):
            h = study.add_confirmation('P1', mechanical_record(c, seed=100+i))
            self.assertTrue(h['accepted'], h['issues'])
        self.assertTrue(study.validated, study.report())
        self.assertTrue(study.matches(c))
        self.assertFalse(study.matches(replace(c, threshold=c.threshold*2)))
        with tempfile.TemporaryDirectory() as tmp:
            study.save(Path(tmp)/'setup')
            report = json.loads((Path(tmp)/'setup/configuracao.json').read_text(encoding='utf-8'))
            self.assertTrue(report['validated'])
            self.assertEqual(len(list((Path(tmp)/'setup').glob('exploracao_*.npz'))), len(study.pilots))
            with np.load(Path(tmp)/'setup/exploracao_001.npz') as saved:
                np.testing.assert_equal(saved['data'], study.pilots[0]['data'])

    def test_quiet_rearming_and_offset_do_not_change_originals(self):
        c = ModalConfig(sample_rate=1000, bandpass_enabled=False, duration=.5, pretrigger=.02,
                        threshold=10, trigger_offset=100, rearm_noise_limits=(.01,), quiet_duration=.1)
        capture = ImpactCapture(c)
        capture.arm('P1')
        t = np.arange(800)/1000
        f = np.full(800, 100.)
        f[150], f[500] = 120, 125
        a = np.zeros(800)
        a[:300] = np.sin(np.arange(300))
        capture.feed(t[:400], f[:400], a[:400])
        self.assertIsNone(capture.pending)
        self.assertTrue(capture.ready)
        capture.feed(t[400:510], f[400:510], a[400:510])
        self.assertIsNotNone(capture.pending)
        self.assertEqual(capture.pending[c.pre][1], 125)

    def test_failed_new_noise_measurement_cannot_reuse_old_confirmation(self):
        study = ready_study()
        c = study.suggest().config
        rng = np.random.default_rng(33)
        noise = rng.normal(size=(round(.2*c.sample_rate), 2))*[.01, .0001]+[.3, .02]
        study.set_confirmation_noise(noise)
        for i in range(3):
            study.add_confirmation('P1', mechanical_record(study.recommendation.config, seed=300+i))
        self.assertTrue(study.validated)
        noise[10, 0] += 100
        with self.assertRaises(ValueError):
            study.set_confirmation_noise(noise)
        self.assertFalse(study.validated)
        self.assertIsNone(study.confirmation_noise)
        self.assertFalse(study.confirmations)

    def test_common_exponential_keeps_impulse_gain_and_shared_post_pipeline(self):
        c = ModalConfig(sample_rate=1000, bandpass_enabled=False, duration=1, pretrigger=.05,
                        force_width=.05, exponential_end=.1)
        force = np.zeros(c.n)
        force[c.pre+15] = 100
        data = np.column_stack([np.arange(c.n)/1000, force, 3*force])
        hit = analyze_hit(c, data)
        np.testing.assert_allclose(hit['A']/hit['F'], 3, atol=1e-12)
        wf, wa = windows(c)
        self.assertEqual(wa[c.pre], 1)
        self.assertAlmostEqual(wa[-1], .1)
        self.assertAlmostEqual(exponential_alpha(c), -np.log(.1)/((c.n-c.pre-1)/1000))
        from ads1800_app.modal import ModalSession
        with tempfile.TemporaryDirectory() as tmp:
            session = ModalSession(Path(tmp)/'run', c)
            for _ in range(2):
                record, _ = session.capture('P1', data)
                session.review(record, True)
            post = prepare_data(session, PostSettings(fmin=5, fmax=200, exponential_end=.1))
            _, online, _ = ensemble(c, session.hits('P1'))
            np.testing.assert_allclose(post.frfs[0], online, equal_nan=True)


if __name__ == '__main__':
    unittest.main()
