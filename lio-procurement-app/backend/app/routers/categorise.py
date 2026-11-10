from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_membership
from app.db.session import get_db
from app.models import OrganizationMember
from app.schemas.categorise import CategoriseIn, CategoriseOut, LineCategoryOut
from app.services.categorisation import best_hit, commodity_block, company_rules, match_line

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
    commodity = commodity_block(
        db,
        membership.role,
        hit.rule.commodity_group_id if hit else None,
        "rule" if hit else "none",
        hit,
    )
    return CategoriseOut(lines=lines, commodity=commodity)
