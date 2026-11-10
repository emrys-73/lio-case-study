import io

from PIL import Image, ImageDraw, ImageFont

from app.services.ocr import lines_missing_from, page_regions, read_pictures
from app.services.pdf import extract_pages

TEXT_LAYER = """styleGREEN Angebot AN-OF2312380
Es gelten die AGB der FlowerArt GmbH, Geschäftsführer Simon Krämer, AG München
Lio Technologies GmbH
Höhenkirchen-Siegertsbrunn
Pos Menge Einheit Bezeichnung Einzelpreis Gesamtpreis
1 1,28 qm styleGREEN INDIVIDUAL m2 Modul 559,00 715,52"""


def test_a_footer_only_in_the_picture_is_kept():
    ocr = "FlowerArt GmbH | USt-IdNr.: DE271073640"
    assert lines_missing_from(TEXT_LAYER, ocr) == ["FlowerArt GmbH | USt-IdNr.: DE271073640"]


def test_a_line_already_in_the_text_is_dropped():
    assert lines_missing_from(TEXT_LAYER, "Lio Technologies GmbH") == []


def test_one_misread_word_does_not_bring_a_line_back():
    assert lines_missing_from(TEXT_LAYER, "Lio Technologies GmbH Héhenkirchen-Siegertsbrunn") == []


def test_glued_words_in_the_text_layer_still_count_as_found():
    assert lines_missing_from("PosMengeEinheitBezeichnung", "Pos Menge Einheit Bezeichnung") == []


def test_noise_lines_are_dropped():
    assert lines_missing_from(TEXT_LAYER, "|\n— .\n  \n") == []


def _pdf_with_text_in_a_picture(text: str) -> bytes:
    image = Image.new("RGB", (1700, 400), "white")
    ImageDraw.Draw(image).text((60, 150), text, fill="black", font=ImageFont.load_default(size=56))
    buffer = io.BytesIO()
    image.save(buffer, format="PDF", resolution=200)
    return buffer.getvalue()


def test_text_in_a_picture_is_read():
    pdf = _pdf_with_text_in_a_picture("USt-IdNr. DE271073640")
    pages = extract_pages(pdf)
    assert pages == [""]
    found = read_pictures(pdf, pages)
    assert found.pages_without_text == [1]
    assert any("DE271073640" in line.replace(" ", "") for line in found.lines)


def test_a_line_with_a_new_id_is_kept_even_when_its_other_words_are_known():
    ocr = "Geschäftsführer: Simon Krämer | AG München | USt-IdNr.: DE271073640"
    assert lines_missing_from(TEXT_LAYER, ocr) == [ocr]


def test_a_known_line_with_only_known_numbers_is_still_dropped():
    assert lines_missing_from(TEXT_LAYER, "1 1,28 qm styleGREEN INDIVIDUAL m2 Modul 559,00 715,52") == []


def test_the_letterhead_and_footer_get_their_own_ocr_pass():
    page = Image.new("RGB", (1000, 2000), "white")
    full, top, bottom = page_regions(page)
    assert full.size == (1000, 2000)
    assert top.size == (1000, 300)
    assert bottom.size == (1000, 300)


def test_the_same_line_found_twice_is_added_once():
    pdf = _pdf_with_text_in_a_picture("USt-IdNr. DE271073640")
    found = read_pictures(pdf, [""])
    assert len(found.lines) == len(set(found.lines))
