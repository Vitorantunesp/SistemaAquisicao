import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from html.parser import HTMLParser
from unittest.mock import patch
import subprocess

from ads1800_app.modal import ModalConfig, ModalSession
from ads1800_app.modal_ema import identify_ema
from ads1800_app.modal_post import PostSettings
from ads1800_app.modal_report import generate_report
from ads1800_app.modal_report_runner import generate_report_isolated
from test_modal_post import analytic_data
from test_modal_mimo import mimo_data


class ReportTests(unittest.TestCase):
    def test_subprocess_report_and_failed_renderer_preserve_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            session = SimpleNamespace(config=ModalConfig(), metadata={}, records=[], directory=Path(folder))
            result = identify_ema(analytic_data(), PostSettings(fmin=20, fmax=115), [40, 85], order=8)
            target = Path(folder)/'report.html'
            generate_report_isolated(session, result, target)
            original = target.read_bytes()
            self.assertIn(b'<svg', original)
            with patch('ads1800_app.modal_report_runner.subprocess.run', return_value=subprocess.CompletedProcess([], 139, '', 'Falha nativa simulada')):
                with self.assertRaisesRegex(RuntimeError, 'Falha nativa simulada'):
                    generate_report_isolated(session, result, target)
            self.assertEqual(target.read_bytes(), original)
            with patch('ads1800_app.modal_report.os.replace', side_effect=PermissionError('arquivo bloqueado')):
                with self.assertRaises(PermissionError):
                    generate_report(session, result, target)
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual(list(Path(folder).glob('.relatorio_*.tmp')), [])

    def test_report_metadata_unknown_dates_temperature_roundtrip_and_escaping(self):
        with tempfile.TemporaryDirectory() as folder:
            c = ModalConfig(ambient_temperature_c=23.7)
            session = ModalSession(Path(folder)/'run', c, dict(mode='<script>teste</script>',
                acquisition_started_at='2026-10-23T14:31:22-03:00'))
            session = ModalSession.load(session.directory)
            self.assertEqual(session.config.ambient_temperature_c, 23.7)
            result = identify_ema(analytic_data(), PostSettings(fmin=20, fmax=115), [40, 85], order=8)
            path = generate_report(session, result, Path(folder)/'report.html')
            text = path.read_text(encoding='utf-8')
            HTMLParser().feed(text)
            for value in ['23.7', '23/10/2026 14:31:22 -0300', 'Amortecimento', 'Coerência', 'Z imaginário', 'P3', '<svg']:
                self.assertIn(value, text)
            self.assertNotIn('<script>', text)
            self.assertIn('&lt;script&gt;', text)
            session.metadata = {}
            session.config.ambient_temperature_c = None
            generate_report(session, result, path)
            text = path.read_text(encoding='utf-8')
            self.assertIn('Não informado', text)
            self.assertNotIn('14:31:22', text)
            with self.assertRaises(ValueError):
                ModalConfig(ambient_temperature_c=float('nan')).validate()

    def test_mimo_report_pairs_outputs_and_figures(self):
        with tempfile.TemporaryDirectory() as folder:
            c = ModalConfig(additional_accelerometers=[dict(name='A2', channel=2, position=[.8, .25], factor=1)])
            session = SimpleNamespace(config=c, metadata={}, records=[], directory=Path(folder))
            result = identify_ema(mimo_data(), PostSettings(fmin=20, fmax=115), [40, 85], order=8)
            path = generate_report(session, result, Path(folder)/'mimo.html', 'MIMO')
            text = path.read_text(encoding='utf-8')
            self.assertIn('A2 ← P3', text)
            self.assertIn('Z real (saída)', text)
            self.assertIn('Todos os acelerômetros', text)
            self.assertEqual(text.count('<svg'), 4)  # geometry, coherence, two modes
