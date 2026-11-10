from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol


class HasTotal(Protocol):
    total_price: float | None


def _cents(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def add_up(lines: Iterable[HasTotal]) -> float:
    return float(sum((_cents(line.total_price or 0) for line in lines), Decimal("0")))


def same_amount(a: float, b: float) -> bool:
    return _cents(a) == _cents(b)


def check_totals(
    lines: Iterable[HasTotal],
    printed: float | None,
    vat: float | None = None,
    gross: float | None = None,
) -> dict:
    computed = add_up(lines)
    both = vat is not None and gross is not None
    return {
        "computed": computed,
        "printed": printed,
        "match": None if printed is None else same_amount(computed, printed),
        "vat": vat,
        "gross": gross,
        "grossMatch": same_amount(computed + vat, gross) if both else None,
    }
