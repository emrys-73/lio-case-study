import re

from app.schemas.extraction import ExtractedVendorData
from app.services.totals import add_up, gross_fits, same_amount

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


def _fits(extracted: ExtractedVendorData, lines: list) -> bool:
    return bool(gross_fits(add_up(lines), extracted.vat_amount, extracted.gross_total))


def drop_listed_alternatives(extracted: ExtractedVendorData) -> None:
    if extracted.gross_total is None or _fits(extracted, extracted.order_lines):
        return
    alternative_prices = [a.total_price for a in extracted.alternatives if a.total_price is not None]
    kept = [
        l for l in extracted.order_lines
        if l.kind == "charge" or l.total_price is None
        or not any(same_amount(l.total_price, p) for p in alternative_prices)
    ]
    if len(kept) < len(extracted.order_lines) and _fits(extracted, kept):
        extracted.order_lines = kept


def fill_lump_sum_charges(extracted: ExtractedVendorData) -> None:
    for line in extracted.order_lines:
        if (line.kind == "charge" and line.total_price is not None
                and line.unit_price is None and line.amount is None):
            line.amount = 1
            line.unit_price = line.total_price
