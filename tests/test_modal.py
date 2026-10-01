import tempfile
from pathlib import Path
import unittest
import numpy as np

from ads1800_app.modal import ModalConfig, ImpactCapture, ModalSession, analyze_hit, ensemble, windows


class ModalTests(unittest.TestCase):
    def config(self, **kwargs):
        return ModalConfig(sample_rate=1000, bandpass_enabled=False, duration=.2, pretrigger=.02, force_width=.01,
                           force_window='Retangular', response_window='Retangular', **kwargs)

    def test_trigger_boundary_pretrigger_polarity_and_single_shot(self):
        for polarity, sign in [('Absoluto', -1), ('Positivo', 1), ('Negativo', -1)]:
            c = self.config(polarity=polarity)
            capture = ImpactCapture(c)
            capture.arm('P2')
            t = np.arange(500)/c.sample_rate
            f = np.zeros(500)
            f[50:53] = sign*20
            f[300:303] = sign*20
            result = None
            for start, end in [(0, 50), (50, 51), (51, 145), (145, 500)]:
                hit = capture.feed(t[start:end], f[start:end], f[start:end]*2)
                if hit:
                    result = hit
            self.assertEqual(result[0], 'P2')
            self.assertEqual(result[1].shape, (c.n, 3))
            self.assertAlmostEqual(result[1][c.pre, 0], .05)
            self.assertEqual(result[1][c.pre, 1], sign*20)
            self.assertFalse(capture.armed)

    def test_gap_cancels_pending(self):
        c = self.config()
        capture = ImpactCapture(c)
        capture.arm('P1')
        f = np.zeros(50)
        f[30] = 20
        capture.feed(np.arange(50)/1000, f, f)
        self.assertIsNotNone(capture.pending)
        with self.assertRaises(ValueError):
            capture.feed([.055], [0], [0])
        self.assertFalse(capture.armed)
        self.assertIsNone(capture.pending)

    def test_h1_complex_gain_and_coherence_requires_ensemble(self):
        c = self.config()
        rng = np.random.default_rng(6)
        force = rng.normal(size=c.n)
        F = np.fft.rfft(force)
        freq = np.fft.rfftfreq(c.n, 1/c.sample_rate)
        expected = 2*np.exp(-2j*np.pi*freq*.003)
        hit = {'F': F, 'A': F*expected}
        _, h, coherence = ensemble(c, [hit])
        np.testing.assert_allclose(h, expected)
        self.assertTrue(np.isnan(coherence).all())
        _, h, coherence = ensemble(c, [hit, hit])
        np.testing.assert_allclose(coherence, 1)
        noisy = [{'F': np.fft.rfft(rng.normal(size=c.n)), 'A': np.fft.rfft(rng.normal(size=c.n))} for _ in range(100)]
        self.assertLess(np.nanmean(ensemble(c, noisy)[2]), .05)

    def test_windows_and_quality(self):
        c = ModalConfig(sample_rate=1000, bandpass_enabled=False, duration=.2, pretrigger=.02, force_width=.01, force_limits=(-50, 50))
        wf, wa = windows(c)
        self.assertEqual(wf[c.pre], 1)
        self.assertEqual(wf[-1], 0)
        self.assertAlmostEqual(wa[-1], .01)
        data = np.zeros((c.n, 3))
        data[:, 0] = np.arange(c.n)/c.sample_rate
        data[c.pre:c.pre+2, 1] = 50
        data[c.pre+30:c.pre+32, 1] = 25
        data[c.pre:, 2] = 1
        issues = analyze_hit(c, data)['issues']
        self.assertTrue(any('duplo' in s for s in issues))
        self.assertTrue(any('saturação' in s for s in issues))
        self.assertTrue(any('não decaiu' in s for s in issues))
        self.assertTrue(any('fora da janela' in s for s in issues))

    def test_persistence_excludes_rejected_and_isolates_points(self):
        c = self.config()
        data = np.zeros((c.n, 3))
        data[:, 0] = np.arange(c.n)/c.sample_rate
        data[c.pre, 1:] = [20, 40]
        with tempfile.TemporaryDirectory() as folder:
            session = ModalSession(Path(folder)/'run', c)
            first, _ = session.capture('P1', data)
            second, _ = session.capture('P2', data)
            session.review(first, True)
            session.review(second, False)
            self.assertEqual(len(session.hits('P1')), 1)
            self.assertEqual(len(session.hits('P2')), 0)
            self.assertTrue((session.directory/'frf_ponto_1.csv').exists())
            with np.load(session.directory/first['file']) as saved:
                np.testing.assert_equal(saved['acceleration_m_s2'], data[:, 2])
            session.review(first, False)
            self.assertEqual(len(session.hits('P1')), 0)
            restored = ModalSession.load(session.directory)
            self.assertEqual(restored.config, session.config)
            self.assertEqual(restored.records, session.records)
            restored.review(restored.records[1], True)
            self.assertEqual(len(restored.hits('P2')), 1)

    def test_session_rejects_external_capture_paths(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            session = ModalSession(Path(folder)/'run', self.config())
            manifest = session.directory/'session.json'
            payload = json.loads(manifest.read_text(encoding='utf-8'))
            payload['records'] = [{'file': '../external.npz'}]
            manifest.write_text(json.dumps(payload), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Caminho'):
                ModalSession.load(session.directory)

    def test_config_validation(self):
        for patch in [{'points': [['P1', 0, 0], ['P1', 1, 1]]}, {'pretrigger': 0},
                      {'force_channel': 1}, {'exponential_end': 0}, {'threshold': float('nan')}]:
            c = ModalConfig(**patch)
            with self.assertRaises(ValueError):
                c.validate()
