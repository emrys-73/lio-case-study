import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import CommodityGroup, Organization
from app.schemas.organizations import CommodityRule
from app.schemas.requests import CommodityOut
from app.services.keywords import keyword_hits, words
from app.services.organization_settings import load_settings


@dataclass(frozen=True)
class LineMatch:
    rule: CommodityRule
    keyword: str
    position: int


def match_line(
    rules: list[CommodityRule], text: str, amount: float | None = None
) -> LineMatch | None:
    text_words = words(text)
    for position, rule in enumerate(rules, start=1):
        if rule.max_amount is not None and (amount is None or amount > rule.max_amount):
            continue
        for keyword in rule.keywords:
            if keyword_hits(keyword, text_words):
                return LineMatch(rule=rule, keyword=keyword, position=position)
    return None


def match_rule(
    rules: list[CommodityRule], text: str, amount: float | None = None
) -> CommodityRule | None:
    match = match_line(rules, text, amount)
    return match.rule if match else None


def company_rules(db: Session, organization_id: uuid.UUID) -> list[CommodityRule]:
    return load_settings(db.get(Organization, organization_id)).commodity_rules


def categorise(
    db: Session, organization_id: uuid.UUID, text: str, amount: float | None = None
) -> int | None:
    rule = match_rule(company_rules(db, organization_id), text, amount)
    return rule.commodity_group_id if rule else None


@dataclass(frozen=True)
class RuleHit:
    rule: CommodityRule
    line: int
    flagged: bool
    hits: list[dict]
    keyword: str
    position: int
    text: str


def best_hit(rules: list[CommodityRule], lines: list[tuple[str, float | None]]) -> RuleHit | None:
    hits = []
    for number, (text, total) in enumerate(lines, start=1):
        match = match_line(rules, text, total)
        if match is not None:
            hits.append((number, total or 0, match, text))
    if not hits:
        return None
    number, _, match, text = max(hits, key=lambda hit: hit[1])
    return RuleHit(
        rule=match.rule,
        line=number,
        flagged=len({hit[2].rule.id for hit in hits}) > 1,
        hits=[{"line": n, "rule_id": hit_match.rule.id} for n, _, hit_match, _ in hits],
        keyword=match.keyword,
        position=match.position,
        text=text,
    )


def rule_for_lines(db: Session, organization_id: uuid.UUID, lines) -> RuleHit | None:
    return best_hit(
        company_rules(db, organization_id),
        [(line.position_description, float(line.total_price)) for line in lines],
    )


def commodity_block(
    db: Session,
    role: str,
    group_id: int | None,
    source: str,
    hit: RuleHit | None,
    corrected_from: int | None = None,
) -> CommodityOut:
    group = db.get(CommodityGroup, group_id) if group_id is not None else None
    return CommodityOut(
        group_id=group_id,
        group_name=group.name if group else None,
        source=source,
        rule_id=hit.rule.id if hit else None,
        rule_position=hit.position if hit else None,
        matched_keyword=hit.keyword if hit else None,
        matched_line=hit.text if hit else None,
        reason=hit.rule.reason if hit else None,
        locked=hit is not None and source == "rule",
        can_override=role in ("buyer", "admin"),
        corrected=corrected_from is not None,
        corrected_from_group_id=corrected_from,
    )
