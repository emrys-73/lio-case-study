from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership
from app.db.session import get_db
from app.models import OrganizationMember
from app.schemas.categorise import CategoriseIn, CategoriseOut, LineCategoryOut
from app.services.categorisation import best_hit, commodity_block, company_rules, match_line
from app.services.classifier import classify

router = APIRouter(prefix="/categorise", tags=["categorise"])


def _line_total(quantity: float | None, unit_price: float | None) -> float | None:
    if quantity is None or unit_price is None:
        return None
    return round(quantity * unit_price, 2)


@router.post("", response_model=CategoriseOut)
def categorise_lines(
    payload: CategoriseIn,
    membership: OrganizationMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> CategoriseOut:
    rules = company_rules(db, membership.organization_id)
    items = [(line.description, _line_total(line.quantity, line.unit_price)) for line in payload.lines]
    lines = []
    for line, (text, total) in zip(payload.lines, items):
        match = match_line(rules, text, total)
        lines.append(
            LineCategoryOut(
                line_id=line.id,
                group_id=match.rule.commodity_group_id if match else None,
                source="rule" if match else "none",
                rule_id=match.rule.id if match else None,
                matched_keyword=match.keyword if match else None,
            )
        )
    hit = best_hit(rules, items)
    if hit is None and any(len(line.description.strip()) >= 3 for line in payload.lines):
        suggestion = classify([line.description for line in payload.lines])
        if suggestion is not None:
            commodity = commodity_block(db, membership.role, suggestion.group_id, "model", None)
            commodity = commodity.model_copy(update={"reason": suggestion.reason or None})
            return CategoriseOut(lines=lines, commodity=commodity)
    commodity = commodity_block(
        db,
        membership.role,
        hit.rule.commodity_group_id if hit else None,
        "rule" if hit else "none",
        hit,
    )
    return CategoriseOut(lines=lines, commodity=commodity)
