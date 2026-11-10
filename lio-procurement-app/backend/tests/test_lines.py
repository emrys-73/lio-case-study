import pytest

from app.schemas.extraction import ExtractedVendorData, OrderLineData
from app.services.lines import drop_vat_lines, is_vat_label


def _line(description, total, kind="charge"):
    return OrderLineData(positionDescription=description, totalPrice=total, kind=kind)


@pytest.mark.parametrize("label", [
    "MwSt.",
    "MwSt",
    "USt.",
    "VAT",
    "Mehrwertsteuer",
    "Umsatzsteuer 19%",
    "zzgl. gesetzl. MwSt. (19%)",
    "Positionen USt. 19,00% auf 1.337,26 €",
    "Versandkosten Ust. 19,00% auf 215,00 €",
    "19% MwSt.",
])
def test_vat_labels_are_recognised(label):
    assert is_vat_label(label)


@pytest.mark.parametrize("label", [
    None,
    "",
    "Urheberrechtsabgabe",
    "Versandkosten",
    "Montage inkl. MwSt. und Anfahrt",
    "MacBook Air 13 Zoll",
    "Mwst-freie Lieferung von Moos",
])
def test_other_labels_are_not_vat(label):
    assert not is_vat_label(label)


def test_a_vat_line_is_taken_out_of_the_lines():
    data = ExtractedVendorData(
        orderLines=[_line("MacBook Air", 1467.61, "item"), _line("MwSt.", 280.85),
                    _line("Urheberrechtsabgabe", 10.55)],
        vatAmount=280.85, grossTotal=1759.01,
    )
    drop_vat_lines(data)
    assert [l.position_description for l in data.order_lines] == ["MacBook Air", "Urheberrechtsabgabe"]
    assert data.vat_amount == 280.85


def test_a_vat_line_fills_an_empty_vat_field():
    data = ExtractedVendorData(
        orderLines=[_line("Moos", 1000.0, "item"), _line("MwSt. 19%", 190.0)],
        vatAmount=None,
    )
    drop_vat_lines(data)
    assert len(data.order_lines) == 1
    assert data.vat_amount == 190.0


def test_several_vat_lines_add_up_into_an_empty_vat_field():
    data = ExtractedVendorData(
        orderLines=[_line("Moos", 1337.26, "item"),
                    _line("Positionen USt. 19,00% auf 1.337,26 €", 254.08),
                    _line("Versandkosten Ust. 19,00% auf 215,00 €", 40.85)],
    )
    drop_vat_lines(data)
    assert data.vat_amount == 294.93


def test_quotes_without_vat_lines_are_left_alone():
    lines = [_line("Moos", 715.26, "item"), _line("Versandkosten", 215.0)]
    data = ExtractedVendorData(orderLines=lines, vatAmount=176.75)
    drop_vat_lines(data)
    assert data.order_lines == lines
    assert data.vat_amount == 176.75

