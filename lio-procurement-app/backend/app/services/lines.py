import re

from app.schemas.extraction import ExtractedVendorData
from app.services.totals import add_up

VAT_WORDS = {"mwst", "ust", "umsatzsteuer", "mehrwertsteuer", "vat"}
VAT_FILLER = {"zzgl", "gesetzl", "gesetzliche", "plus", "auf", "positionen", "versandkosten", "eur"}


def _words(text: str) -> list[str]:
    return re.findall(r"[^\W\d_]+", text.lower())


def is_vat_label(description: str | None) -> bool:
    words = _words(description or "")
    return any(w in VAT_WORDS for w in words) and all(w in VAT_WORDS | VAT_FILLER for w in words)


def drop_vat_lines(extracted: ExtractedVendorData) -> None:
    vat_lines = [l for l in extracted.order_lines if is_vat_label(l.position_description)]
    if not vat_lines:
        return
    extracted.order_lines = [l for l in extracted.order_lines if not is_vat_label(l.position_description)]
    if extracted.vat_amount is None:
        extracted.vat_amount = add_up(vat_lines)

