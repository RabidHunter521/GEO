"""Triage a Truth Vault conflict using its client's industry pack.

This is where the pack system earns its keep: the same class of conflict means
different things in different industries. A wrong opening time is a nuisance
everywhere, but a wrong practitioner credential, a false halal status and a
false emergency-callout promise are not nuisances — someone acts on those.

What never varies is the KIND of output. Every result is a candidate for a
human reviewer, carrying an instruction about what to CHECK. Nothing here
concludes that a business broke a rule, and the pack validator enforces that at
import time so it cannot drift.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.industry_packs.base import IndustryPack, RiskRule, finding_severity_for

# Applied when a pack is in force but no rule addresses this fact. The pack
# author has told us this industry matters without telling us how much, so it
# sits above the unpacked default rather than being ignored.
_UNMATCHED_SEVERITY = "medium"
_UNMATCHED_INSTRUCTION = (
    "An AI answer conflicts with an approved fact that this industry pack has no "
    "specific rule for. Confirm the approved value and decide whether to request "
    "a correction."
)

# Preserved for clients with no reviewed pack: exactly the severity such
# findings have carried since the Truth Vault shipped, so adding packs cannot
# retroactively re-triage anyone's existing evidence.
_UNPACKED_SEVERITY = "low"
_UNPACKED_INSTRUCTION = (
    "An AI answer conflicts with an approved fact. Confirm the approved value "
    "and decide whether to request a correction."
)


@dataclass(frozen=True)
class PackRiskResult:
    """How one conflict should be triaged, and why."""

    severity: str
    finding_severity: str
    review_instruction: str
    rule_id: str | None
    pack_key: str | None
    pack_version: str | None
    provenance: str | None
    # Structural, not a flag anyone may set: a pack routes evidence to a human.
    needs_review: bool = True


def evaluate_pack_risk(pack: IndustryPack | None, conflict) -> PackRiskResult:
    """Return the pack-appropriate triage for one Truth Vault conflict.

    `conflict` is a TruthConflictCandidate (or anything exposing fact_type and
    fact_key). `pack=None` means the client has no reviewed pack.
    """
    if pack is None:
        return PackRiskResult(
            severity=_UNPACKED_SEVERITY,
            finding_severity=finding_severity_for(_UNPACKED_SEVERITY),
            review_instruction=_UNPACKED_INSTRUCTION,
            rule_id=None, pack_key=None, pack_version=None, provenance=None,
        )

    rule = _match_rule(pack, conflict.fact_type, conflict.fact_key)
    if rule is None:
        return PackRiskResult(
            severity=_UNMATCHED_SEVERITY,
            finding_severity=finding_severity_for(_UNMATCHED_SEVERITY),
            review_instruction=_UNMATCHED_INSTRUCTION,
            rule_id=None,
            pack_key=pack.key,
            pack_version=pack.version,
            provenance=_provenance(pack, None, _UNMATCHED_SEVERITY),
        )

    return PackRiskResult(
        severity=rule.severity,
        # `critical` cannot be stored on a finding, so it narrows here. The
        # unnarrowed severity survives in provenance, or the distinction the
        # pack draws would be lost the moment it is persisted.
        finding_severity=finding_severity_for(rule.severity),
        review_instruction=rule.review_instruction,
        rule_id=rule.id,
        pack_key=pack.key,
        pack_version=pack.version,
        provenance=_provenance(pack, rule.id, rule.severity),
    )


def _match_rule(pack: IndustryPack, fact_type: str, fact_key: str | None) -> RiskRule | None:
    """Most specific rule wins: an exact fact_key beats a type wildcard."""
    wildcard: RiskRule | None = None
    for rule in pack.risk_rules:
        if rule.fact_type != fact_type:
            continue
        if rule.fact_key == fact_key:
            return rule
        if rule.fact_key is None and wildcard is None:
            wildcard = rule
    return wildcard


def _provenance(pack: IndustryPack, rule_id: str | None, severity: str) -> str:
    """Which pack version and rule produced this triage.

    Stored in MisinformationFinding.rule_key, which is String(64) and is already
    interpreted by category — COMPLIANCE_RULES keys for prohibited_claim rows,
    this namespaced form for factual_error rows. Phase 4's migration contract is
    "client columns only", so provenance is a structured string rather than
    three new columns; the `pack:` prefix keeps the two vocabularies distinct.
    """
    value = f"pack:{pack.key}@{pack.version}:{rule_id or 'unmatched'}:{severity}"
    return value[:64]
