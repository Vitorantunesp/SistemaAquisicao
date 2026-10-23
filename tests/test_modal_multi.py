import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
import numpy as np

from ads1800_app.modal import ModalConfig, ModalSession, ImpactCapture, ensemble
from ads1800_app.modal_post import PostSettings, prepare_data


class MultipleAccelerometersTests(unittest.TestCase):
    def config(self):
        return ModalConfig(sample_rate=1000, bandpass_enabled=False, duration=.2,
                           pretrigger=.02, force_width=.01, force_window='Retangular', response_window='Retangular',
                           additional_accelerometers=[dict(name='A2', channel=2, position=[.8, .25], factor=1, limits=[-100, 100])])

    def test_synchronized_capture_roundtrip_separate_frfs_and_postprocessing(self):
        c = self.config()
        capture = ImpactCapture(c)
        capture.arm('P1')
        t = np.arange(400)/c.sample_rate
        force = np.zeros(400)
        force[50:52] = 20
        responses = np.column_stack([force*2, force*-3])
        self.assertIsNone(capture.feed(t[:51], force[:51], responses[:51]))
        point, data = capture.feed(t[51:], force[51:], responses[51:])
        self.assertEqual(data.shape, (c.n, 4))
        np.testing.assert_allclose(data[:, 2], data[:, 1]*2)
        np.testing.assert_allclose(data[:, 3], data[:, 1]*-3)
        with tempfile.TemporaryDirectory() as folder:
            session = ModalSession(Path(folder)/'run', c)
            for _ in range(2):
                record, _ = session.capture(point, data)
                session.review(record, True)
            restored = ModalSession.load(session.directory)
            self.assertEqual(len(restored.config.sensors), 2)
            for sensor, gain in enumerate([2, -3]):
                _, h, coherence = ensemble(c, restored.hits('P1', sensor))
                np.testing.assert_allclose(h[np.isfinite(h)], gain)
                np.testing.assert_allclose(coherence[np.isfinite(coherence)], 1)
                modal = prepare_data(restored, PostSettings(fmin=10, fmax=300), sensor)
                np.testing.assert_allclose(modal.frfs[np.isfinite(modal.frfs)], gain)
                self.assertEqual(modal.source_records[0]['accelerometer'], f'A{sensor+1}')
            for _ in range(2):
                second, _ = restored.capture('P2', data)
                restored.review(second, True)
            joint = prepare_data(restored, PostSettings(fmin=10, fmax=300), None)
            self.assertEqual(joint.frf_pairs, [('A1', 'P1'), ('A1', 'P2'), ('A2', 'P1'), ('A2', 'P2')])
            self.assertEqual(joint.frfs.shape[0], 4)
            self.assertTrue((session.directory/'frf_ponto_1_acelerometro_2.csv').exists())
            # Rejecting the shared hit removes it from every response ensemble.
            restored.review(restored.records[0], False)
            self.assertEqual([len(restored.hits('P1', i)) for i in range(2)], [1, 1])

    def test_duplicate_channels_invalid_geometry_and_nonfinite_response(self):
        c = self.config()
        for extra in [dict(c.additional_accelerometers[0], channel=0),
                      dict(c.additional_accelerometers[0], name='A1'),
                      dict(c.additional_accelerometers[0], factor=0),
                      dict(c.additional_accelerometers[0], position=[np.nan, 0])]:
            with self.assertRaises(ValueError):
                replace(c, additional_accelerometers=[extra]).validate()
        capture = ImpactCapture(c)
        capture.arm('P1')
        with self.assertRaises(ValueError):
            capture.feed([0], [0], [[0, np.nan]])
        self.assertFalse(capture.armed)
