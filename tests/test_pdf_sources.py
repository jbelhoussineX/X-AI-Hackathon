from io import BytesIO
import json
from pathlib import Path
import subprocess
from time import monotonic
import unittest
from unittest.mock import patch

import httpx
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from backend.pdf_text_worker import extract_pdf
from backend.source_verification import read_pdf, verify_sources


def pdf_bytes(texts, password=None):
    writer = PdfWriter()
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                             NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    for text in texts:
        page = writer.add_blank_page(width=600, height=800)
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        content = DecodedStreamObject()
        content.set_data(b'BT /F1 12 Tf 50 700 Td <' + text.encode('ascii').hex().encode() + b'> Tj ET')
        page[NameObject('/Contents')] = content
    if password:
        writer.encrypt(password)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class PdfSourceTests(unittest.TestCase):
    def report(self, excerpt):
        report = json.loads((Path(__file__).parent / 'fixtures/dust/report.json').read_text(encoding='utf-8'))
        report['documents'][0]['evidence'] = [{'purpose':'contenu',
            'url':'https://www.senat.fr/leg/test.pdf', 'excerpt':excerpt, 'location':None}]
        return report

    def verify(self, texts, excerpt):
        transport = httpx.MockTransport(lambda _: httpx.Response(200, content=pdf_bytes(texts), headers={'content-type':'application/pdf'}))
        return verify_sources(self.report(excerpt), transport=transport)

    def test_subprocess_extracts_pdf_and_reports_page_number(self):
        result = self.verify(['Fictional cover.', 'The proposed grant is 100 euros.'], 'The proposed grant is 100 euros.')
        self.assertTrue(result.all_matched)
        self.assertEqual(result.checks[0]['pdf_page'], 2)

    def test_pdf_excerpt_absent_does_not_match(self):
        result = self.verify(['The proposed grant is 100 euros.'], 'The proposed grant is 200 euros.')
        self.assertEqual(result.checks[0]['status'], 'not_found')
        self.assertIsNone(result.checks[0]['pdf_page'])

    def test_no_cross_page_fabricated_quote(self):
        result = self.verify(['The proposed grant', 'is 100 euros.'], 'The proposed grant is 100 euros.')
        self.assertFalse(result.all_matched)

    def test_no_text_requires_other_method_not_fake_ocr(self):
        self.assertEqual(extract_pdf(pdf_bytes(['']))['status'], 'pdf_no_text')

    def test_encrypted_pdf_is_not_opened(self):
        self.assertEqual(extract_pdf(pdf_bytes(['Fictional text'], 'secret'))['status'], 'encrypted_pdf')

    def test_excess_pages_are_not_silently_truncated(self):
        with patch('backend.pdf_text_worker.MAX_PDF_PAGES', 1):
            self.assertEqual(extract_pdf(pdf_bytes(['One', 'Two']))['status'], 'pdf_page_limit')

    def test_stream_limit_is_enforced(self):
        with patch('backend.pdf_text_worker.MAX_STREAM_BYTES', 1):
            self.assertEqual(extract_pdf(pdf_bytes(['Text']))['status'], 'pdf_content_limit')

    def test_worker_timeout_is_not_retrieval_success(self):
        with patch('backend.source_verification.subprocess.run', side_effect=subprocess.TimeoutExpired('pdf worker', 1)):
            self.assertEqual(read_pdf(b'%PDF-', monotonic()+10)['status'], 'pdf_timeout')

    def test_invalid_pdf_is_rejected(self):
        self.assertEqual(extract_pdf(b'<html>Access denied</html>')['status'], 'invalid_pdf')
