"""Typed contracts for industry intelligence packs.

A pack specializes the horizontal platform — which buyer queries a client is
scanned on, which business facts matter, how an accuracy conflict is triaged,
and which sources are trusted — WITHOUT forking it. Pack-specific business data
lives in the shared Truth Vault, never in pack-specific tables.

Definitions are frozen and code-versioned. `validate_pack` runs at import time
so a malformed pack fails fast with a named reason, rather than quietly
producing wrong queries or wrong risk severities during a scan.
"""
from __future__ import annotations

import re
import string
from dataclasses import dataclass
from typing import Literal

VALUE_TYPES = ("text", "boolean", "number", "url", "list", "hours")
SCOPES = ("brand", "location", "either")
BUYER_STAGES = ("awareness", "consideration", "decision")
COMMERCIAL_INTENTS = ("low", "medium", "high")
RISK_SEVERITIES = ("critical", "high", "medium", "low")

# Pack severities are deliberately a SUPERSET of the client-facing finding
# vocabulary: "critical" lets a healthcare credential conflict outrank an F&B
# opening-hours conflict during triage, which is the whole point of per-pack
# risk routing.
#
# The mapping below MUST stay total. `misinformation_service` drops any
# candidate whose severity is outside MISINFORMATION_SEVERITIES — quietly, with
# only a log line (see its bad-enum guard) — so an unmapped pack severity would
# make the highest-stakes rule in the product silently produce nothing. The
# original pack severity is preserved in the rule provenance stored alongside
# the finding, so triage ordering is not lost by this narrowing.
FINDING_SEVERITY_BY_RISK_SEVERITY = {
    "critical": "high",
    "high": "high",
    "medium": "medium",
    "low": "low",
}


def finding_severity_for(risk_severity: str) -> str:
    """Narrow a pack risk severity to the client-facing finding vocabulary."""
    try:
        return FINDING_SEVERITY_BY_RISK_SEVERITY[risk_severity]
    except KeyError:
        raise ValueError(
            f"unmapped pack risk severity {risk_severity!r}; every member of "
            "RISK_SEVERITIES must map to a MISINFORMATION_SEVERITIES value or "
            "findings created from it are silently discarded"
        ) from None

# Placeholders a query template may use. Task 6 fills these from APPROVED facts
# and active locations only; anything not in this allowlist is a typo that would
# otherwise reach a model as a literal brace.
ALLOWED_PLACEHOLDERS = frozenset({
    "brand", "service", "specialty", "city", "location", "area",
    "competitor", "industry", "cuisine", "dish", "occasion", "dietary", "problem",
})
# Placeholders that need a real location to expand. A template using one must
# declare location_required, so a client with no location is skipped instead of
# being scanned on "best clinic in {city}".
LOCATION_PLACEHOLDERS = frozenset({"city", "location", "area"})

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")

# schema.org types are PascalCase identifiers. Anything else — a space, a
# hyphen, a stray trailing space — becomes an invalid @type in a JSON-LD file
# the client publishes on their own site, where nothing of ours will catch it.
_SCHEMA_TYPE = re.compile(r"^[A-Z][A-Za-z0-9]*$")

# A pack routes evidence to a human reviewer. It never adjudicates legality:
# SeenBy is not a regulator and cannot substantiate a claim that a business is
# breaking a rule. Instructions must describe what to CHECK, not what is true.
_PROHIBITED_CLAIM_TERMS = (
    "illegal", "illegally", "unlicensed", "unlawful", "non-compliant",
    "noncompliant", "violation", "violates", "breach", "breaches",
    "prosecut", "compliant",
)


@dataclass(frozen=True)
class TruthFieldDefinition:
    """A business fact this pack cares about, stored in the shared Truth Vault.

    `fact_type` and `key` are the TruthFact model's `fact_type`/`fact_key`
    verbatim, which is what lets a pack's declared fields, its risk rules, and
    real Truth Vault rows all address the same thing. Uniqueness is on the pair:
    different types may legitimately reuse a key (`practitioner.name` and
    `facility.name`).
    """

    key: str
    label: str
    value_type: Literal["text", "boolean", "number", "url", "list", "hours"]
    scope: Literal["brand", "location", "either"]
    fact_type: str = "business"
    # Risk-sensitive facts require a source URL and reviewer approval before any
    # surface may repeat them.
    risk_sensitive: bool = False
    required: bool = False


