from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from openai import OpenAI

from app.core.config import settings
from app.data.commodity_groups import COMMODITY_GROUPS
from app.services.catalogue_search import Catalogue, rank

log = logging.getLogger(__name__)

SHORTLIST_SIZE = 15
TIMEOUT_SECONDS = 8.0
NONE = "NONE"
DEFAULT_IDS = (15, 43, 31, 30, 29, 11, 17, 9)
CACHE_LIMIT = 256

BASE_GROUPS: list[tuple[int, str, str]] = [g for g in COMMODITY_GROUPS if " — " not in g[2]]
_BY_LABEL = {f"{category} {name}": (group_id, category, name) for group_id, category, name in BASE_GROUPS}
_BY_ID = {group_id: (group_id, category, name) for group_id, category, name in BASE_GROUPS}
_CATALOGUE: Catalogue | None = None

SYSTEM_PROMPT = (
    "You classify purchase request lines into one commodity group. Answer only with an "
    "alias from the shortlist, or NONE when no group fits."
)


@dataclass(frozen=True)
class Suggestion:
    group_id: int
    reason: str


_CACHE: dict[str, Suggestion | None] = {}


def _catalogue() -> Catalogue:
    global _CATALOGUE
    if _CATALOGUE is None:
        _CATALOGUE = Catalogue(list(_BY_LABEL))
    return _CATALOGUE


def _normalise(descriptions: list[str]) -> str:
    return " | ".join(" ".join(d.lower().split()) for d in descriptions if d and d.strip())


def shortlist(text: str, size: int = SHORTLIST_SIZE) -> list[tuple[int, str, str]]:
    picked = [_BY_LABEL[label] for label, _ in rank(_catalogue(), text)[:size]]
    seen = {group[0] for group in picked}
    for group_id in DEFAULT_IDS:
        if len(picked) >= size:
            break
        if group_id not in seen and group_id in _BY_ID:
            picked.append(_BY_ID[group_id])
            seen.add(group_id)
    return picked


def _prompt(descriptions: list[str], aliases: dict[str, tuple[int, str, str]]) -> str:
    lines = "\n".join(f"- {d.strip()}" for d in descriptions if d and d.strip())
    groups = "\n".join(f"{alias}: {category}, {name}" for alias, (_, category, name) in aliases.items())
    return f"""Pick the single commodity group that best fits this purchase request. The lines may be German.

Request lines:
{lines}

Shortlist:
{groups}
NONE: none of these fit

Consider the PRIMARY nature and purpose of the items:
  * Branded office decor or furniture is Office Equipment
  * Traditional promotional items (brochures, giveaways, banners) are Promotional Materials
  * Software and IT products are Software or IT Services
  * If genuinely uncertain, answer NONE

Answer with the alias and a short reason (one sentence)."""


def _schema(aliases: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "group": {"type": "string", "enum": [*aliases, NONE]},
            "reason": {"type": "string"},
        },
        "required": ["group", "reason"],
        "additionalProperties": False,
    }


def _ask(descriptions: list[str], groups: list[tuple[int, str, str]]) -> Suggestion | None:
    aliases = {f"G{n}": group for n, group in enumerate(groups, start=1)}
    client = OpenAI(api_key=settings.openai_api_key, timeout=TIMEOUT_SECONDS, max_retries=0)
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _prompt(descriptions, aliases)},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "commodity_group", "strict": True, "schema": _schema(list(aliases))},
        },
        max_completion_tokens=200,
        temperature=0,
    )
    reply = json.loads(response.choices[0].message.content or "{}")
    group = aliases.get(reply.get("group"))
    if group is None:
        return None
    return Suggestion(group_id=group[0], reason=str(reply.get("reason") or "").strip()[:300])


def classify(descriptions: list[str]) -> Suggestion | None:
    key = _normalise(descriptions)
    if not key or not settings.openai_api_key:
        return None
    if key in _CACHE:
        return _CACHE[key]
    try:
        groups = shortlist(key)
        if not groups:
            return None
        suggestion = _ask(descriptions, groups)
    except Exception:
        log.warning("commodity classifier failed, no suggestion", exc_info=True)
        return None
    if len(_CACHE) >= CACHE_LIMIT:
        _CACHE.clear()
    _CACHE[key] = suggestion
    log.info("commodity classifier %s -> %s", key[:120], suggestion.group_id if suggestion else NONE)
    return suggestion
