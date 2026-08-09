"""Build a client's scan queries from its industry pack and APPROVED facts.

The governing rule is that nothing is guessed. A placeholder is filled from an
approved, location-correct Truth Vault fact, or the template producing it is
dropped and logged. A scan is the measurement the client is judged on, so a
fabricated query would fabricate the measurement with it — and a leaked brace
would send "Where can I get {service} in KL?" to a live model.

Queries land in the scan engine's four existing categories (see
`base.category_for`); a fifth would silently fall out of position extraction,
diffing, digests and every report.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import structlog

from app.core.constants import (
    MAX_PACK_QUERIES_PER_SCAN,
    MAX_PACK_VALUES_PER_PLACEHOLDER,
)
from app.industry_packs.base import IndustryPack, QueryTemplate, category_for, placeholders_in

logger = structlog.get_logger()

# Which approved fact fills which placeholder, most specific first. Explicit
# rather than inferred: a placeholder whose sources are all missing drops its
# template, so a silent mis-mapping here would quietly shrink a client's scan.
_FACT_SOURCES: dict[str, tuple[tuple[str, str], ...]] = {
    "service":   (("treatment", "offered"), ("service", "catalog"),
                  ("service", "specialisations")),
    "specialty": (("specialty", "offered"), ("practitioner", "specialty")),
    "problem":   (("service", "catalog"), ("service", "specialisations")),
    "cuisine":   (("cuisine", "types"),),
    "dish":      (("menu", "signature_dishes"), ("menu", "items")),
    "occasion":  (("occasion", "suitable_for"),),
    "dietary":   (("dietary", "options"),),
    "subject":   (("programme", "offered"),),
    "level":     (("programme", "levels"),),
}

# Ordering used when the cap bites: keep what a buyer is closest to acting on.
_INTENT_RANK = {"high": 0, "medium": 1, "low": 2}
_STAGE_RANK = {"decision": 0, "consideration": 1, "awareness": 2}


@dataclass(frozen=True)
class ApprovedFact:
    """One approved Truth Vault value, flattened for query building.

    `location_id=None` means brand-wide and therefore applies to every location.
    """

    fact_type: str
    fact_key: str
    value: Any
    location_id: uuid.UUID | None = None


def approved_facts_for(client, db) -> list[ApprovedFact]:
    """Load brand-wide and per-active-location approved facts for a client.

    Delegates entirely to truth_vault_service, which already filters to
    approved-and-currently-effective versions and scopes each query to exactly
    one location, so no draft or retired value can reach a scan.
    """
    from app.models.business_location import BusinessLocation
    from app.services import truth_vault_service

    facts: list[ApprovedFact] = []
    scopes: list[uuid.UUID | None] = [None]
    scopes.extend(
        row.id
        for row in db.query(BusinessLocation)
        .filter(
            BusinessLocation.client_id == client.id,
            BusinessLocation.active.is_(True),
        )
        .order_by(BusinessLocation.created_at, BusinessLocation.id)
        .all()
    )
    for location_id in scopes:
        for version in truth_vault_service.current_facts(client.id, db, location_id=location_id):
            fact = version.truth_fact
            facts.append(
                ApprovedFact(
                    fact_type=fact.fact_type,
                    fact_key=fact.fact_key,
                    value=version.value_json,
                    location_id=location_id,
                )
            )
    return facts


def build_pack_queries(
    client,
    locations: Sequence[Any],
    facts: Iterable[ApprovedFact],
    pack: IndustryPack,
    competitors: Sequence[Any] = (),
) -> list[dict]:
    """Return scan-engine query dicts for a packed client.

    Shape matches the legacy builder exactly (category / query_text /
    competitor_id) so the scan engine consumes both identically.
    """
    facts = list(facts)
    active_locations = [loc for loc in locations if getattr(loc, "active", True)]
    scopes = _location_scopes(client, active_locations)
    subcategory = getattr(client, "industry_subcategory", None)

    built: list[dict] = []
    seen: set[str] = set()
    for template in pack.query_templates:
        if not _applies_to(template, subcategory):
            continue
        for scope in scopes:
            built.extend(
                _expand(template, pack, client, scope, facts, competitors, seen)
            )

    built.sort(
        key=lambda q: (
            _INTENT_RANK.get(q["commercial_intent"], 9),
            _STAGE_RANK.get(q["buyer_stage"], 9),
            # Specialisation has to survive the cap or it is decoration. Two
            # queries of equal intent and stage are not equally useful: the one
            # written for this exact kind of business is the whole reason the
            # subcategory exists, so it takes the slot.
            0 if q["subcategory_specific"] else 1,
            q["template_id"],
            q["query_text"],
        )
    )
    return built[:MAX_PACK_QUERIES_PER_SCAN]


def _applies_to(template: QueryTemplate, subcategory: str | None) -> bool:
    """Whether this template is built for a client of `subcategory`.

    An unscoped template applies to everyone. A scoped one applies only to the
    subcategories it names, so a client with no subcategory — or one the pack
    does not recognise — is measured on the generic set. Falling back to "all
    scoped templates" instead would ask a dental practice whether it needs a
    doctor's referral AND whether to fast beforehand.
    """
    if not template.subcategories:
        return True
    return isinstance(subcategory, str) and subcategory in template.subcategories


@dataclass(frozen=True)
class _Scope:
    """One place the client can be asked about."""

    location_id: uuid.UUID | None
    city: str | None
    region: str | None


def _location_scopes(client, active_locations: Sequence[Any]) -> list[_Scope]:
    """Places to build location queries for.

    Falls back to the client's own city/state when no locations exist, so a
    single-site client behaves exactly as it did before Phase 3.
    """
    if active_locations:
        return [
            _Scope(
                location_id=loc.id,
                city=_clean(getattr(loc, "city", None)),
                region=_region(getattr(loc, "city", None), getattr(loc, "state", None))
                or _region(client.city, client.state),
            )
            for loc in active_locations
        ]
    return [
        _Scope(
            location_id=None,
            city=_clean(getattr(client, "city", None))
            or _clean(getattr(client, "state", None))
            or _clean(getattr(client, "country", None)),
            region=_region(client.city, client.state)
            or _clean(getattr(client, "country", None)),
        )
    ]


def _expand(
    template: QueryTemplate,
    pack: IndustryPack,
    client,
    scope: _Scope,
    facts: list[ApprovedFact],
    competitors: Sequence[Any],
    seen: set[str],
) -> list[dict]:
    """Every filled variant of one template for one location scope."""
    used = placeholders_in(template.template)
    options: dict[str, list[str]] = {}

    for name in used:
        values = _values_for(name, client, scope, facts, competitors)
        if not values:
            # Structural, not exceptional: a client without the underlying
            # approved fact is simply not measured on that question.
            logger.debug(
                "pack_query_skipped_missing_placeholder",
                pack=pack.key, template=template.id, placeholder=name,
            )
            return []
        options[name] = values[:MAX_PACK_VALUES_PER_PLACEHOLDER]

    category = category_for(template)
    rows: list[dict] = []
    for combo in _combinations(options):
        text = template.template.format(**combo)
        if "{" in text or "}" in text or text in seen:
            continue
        seen.add(text)
        rows.append({
            "category": category,
            "query_text": text,
            "competitor_id": None,
            "template_id": template.id,
            "buyer_stage": template.buyer_stage,
            "commercial_intent": template.commercial_intent,
            "location_id": scope.location_id,
            "subcategory_specific": bool(template.subcategories),
        })
    return rows


def _values_for(
    name: str,
    client,
    scope: _Scope,
    facts: list[ApprovedFact],
    competitors: Sequence[Any],
) -> list[str]:
    if name == "brand":
        return [v for v in [_clean(client.name)] if v]
    if name == "industry":
        return [v for v in [_clean(client.industry)] if v]
    if name == "competitor":
        return [v for v in (_clean(getattr(c, "name", None)) for c in competitors) if v]
    if name in ("city", "area"):
        return [scope.city] if scope.city else []
    if name == "location":
        return [scope.region] if scope.region else []
    return _fact_values(name, scope, facts)


def _fact_values(name: str, scope: _Scope, facts: list[ApprovedFact]) -> list[str]:
    """Approved values for a fact-backed placeholder, location-correct.

    A fact belongs to this scope when it is brand-wide (location_id None) or
    approved for exactly this location. Anything approved for a DIFFERENT
    location is invisible here — that is the cross-location leak guard.
    """
    for fact_type, fact_key in _FACT_SOURCES.get(name, ()):
        values: list[str] = []
        for fact in facts:
            if fact.fact_type != fact_type or fact.fact_key != fact_key:
                continue
            if fact.location_id is not None and fact.location_id != scope.location_id:
                continue
            values.extend(_flatten(fact.value))
        if values:
            # Stable order so the cap and dedupe are reproducible.
            return sorted(dict.fromkeys(values))
    return []


def _combinations(options: dict[str, list[str]]) -> list[dict[str, str]]:
    combos: list[dict[str, str]] = [{}]
    for name in sorted(options):
        combos = [
            {**combo, name: value} for combo in combos for value in options[name]
        ]
    return combos


def _flatten(value: Any) -> list[str]:
    """Usable strings from an approved value, dropping blanks.

    An approved-but-empty fact is treated as absent rather than rendered, so a
    client never gets "Where can I get  in Kuala Lumpur?".
    """
    items = value if isinstance(value, (list, tuple)) else [value]
    out: list[str] = []
    for item in items:
        if isinstance(item, bool) or item is None:
            continue
        cleaned = _clean(item if isinstance(item, str) else str(item))
        if cleaned:
            out.append(cleaned)
    return out


def _clean(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    collapsed = " ".join(value.split())
    return collapsed or None


def _region(city: Any, state: Any) -> str | None:
    city, state = _clean(city), _clean(state)
    if city and state:
        return f"{city}, {state}"
    return city or state


def pack_context_for(client, db=None):
    """(pack, approved_facts) for prompt building, or (None, ()) when unpacked.

    `db` is optional because the content services differ: the brief and roadmap
    hold a session, while content_analysis does not. When none is given this
    opens its own, the same fallback cost_tracker.record_llm_usage already uses
    for exactly this situation.

    Best-effort by design. A Truth Vault read failing must degrade the prompt to
    the unspecialised version, never stop content generation — and it must never
    raise into a caller whose except block would log it as a generation failure.
    """
    from app.industry_packs import registry as pack_registry

    pack = pack_registry.find_pack(getattr(client, "industry_pack", None))
    if pack is None:
        return None, ()
    try:
        if db is not None:
            return pack, approved_facts_for(client, db)
        from app.core.database import SessionLocal

        with SessionLocal() as session:
            return pack, approved_facts_for(client, session)
    except Exception as exc:
        logger.warning(
            "pack_context_unavailable", client_id=str(client.id), error=str(exc)
        )
        return pack, ()