@dataclass(frozen=True)
class QueryTemplate:
    """A buyer question, expanded from approved facts only."""

    id: str
    template: str
    buyer_stage: Literal["awareness", "consideration", "decision"]
    commercial_intent: Literal["low", "medium", "high"]
    location_required: bool


@dataclass(frozen=True)
class RiskRule:
    """Routes a Truth Vault conflict to review at a pack-appropriate severity.

    `fact_key = None` matches any key of that fact_type.
    """

    id: str
    fact_type: str
    fact_key: str | None
    severity: Literal["critical", "high", "medium", "low"]
    review_instruction: str


@dataclass(frozen=True)
class TrustedSourceType:
    key: str
    label: str


@dataclass(frozen=True)
class SchemaProfile:
    """Which schema.org type the AI Readiness Toolkit publishes for this pack.

    This is the one pack axis whose output leaves our surfaces entirely: the
    client copies `schema.json` onto their own site. The generator previously
    keyword-matched free-text `client.industry` and fell back to
    `LocalBusiness`, so a dental practice whose industry read "aesthetics" got
    generic markup. The pack knows better and says so here.

    `guidance` lines are appended verbatim to the schema prompt. Keep them about
    STRUCTURE (which properties this business type should carry), never about
    facts — the prompt's never-invent rules still govern content.
    """

    default_type: str
    # (subcategory, schema.org type). A subcategory with no entry uses the
    # default; a subcategory that does not exist on the pack is a typo and is
    # rejected, because it would silently never match.
    subcategory_types: tuple[tuple[str, str], ...] = ()
    guidance: tuple[str, ...] = ()

    def type_for(self, subcategory: str | None) -> str:
        for key, schema_type in self.subcategory_types:
            if key == subcategory:
                return schema_type
        return self.default_type


@dataclass(frozen=True)
class AuthorityTarget:
    """An authority asset that only matters for this pack.

    Merged into the shared AUTHORITY_ASSET_CATALOG so the picker, the add
    resolver and the provenance-to-catalog mapping all see one namespace.
    Keys must therefore be globally unique, which `validate_pack` enforces.
    """

    key: str
    name: str
    asset_type: str
    provenance_domain: str | None = None
    url_hint: str | None = None


@dataclass(frozen=True)
class IndustryPack:
    key: str
    version: str
    label: str
    # How the report names this pack's reviewed facts, e.g. "Practitioner and
    # treatment facts reviewed". Lives on the pack so report wording is pack
    # CONFIGURATION rather than a chain of `if industry` branches in the
    # template — the plan's explicit requirement.
    report_fact_label: str
    subcategories: tuple[str, ...]
    truth_fields: tuple[TruthFieldDefinition, ...]
    query_templates: tuple[QueryTemplate, ...]
    risk_rules: tuple[RiskRule, ...]
    trusted_sources: tuple[TrustedSourceType, ...]
    # Optional on the contract so the registry's fixture packs stay small; a
    # test asserts every REGISTERED pack declares one, because a real pack
    # without a profile publishes LocalBusiness for a dental clinic.
    schema_profile: SchemaProfile | None = None
    # Authority assets this pack adds to the shared catalog…
    authority_targets: tuple[AuthorityTarget, ...] = ()
    # …and the asset keys (shared or pack-added) that matter most for it, which
    # is what floats them to the top of the admin's picker.
    priority_asset_keys: tuple[str, ...] = ()


def placeholders_in(template: str) -> set[str]:
    """Named placeholders used by a template, ignoring literal text."""
    return {
        name
        for _, name, _, _ in string.Formatter().parse(template)
        if name
    }


def category_for(template: QueryTemplate) -> str:
    """Map a pack query onto the scan engine's four existing categories.

    Every consumer of a scan partitions by `category` — position extraction only
    runs on the ranked ones, and diffing, digests, reports and the client view
    all group by it. A fifth category would silently fall out of all of them, so
    pack queries must land in the existing four.

    The mapping is by PLACEHOLDER ANCHOR, never by reading the English:
    whichever entity the question is pinned to is what the question is about.
    That reproduces the legacy templates' own semantics — `{brand} vs
    {competitor}` is comparison, `Best {industry} in {location}` is
    recommendation, `... near me in {city}` is local.
    """
    used = placeholders_in(template.template)
    if "competitor" in used:
        return "comparison"
    if "brand" in used:
        return "brand"
    if used & {"city", "area"}:
        return "local"
    return "recommendation"


