from dataclasses import dataclass
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


Status = Literal["pending", "approved", "rejected"]


@dataclass(frozen=True)
class ApprovalEvent:
    action: Literal["auto_approved", "approval_reset"]
    summary: str
    detail: dict


@dataclass(frozen=True)
class ApprovalOutcome:
    status: Status
    events: tuple[ApprovalEvent, ...] = ()


def _amount(value: float | Decimal | None) -> float | None:
    return None if value is None else float(_cents(value))


def approval_on_save(
    status: Status,
    approved_by_person: bool,
    old_total: float | Decimal | None,
    new_total: float | Decimal | None,
    limit: float | None,
    adds_up: bool | None = None,
) -> ApprovalOutcome:
    if status == "rejected":
        return ApprovalOutcome("rejected")
    decision = approval_for(new_total, limit, adds_up)
    old, new = _amount(old_total), _amount(new_total)
    events: tuple[ApprovalEvent, ...] = ()
    if status == "approved":
        if approved_by_person:
            keep = (new or 0) <= (old or 0)
        else:
            keep = decision == "approved"
        if keep:
            return ApprovalOutcome("approved")
        if (new or 0) != (old or 0):
            why = f"the total went from €{old or 0:,.2f} to €{new or 0:,.2f}"
        elif adds_up is False:
            why = "the lines don't add up to the total"
        else:
            why = f"€{new or 0:,.2f} is no longer under the limit"
        events = (
            ApprovalEvent(
                "approval_reset",
                f"Back to pending, {why}",
                {"from_total": old, "to_total": new, "limit": limit},
            ),
        )
    if decision == "approved":
        auto = ApprovalEvent(
            "auto_approved",
            f"Approved automatically, €{new:,.2f} is under the €{limit:,.2f} limit",
            {"limit": limit, "computed_total": new},
        )
        return ApprovalOutcome("approved", events + (auto,))
    return ApprovalOutcome("pending", events)
