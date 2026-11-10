import uuid

from sqlalchemy.orm import Session

from app.models import Organization
from app.schemas.organizations import CommodityRule
from app.services.keywords import keyword_hits, words
from app.services.organization_settings import load_settings

def match_rule(
    rules: list[CommodityRule], text: str, amount: float | None = None
) -> CommodityRule | None:
    text_words = words(text)
    for rule in rules:
        if rule.max_amount is not None and (amount is None or amount > rule.max_amount):
            continue
        if any(keyword_hits(keyword, text_words) for keyword in rule.keywords):
            return rule
    return None


def company_rules(db: Session, organization_id: uuid.UUID) -> list[CommodityRule]:
    return load_settings(db.get(Organization, organization_id)).commodity_rules


def categorise(
    db: Session, organization_id: uuid.UUID, text: str, amount: float | None = None
) -> int | None:
    rule = match_rule(company_rules(db, organization_id), text, amount)
    return rule.commodity_group_id if rule else None