def validate_pack(pack: IndustryPack) -> None:
    """Raise ValueError with a named reason if the pack is malformed."""
    # Imported here rather than at module scope so `base` stays importable by
    # the schema layer's tests without dragging in app config.
    from app.core.constants import INDUSTRY_PACK_KEYS

    if pack.key not in INDUSTRY_PACK_KEYS:
        raise ValueError(
            f"unsupported pack key {pack.key!r}; expected one of {INDUSTRY_PACK_KEYS}"
        )
    if not _SEMVER.match(pack.version or ""):
        raise ValueError(f"pack {pack.key}: version {pack.version!r} must be MAJOR.MINOR.PATCH")
    if not pack.label.strip():
        raise ValueError(f"pack {pack.key}: label is required")
    if not pack.report_fact_label.strip():
        raise ValueError(f"pack {pack.key}: report_fact_label is required")

    if not pack.subcategories:
        raise ValueError(f"pack {pack.key}: at least one subcategory is required")
    _reject_duplicates(pack.subcategories, f"pack {pack.key}: duplicate subcategory")

    _reject_duplicates(
        [(f.fact_type, f.key) for f in pack.truth_fields],
        f"pack {pack.key}: duplicate truth field",
    )
    _reject_duplicates(
        [t.id for t in pack.query_templates], f"pack {pack.key}: duplicate query template"
    )
    _reject_duplicates([r.id for r in pack.risk_rules], f"pack {pack.key}: duplicate risk rule")
    _reject_duplicates(
        [s.key for s in pack.trusted_sources], f"pack {pack.key}: duplicate trusted source"
    )

    for field in pack.truth_fields:
        if field.value_type not in VALUE_TYPES:
            raise ValueError(
                f"pack {pack.key}: truth field {field.key!r} has unsupported "
                f"value_type {field.value_type!r}"
            )
        if field.scope not in SCOPES:
            raise ValueError(
                f"pack {pack.key}: truth field {field.key!r} has unsupported "
                f"scope {field.scope!r}"
            )

    for template in pack.query_templates:
        _validate_template(pack.key, template)

    declared_types = {f.fact_type for f in pack.truth_fields}
    declared_pairs = {(f.fact_type, f.key) for f in pack.truth_fields}
    for rule in pack.risk_rules:
        _validate_risk_rule(pack.key, rule, declared_types, declared_pairs)

    if pack.schema_profile is not None:
        _validate_schema_profile(pack.key, pack.schema_profile, set(pack.subcategories))
    _validate_authority(pack)


def _validate_schema_profile(
    pack_key: str, profile: SchemaProfile, subcategories: set[str]
) -> None:
    if not profile.default_type.strip():
        raise ValueError(f"pack {pack_key}: schema profile needs a default_type")

    _reject_duplicates(
        [sub for sub, _ in profile.subcategory_types],
        f"pack {pack_key}: duplicate schema override for subcategory",
    )
    for schema_type in [profile.default_type, *(t for _, t in profile.subcategory_types)]:
        if not _SCHEMA_TYPE.match(schema_type):
            raise ValueError(
                f"pack {pack_key}: {schema_type!r} is not a valid schema.org type "
                "(expected a PascalCase identifier such as 'MedicalClinic')"
            )
    for sub, _ in profile.subcategory_types:
        if sub not in subcategories:
            raise ValueError(
                f"pack {pack_key}: schema override names {sub!r}, but the pack "
                "declares no subcategory by that name, so it could never match"
            )


