from dataclasses import asdict, replace
from pathlib import Path
import tempfile
import unittest
import numpy as np

from ads1800_app.modal import ModalConfig, ModalSession, processed_signals, analyze_hit, ensemble
from ads1800_app.modal_post import prepare_data, fit_modes, PostSettings
from test_modal_post import raw_session


class ModalFilterTests(unittest.TestCase):
    def test_defaults_nyquist_and_legacy_configuration(self):
        c = ModalConfig()
        c.validate()
        self.assertTrue(c.bandpass_enabled)
        self.assertEqual((c.low_cut, c.high_cut, c.sample_rate), (1, 500, 2000))
        for values in [{'sample_rate': 1000}, {'low_cut': 500}, {'high_cut': float('nan')}, {'low_cut': 0}]:
            with self.assertRaises(ValueError):
                replace(c, **values).validate()
        old = asdict(c)
        for key in ('bandpass_enabled', 'low_cut', 'high_cut'):
            old.pop(key)
        old['sample_rate'] = 1000
        restored = ModalConfig.from_dict(old)
        restored.validate()
        self.assertFalse(restored.bandpass_enabled)
        self.assertTrue(ModalConfig.from_dict(asdict(c)).bandpass_enabled)

    def test_filter_attenuates_both_stopbands_and_preserves_channel_ratio(self):
        c = ModalConfig(duration=8, pretrigger=.05, low_cut=20, high_cut=200)
        t = np.arange(c.n)/c.sample_rate
        signal = sum(np.sin(2*np.pi*f*t) for f in [2, 80, 600])
        force, response = processed_signals(c, signal, 3*signal)
        np.testing.assert_allclose(response, 3*force, atol=1e-11)
        def amplitude(values, frequency):
            return abs(2*np.mean(values[4000:]*np.exp(-2j*np.pi*frequency*t[4000:])))
        self.assertGreater(amplitude(force, 80), .95)
        self.assertLess(amplitude(force, 2), .005)
        self.assertLess(amplitude(force, 600), .01)
        raw = processed_signals(replace(c, bandpass_enabled=False), signal, 3*signal)
        self.assertGreater(amplitude(raw[0], 2), .99)

    def test_saved_spectra_and_raw_data_with_passband_mask(self):
        c = ModalConfig(duration=1, force_window='Retangular', response_window='Retangular')
        force = np.zeros(c.n)
        force[c.pre] = 100
        data = np.column_stack([np.arange(c.n)/c.sample_rate, force, 2*force])
        analysis = analyze_hit(c, data)
        expected = processed_signals(c, force, 2*force)
        np.testing.assert_allclose(analysis['F'], np.fft.rfft(expected[0]))
        f, h, coherence = ensemble(c, [analysis, analysis])
        valid = (f >= c.low_cut) & (f <= c.high_cut)
        np.testing.assert_allclose(h[valid], 2, atol=1e-10)
        self.assertTrue(np.isnan(h[~valid]).all())
        self.assertTrue(np.isnan(coherence[~valid]).all())
        with tempfile.TemporaryDirectory() as folder:
            session = ModalSession(Path(folder)/'run', c)
            record, _ = session.capture('P1', data)
            with np.load(session.directory/record['file']) as saved:
                np.testing.assert_equal(saved['force_N'], force)
                np.testing.assert_allclose(saved['F'], analysis['F'])
            loaded = ModalSession.load(session.directory)
            self.assertTrue(loaded.config.bandpass_enabled)

    def test_postprocessing_uses_filter_and_recovers_modes(self):
        with tempfile.TemporaryDirectory() as folder:
            session = raw_session(folder)
            session.config.bandpass_enabled = True
            settings = PostSettings(fmin=20, fmax=115, max_modes=2)
            data = prepare_data(session, settings)
            result = fit_modes(data, settings, [40, 85])
            np.testing.assert_allclose([m['frequency_hz'] for m in result['modes']], [40, 85], atol=.15)
            np.testing.assert_allclose([m['damping_ratio'] for m in result['modes']], [.012, .025], atol=.003)
            self.assertTrue(np.isnan(data.frfs[:, data.frequency > 500]).all())
            self.assertTrue(any('Passa-banda' in s for s in data.warnings))
            with self.assertRaisesRegex(ValueError, 'passa-banda'):
                prepare_data(session, replace(settings, fmax=600))
