from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

AutoDecision = Literal["approved", "pending"]


def _cents(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def approval_for(
    computed_total: float | Decimal | None,
    limit: float | None,
    adds_up: bool | None = None,
) -> AutoDecision:
    if limit is None or computed_total is None or adds_up is False:
        return "pending"
    total = _cents(computed_total)
    if total <= 0:
        return "pending"
    return "approved" if total < _cents(limit) else "pending"