def _validate_authority(pack: IndustryPack) -> None:
    """Pack authority targets share one key namespace with the global catalog.

    Imported here rather than at module scope for the same reason as
    INDUSTRY_PACK_KEYS above: `base` must stay importable without app config.
    """
    from app.core.constants import AUTHORITY_ASSET_CATALOG, AUTHORITY_ASSET_TYPES

    shared_keys = {item["key"] for item in AUTHORITY_ASSET_CATALOG}

    _reject_duplicates(
        [t.key for t in pack.authority_targets],
        f"pack {pack.key}: duplicate authority target",
    )
    for target in pack.authority_targets:
        if target.key in shared_keys:
            raise ValueError(
                f"pack {pack.key}: authority target {target.key!r} is already in the "
                "shared authority catalog; use priority_asset_keys to promote it instead"
            )
        if not target.name.strip():
            raise ValueError(
                f"pack {pack.key}: authority target {target.key!r} needs a name"
            )
        if target.asset_type not in AUTHORITY_ASSET_TYPES:
            raise ValueError(
                f"pack {pack.key}: authority target {target.key!r} has unsupported "
                f"asset_type {target.asset_type!r}; expected one of {AUTHORITY_ASSET_TYPES}"
            )

    _reject_duplicates(
        list(pack.priority_asset_keys),
        f"pack {pack.key}: duplicate priority authority asset",
    )
    known = shared_keys | {t.key for t in pack.authority_targets}
    for key in pack.priority_asset_keys:
        if key not in known:
            raise ValueError(
                f"pack {pack.key}: priority list names unknown authority asset {key!r}"
            )


def _validate_template(pack_key: str, template: QueryTemplate) -> None:
    used = placeholders_in(template.template)
    unknown = used - ALLOWED_PLACEHOLDERS
    if unknown:
        raise ValueError(
            f"pack {pack_key}: query {template.id!r} uses unknown "
            f"placeholder(s) {sorted(unknown)}"
        )
    if template.buyer_stage not in BUYER_STAGES:
        raise ValueError(
            f"pack {pack_key}: query {template.id!r} has unsupported "
            f"buyer_stage {template.buyer_stage!r}"
        )
    if template.commercial_intent not in COMMERCIAL_INTENTS:
        raise ValueError(
            f"pack {pack_key}: query {template.id!r} has unsupported "
            f"commercial_intent {template.commercial_intent!r}"
        )

    needs_location = bool(used & LOCATION_PLACEHOLDERS)
    if needs_location and not template.location_required:
        raise ValueError(
            f"pack {pack_key}: query {template.id!r} uses a location placeholder but "
            "does not set location_required, so it would be built for clients with no location"
        )
    if template.location_required and not needs_location:
        raise ValueError(
            f"pack {pack_key}: query {template.id!r} sets location_required but uses no "
            "location placeholder, so it would be skipped for no reason"
        )


def _validate_risk_rule(
    pack_key: str,
    rule: RiskRule,
    declared_types: set[str],
    declared_pairs: set[tuple[str, str]],
) -> None:
    # A rule addressing a fact the pack never declares can never match anything,
    # so it would look like coverage while providing none. Typos in a fact_key
    # are exactly this failure and are invisible at runtime.
    if rule.fact_type not in declared_types:
        raise ValueError(
            f"pack {pack_key}: risk rule {rule.id!r} targets fact_type "
            f"{rule.fact_type!r}, which no truth field declares"
        )
    if rule.fact_key is not None and (rule.fact_type, rule.fact_key) not in declared_pairs:
        raise ValueError(
            f"pack {pack_key}: risk rule {rule.id!r} targets "
            f"{rule.fact_type}.{rule.fact_key}, which no truth field declares"
        )
    if rule.severity not in RISK_SEVERITIES:
        raise ValueError(
            f"pack {pack_key}: risk rule {rule.id!r} has unsupported severity {rule.severity!r}"
        )
    if not rule.fact_type.strip():
        raise ValueError(f"pack {pack_key}: risk rule {rule.id!r} needs a fact_type")
    if not rule.review_instruction.strip():
        raise ValueError(f"pack {pack_key}: risk rule {rule.id!r} needs a review_instruction")

    lowered = rule.review_instruction.lower()
    hit = next((term for term in _PROHIBITED_CLAIM_TERMS if term in lowered), None)
    if hit is not None:
        raise ValueError(
            f"pack {pack_key}: risk rule {rule.id!r} may not assert a legal or regulatory "
            f"conclusion (found {hit!r}). Describe what a reviewer should CHECK instead."
        )


def _reject_duplicates(values, message: str) -> None:
    seen: set = set()
    for value in values:
        if value in seen:
            raise ValueError(f"{message} {value!r}")
        seen.add(value)
