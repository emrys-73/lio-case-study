from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.routers import extraction as route
from app.schemas.extraction import ExtractedVendorData, ExtractionResponse
from app.services.extraction import (
    merge_picture_answer,
    needs_page_images,
    quote_text,
    request_params,
)
from app.services.ocr import PictureText


def _answer(**fields):
    return ExtractionResponse(success=True, data=ExtractedVendorData(**fields))


def test_text_found_only_in_pictures_is_added_under_its_own_label():
    text = quote_text(["Seite 1", "Seite 2"], PictureText(lines=["USt-IdNr.: DE271073640"]))
    assert text.startswith("Seite 1\nSeite 2")
    assert "Text found in pictures on the page (OCR, may have misreads):\nUSt-IdNr.: DE271073640" in text


def test_nothing_is_added_when_ocr_found_nothing_new():
    assert quote_text(["Seite 1"], PictureText()) == "Seite 1"


def test_page_pictures_go_to_the_model_for_a_scanned_page():
    assert needs_page_images(PictureText(pages_without_text=[1]), _answer(vendorName="A", vatId="B"))


def test_page_pictures_go_to_the_model_when_vendor_or_vat_id_stay_empty():
    assert needs_page_images(PictureText(), _answer(vendorName="styleGREEN", vatId=None))
    assert needs_page_images(PictureText(), _answer(vendorName=" ", vatId="DE1"))


def test_no_page_pictures_when_text_was_enough():
    assert not needs_page_images(PictureText(), _answer(vendorName="styleGREEN", vatId="DE271073640"))


def test_no_page_pictures_after_a_failed_call():
    assert not needs_page_images(PictureText(), ExtractionResponse(success=False, error="x"))


def test_picture_answer_only_fills_what_was_empty():
    first = _answer(vendorName="styleGREEN", vatId=None, totalCost=1299.99)
    second = _answer(vendorName="FlowerArt GmbH", vatId="DE271073640", totalCost=1.0)
    merged = merge_picture_answer(first, second, PictureText())
    assert merged.data.vendor_name == "styleGREEN"
    assert merged.data.vat_id == "DE271073640"
    assert merged.data.total_cost == 1299.99
    assert "VAT ID" not in (merged.missing_fields or [])


def test_picture_answer_replaces_everything_for_a_scan():
    first = _answer(vendorName=None)
    second = _answer(vendorName="Scan GmbH", vatId="DE1")
    merged = merge_picture_answer(first, second, PictureText(pages_without_text=[1]))
    assert merged is second


def test_failed_picture_answer_keeps_the_first():
    first = _answer(vendorName="styleGREEN")
    second = ExtractionResponse(success=False, error="timeout")
    assert merge_picture_answer(first, second, PictureText()) is first


def test_page_pictures_are_sent_as_images():
    page = Image.new("RGB", (20, 30), "white")
    params = request_params("Angebot", "1 | IT | Software", page_images=[page, page])
    content = params["messages"][1]["content"]
    assert content[0]["type"] == "text"
    images = [part for part in content if part["type"] == "image_url"]
    assert len(images) == 2
    assert images[0]["image_url"]["url"].startswith("data:image/png;base64,")


def test_without_pictures_the_prompt_stays_plain_text():
    params = request_params("Angebot", "1 | IT | Software")
    assert isinstance(params["messages"][1]["content"], str)


def _token(client):
    r = client.post("/auth/signin", json={"email": "buyer@acme.com", "password": "demo1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_pdf_route_reads_the_file_on_the_server_and_names_the_buyer(monkeypatch):
    seen = {}

    def fake_extract_quote(pdf_bytes, db, buyer_name=None):
        seen.update(pdf_bytes=pdf_bytes, buyer_name=buyer_name)
        return ExtractionResponse(success=False, error="stopped before the model")

    monkeypatch.setattr(route, "extract_quote", fake_extract_quote)
    client = TestClient(app)
    r = client.post("/extraction/pdf", headers=_token(client),
                    files={"file": ("q.pdf", b"%PDF-1.4 quote", "application/pdf")})
    assert r.status_code == 200, r.text
    assert seen == {"pdf_bytes": b"%PDF-1.4 quote", "buyer_name": "Acme Corp"}


def test_pdf_route_rejects_a_file_that_is_not_a_pdf():
    client = TestClient(app)
    r = client.post("/extraction/pdf", headers=_token(client),
                    files={"file": ("q.txt", b"hello", "text/plain")})
    assert r.status_code == 400
