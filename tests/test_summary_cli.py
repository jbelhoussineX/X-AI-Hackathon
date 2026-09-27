from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.summary_cli import main
from backend.source_verification import SourceVerification

REPORT = Path(__file__).resolve().parents[1] / 'methods/political_summary/test_report.json'


class SummaryCliTests(unittest.TestCase):
    def test_default_validates_without_call(self):
        with patch('backend.summary_cli.analyze_summary') as analyze, redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(REPORT), '--topic', 'Logement étudiant']), 0)
        analyze.assert_not_called()

    def test_existing_output_refuses_before_call(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'result.json'
            output.write_text('keep', encoding='utf-8')
            with patch('backend.summary_cli.analyze_summary') as analyze, redirect_stdout(io.StringIO()):
                self.assertEqual(main([str(REPORT), '--topic', 'Logement', '--run', '--output', str(output)]), 1)
            analyze.assert_not_called()
            self.assertEqual(output.read_text(), 'keep')

    def test_failure_does_not_write_result_or_expose_error(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'result.json'
            log = io.StringIO()
            report = json.loads(REPORT.read_text(encoding='utf-8'))
            with patch('backend.summary_cli.verify_sources', return_value=SourceVerification(report, [{'status':'matched'}])), \
                 patch('backend.summary_cli.analyze_summary', side_effect=RuntimeError('secret-value')), redirect_stdout(log):
                self.assertEqual(main([str(REPORT), '--topic', 'Logement', '--run', '--output', str(output)]), 1)
            self.assertFalse(output.exists())
            self.assertNotIn('secret-value', log.getvalue())
