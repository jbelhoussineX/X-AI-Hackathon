"""PDF text extraction in a short-lived process. Never executes PDF actions or OCR."""
from io import BytesIO
import json
import sys

from pypdf import PdfReader

MAX_PDF_PAGES = 40
MAX_STREAM_BYTES = 2_000_000
MAX_TEXT_CHARS = 500_000


def extract_pdf(data):
    if not data.startswith(b'%PDF-'):
        return {'status': 'invalid_pdf', 'pages': []}
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            return {'status': 'encrypted_pdf', 'pages': []}
        if len(reader.pages) > MAX_PDF_PAGES:
            return {'status': 'pdf_page_limit', 'pages': []}
        pages = []
        total = 0
        for page in reader.pages:
            content = page.get_contents()
            if content is not None and len(content.get_data()) > MAX_STREAM_BYTES:
                return {'status': 'pdf_content_limit', 'pages': []}
            text = page.extract_text() or ''
            total += len(text)
            if total > MAX_TEXT_CHARS:
                return {'status': 'pdf_content_limit', 'pages': []}
            pages.append(text)
        if not any(text.strip() for text in pages):
            return {'status': 'pdf_no_text', 'pages': []}
        return {'status': 'retrieved', 'pages': pages}
    except Exception:
        return {'status': 'invalid_pdf', 'pages': []}


if __name__ == '__main__':
    data = sys.stdin.buffer.read(2_000_001)
    result = {'status': 'too_large', 'pages': []} if len(data) > 2_000_000 else extract_pdf(data)
    sys.stdout.write(json.dumps(result, ensure_ascii=True))
