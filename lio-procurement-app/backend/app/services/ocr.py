import io
import re
import subprocess
import unicodedata
from dataclasses import dataclass, field

import pypdfium2 as pdfium
from PIL import Image

OCR_DPI = 300
OCR_LANGUAGES = "deu+eng"
MIN_PAGE_TEXT = 20
BAND = 0.15


@dataclass
class PictureText:
    lines: list[str] = field(default_factory=list)
    pages_without_text: list[int] = field(default_factory=list)


def _fold(text: str) -> str:
    text = text.lower().replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def _words(line: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", _fold(line))
    return [w for w in words if len(w) >= 3 or any(c.isdigit() for c in w)]


def _looks_like_an_id(word: str) -> bool:
    return len(word) >= 6 and sum(c.isdigit() for c in word) >= 4


def _ids(line: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", _fold(re.sub(r"(?<=\d)[ .](?=\d)", "", line)))
            if _looks_like_an_id(w)]


def lines_missing_from(text_layer: str, ocr_text: str) -> list[str]:
    known = re.sub(r"[^a-z0-9]", "", _fold(text_layer))
    kept = []
    for line in ocr_text.splitlines():
        words = _words(line)
        if not words:
            continue
        missing = [w for w in words if w not in known]
        new_id = any(w not in known for w in _ids(line))
        if new_id or len(missing) * 2 >= len(words):
            kept.append(" ".join(line.split()))
    return kept


def page_regions(image: Image.Image) -> list[Image.Image]:
    width, height = image.size
    band = int(height * BAND)
    return [
        image,
        image.crop((0, 0, width, band)),
        image.crop((0, height - band, width, height)),
    ]


def render_pages(pdf_bytes: bytes, dpi: int = OCR_DPI) -> list[Image.Image]:
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        return [page.render(scale=dpi / 72).to_pil() for page in pdf]
    finally:
        pdf.close()


def ocr_image(image: Image.Image) -> str:
    png = io.BytesIO()
    image.save(png, format="PNG")
    result = subprocess.run(
        ["tesseract", "stdin", "stdout", "-l", OCR_LANGUAGES],
        input=png.getvalue(), capture_output=True, check=True, timeout=60,
    )
    return result.stdout.decode("utf-8", errors="replace")


def read_pictures(pdf_bytes: bytes, page_texts: list[str]) -> PictureText:
    found = PictureText()
    for number, image in enumerate(render_pages(pdf_bytes), start=1):
        text_layer = page_texts[number - 1] if number <= len(page_texts) else ""
        ocr_text = "\n".join(ocr_image(region) for region in page_regions(image))
        if len(text_layer.strip()) < MIN_PAGE_TEXT:
            found.pages_without_text.append(number)
            lines = [" ".join(line.split()) for line in ocr_text.splitlines() if _words(line)]
        else:
            lines = lines_missing_from(text_layer, ocr_text)
        found.lines += [line for line in lines if line not in found.lines]
    return found
