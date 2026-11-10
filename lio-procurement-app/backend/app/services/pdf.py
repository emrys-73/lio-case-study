import io

from pypdf import PdfReader


def extract_text(pdf_bytes: bytes) -> str:
    """Extract the text from a vendor-offer PDF.

    Covers the offer formats we handle; the vendors we work with send
    text-based PDFs.
    """
    return "\n".join(extract_pages(pdf_bytes))


def extract_pages(pdf_bytes: bytes) -> list[str]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return [page.extract_text() or "" for page in reader.pages]
