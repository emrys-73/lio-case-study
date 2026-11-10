import logging

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from app.models import CommodityGroup, Organization
from app.schemas.organizations import (
    CommodityRule,
    ConfigurableRequiredField,
    OrganizationSettings,
    OrganizationSettingsUpdate,
)

logger = logging.getLogger(__name__)

_required_field = TypeAdapter(ConfigurableRequiredField)


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

    return OrganizationSettings(required_fields=required_fields, commodity_rules=rules)


def save_settings(
    db: Session, org: Organization, update: OrganizationSettingsUpdate
) -> OrganizationSettings:
    changes = update.model_dump(exclude_unset=True, exclude_none=True)
    merged = OrganizationSettings.model_validate(
        {**load_settings(org).model_dump(), **changes}
    )
    missing = _unknown_groups(db, merged.commodity_rules)
    if missing:
        raise InvalidSettings(
            f"Unknown commodity group id: {', '.join(str(group) for group in missing)}"
        )
    org.settings = merged.model_dump(mode="json")
    return merged


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
