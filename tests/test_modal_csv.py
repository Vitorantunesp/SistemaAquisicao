from pathlib import Path
import tempfile
import unittest
import numpy as np

from ads1800_app.modal import ModalConfig
from ads1800_app.modal_csv import read_recording, candidate_impacts, import_interval


class CsvTests(unittest.TestCase):
    def test_both_headers_SI_conversion_and_pending_only_import(self):
        headers = ['Name;Martelo;Acel; ;SampFreq:;1000Hz\nUnit;lbf;g\nHighLim;7;6\nLowLim;-7;-6\nTime (s)\n',
                   'Experimento;Teste\nFrequencia_Hz;1000\n\ntempo_s;Martelo [lbf];Acel [g]\n']
        with tempfile.TemporaryDirectory() as folder:
            for i, header in enumerate(headers):
                path = Path(folder)/f'input_{i}.csv'
                t = np.arange(3000)/1000
                force = np.zeros(3000)
                force[100] = force[2000] = 2
                source = header+'\n'.join(f'{x:.3f};{f};{.1*f}' for x, f in zip(t, force))
                path.write_text(source, encoding='utf-8')
                recording = read_recording(path)
                self.assertEqual(recording.sample_rate, 1000)
                self.assertAlmostEqual(recording.samples[100, 1], 8.896443230521)
                self.assertAlmostEqual(recording.samples[100, 2], 1.96133)
                c = ModalConfig(sample_rate=1000, duration=.5, high_cut=450, threshold=2)
                captures = candidate_impacts(recording, c, 0, 1)
                self.assertEqual(len(captures), 1)
                session = import_interval(recording, c, Path(folder)/f'run_{i}', 'P2', 0, 1)
                self.assertEqual(len(session.records), 1)
                self.assertEqual(session.records[0]['status'], 'pendente')
                self.assertEqual(session.records[0]['point'], 'P2')
                self.assertEqual(session.hits('P2'), [])
                self.assertEqual(path.read_text(encoding='utf-8'), source)

    def test_discontinuous_csv_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'gap.csv'
            path.write_text('Frequencia_Hz;1000\ntempo_s;Martelo [N];Acel [g]\n'+
                            '\n'.join(f'{i*.002};0;0' for i in range(20)), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'descontínuo'):
                read_recording(path)
