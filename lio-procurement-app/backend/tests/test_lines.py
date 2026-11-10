import pytest

from app.schemas.extraction import AlternativeData, ExtractedVendorData, OrderLineData
from app.services.lines import drop_listed_alternatives, drop_vat_lines, is_vat_label


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


def _alt(description, total):
    return AlternativeData(positionDescription=description, totalPrice=total)


def _dream_in_green(**overrides):
    fields = dict(
        orderLines=[_line("Moosbild Mix-Moos 160x80 cm", 715.26, "item"),
                    _line('Logointegration "asklio" horizontal', 622.0, "item"),
                    _line('Logointegration "asklio" vertical', 430.0, "item"),
                    _line("Versandkosten", 215.0)],
        alternatives=[_alt("Logo vertikal", 430.0)],
        vatAmount=254.08, grossTotal=1847.19,
    )
    fields.update(overrides)
    return ExtractedVendorData(**fields)


def test_a_line_that_is_also_listed_as_an_alternative_is_taken_out_when_the_gross_agrees():
    data = _dream_in_green()
    drop_listed_alternatives(data)
    assert [l.total_price for l in data.order_lines] == [715.26, 622.0, 215.0]
    assert [a.total_price for a in data.alternatives] == [430.0]


def test_lines_are_kept_when_the_gross_already_fits():
    data = _dream_in_green(
        orderLines=[_line("Logo weiss", 430.0, "item")],
        alternatives=[_alt("Logo schwarz", 430.0)],
        vatAmount=81.7, grossTotal=511.7,
    )
    drop_listed_alternatives(data)
    assert [l.total_price for l in data.order_lines] == [430.0]


def test_lines_are_kept_when_taking_them_out_does_not_fit_the_gross_either():
    data = _dream_in_green(grossTotal=9999.0)
    drop_listed_alternatives(data)
    assert len(data.order_lines) == 4


def test_lines_are_kept_without_a_gross_to_check_against():
    data = _dream_in_green(grossTotal=None)
    drop_listed_alternatives(data)
    assert len(data.order_lines) == 4


def test_charges_are_never_taken_out_as_alternatives():
    data = ExtractedVendorData(
        orderLines=[_line("Moos", 1000.0, "item"), _line("Versand", 100.0)],
        alternatives=[_alt("Abholung statt Versand", 100.0)],
        grossTotal=1190.0,
    )
    drop_listed_alternatives(data)
    assert len(data.order_lines) == 2
