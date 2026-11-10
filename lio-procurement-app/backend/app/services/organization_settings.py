import logging
import secrets
from datetime import datetime, timezone

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from app.models import CommodityGroup, Organization
from app.schemas.organizations import (
    ApprovalLimit,
    CommodityRule,
    CommodityRuleIn,
    ConfigurableRequiredField,
    OrganizationSettings,
    OrganizationSettingsUpdate,
)
from app.services.keywords import words

logger = logging.getLogger(__name__)

_required_field = TypeAdapter(ConfigurableRequiredField)
_approval_limit = TypeAdapter(ApprovalLimit | None)


class InvalidSettings(ValueError):
    pass


def load_settings(org: Organization | None) -> OrganizationSettings:
    if org is None:
        return OrganizationSettings()
    raw = org.settings if isinstance(org.settings, dict) else {}
    for key in sorted(raw.keys() - OrganizationSettings.model_fields.keys()):
        logger.warning("Organization %s settings: skipped unknown key %r", org.id, key)

    required_fields = []
    for value in _as_list(org, raw, "required_fields"):
        try:
            required_fields.append(_required_field.validate_python(value))
        except ValidationError:
            logger.warning(
                "Organization %s settings: skipped unknown required field %r", org.id, value
            )

    rules = []
    for index, value in enumerate(_as_list(org, raw, "commodity_rules")):
        try:
            rules.append(CommodityRule.model_validate(value))
        except ValidationError as error:
            logger.warning(
                "Organization %s settings: skipped invalid commodity rule %d: %s",
                org.id,
                index,
                error,
            )

    session = object_session(org)
    if session is not None:
        missing = set(_unknown_groups(session, rules))
        for rule in rules:
            if rule.commodity_group_id in missing:
                logger.warning(
                    "Organization %s settings: skipped commodity rule %s, group %s does not exist",
                    org.id,
                    rule.keywords,
                    rule.commodity_group_id,
                )
        rules = [rule for rule in rules if rule.commodity_group_id not in missing]

    return OrganizationSettings(
        required_fields=required_fields,
        commodity_rules=rules,
        approval_limit=_read_approval_limit(org, raw),
    )


def _read_approval_limit(org: Organization, raw: dict) -> float | None:
    value = raw.get("approval_limit")
    try:
        return _approval_limit.validate_python(value)
    except ValidationError:
        logger.warning(
            "Organization %s settings: skipped approval_limit %r, not a positive number",
            org.id,
            value,
        )
        return None


_RULE_CONTENT = {"keywords", "commodity_group_id", "reason", "max_amount"}


def new_rule_id() -> str:
    return f"r_{secrets.token_hex(4)}"


def save_settings(
    db: Session, org: Organization, update: OrganizationSettingsUpdate, actor: str
) -> OrganizationSettings:
    current = load_settings(org)
    changes = update.model_dump(exclude_unset=True, exclude_none=True)
    if "approval_limit" in update.model_fields_set:
        changes["approval_limit"] = update.approval_limit
    if update.commodity_rules is not None:
        changes["commodity_rules"] = [
            rule.model_dump()
            for rule in _stamp_rules(current.commodity_rules, update.commodity_rules, actor)
        ]
    merged = OrganizationSettings.model_validate({**current.model_dump(), **changes})
    missing = _unknown_groups(db, merged.commodity_rules)
    if missing:
        raise InvalidSettings(
            f"Unknown commodity group id: {', '.join(str(group) for group in missing)}"
        )
    org.settings = merged.model_dump(mode="json")
    return merged


def _stamp_rules(
    existing: list[CommodityRule], incoming: list[CommodityRuleIn], actor: str
) -> list[CommodityRule]:
    by_id = {rule.id: rule for rule in existing}
    seen: set[str] = set()
    now = datetime.now(timezone.utc)
    stamped = []
    for rule in incoming:
        if rule.id is not None and rule.id not in by_id:
            raise InvalidSettings(f"Unknown rule id: {rule.id}")
        if rule.id in seen:
            raise InvalidSettings(f"Rule id used twice: {rule.id}")
        if rule.id is not None:
            seen.add(rule.id)
        empty = [keyword for keyword in rule.keywords if not words(keyword)]
        if empty:
            raise InvalidSettings(f"Keywords need letters or digits: {empty}")
        content = rule.model_dump(include=_RULE_CONTENT)
        old = by_id.get(rule.id)
        if old is not None and old.model_dump(include=_RULE_CONTENT) == content:
            stamped.append(old)
            continue
        stamped.append(
            CommodityRule(id=rule.id or new_rule_id(), updated_by=actor, updated_at=now, **content)
        )
    return stamped


def _as_list(org: Organization, raw: dict, key: str) -> list:
    value = raw.get(key, [])
    if isinstance(value, list):
        return value
    logger.warning("Organization %s settings: skipped %s, not a list", org.id, key)
    return []


def _unknown_groups(db: Session, rules: list[CommodityRule]) -> list[int]:
    wanted = {rule.commodity_group_id for rule in rules}
    if not wanted:
        return []
    found = set(db.scalars(select(CommodityGroup.id).where(CommodityGroup.id.in_(wanted))))
    return sorted(wanted - found)
