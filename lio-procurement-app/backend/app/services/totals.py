from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol


class HasTotal(Protocol):
    total_price: float | None


def _cents(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def add_up(lines: Iterable[HasTotal]) -> float:
    return float(sum((_cents(line.total_price or 0) for line in lines), Decimal(0)))


def same_amount(a: float, b: float) -> bool:
    return _cents(a) == _cents(b)


VAT_RATES = (Decimal("0.19"), Decimal("0.07"))
ROUNDING = Decimal("0.02")


def gross_fits(net: float, vat: float | None, gross: float | None) -> bool | None:
    if gross is None:
        return None
    net_c, gross_c = _cents(net), _cents(gross)
    if vat is not None and net_c + _cents(vat) == gross_c:
        return True
    if not vat and net_c == gross_c:
        return True
    return any(abs(net_c * (1 + rate) - gross_c) <= ROUNDING for rate in VAT_RATES)


def check_totals(
    lines: Iterable[HasTotal],
    printed: float | None,
    vat: float | None = None,
    gross: float | None = None,
) -> dict:
    computed = add_up(lines)
    return {
        "computed": computed,
        "printed": printed,
        "match": None if printed is None else same_amount(computed, printed),
        "vat": vat,
        "gross": gross,
        "grossMatch": gross_fits(computed, vat, gross),
    }
