# backend/app/services/misinformation_service.py
"""AI misinformation / advertising-risk findings (Spec 8).

The one rule that makes this feature trustworthy: a finding cannot exist unless
its `quote` appears verbatim in the stored response it came from. Claude
proposes candidates; `quote_in_response` is the firewall that drops anything
fabricated before it can be stored. Rejected candidates are logged, never saved.

Everything is admin-gated: detection writes status="suggested", and nothing
below "confirmed" reaches a client surface — an unreviewed "AI is lying about
you" claim would itself be misinformation.

See docs/superpowers/specs/2026-07-19-misinformation-compliance-design.md.
"""
import json
import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy.orm import Session

from app.core.constants import (
    COMPLIANCE_RULES,
    MISINFORMATION_CATEGORIES,
    MISINFORMATION_MAX_ROWS_PER_SCAN,
    MISINFORMATION_SEVERITIES,
)
from app.core.time import utcnow
from app.models.client import Client
from app.models.misinformation_finding import MisinformationFinding
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.prompts.misinformation import build_detection
from app.services.claude_client import MODEL, anthropic_client, strip_code_fences
from app.services.cost_tracker import record_llm_call
from app.services.truth_comparison_service import TruthConflictCandidate

logger = structlog.get_logger()


@dataclass(frozen=True)
class Candidate:
    quote: str
    category: str
    rule_key: str | None
    severity: str
    explanation: str


def normalize_ws(text: str) -> str:
    """Collapse whitespace runs to single spaces and strip.

    AI answers wrap and indent unpredictably, so a quote that is correct in
    substance can differ from the source by line breaks alone. Comparing
    normalized forms keeps the firewall strict about words and forgiving about
    layout.
    """
    return " ".join(text.split())


def quote_in_response(quote: str | None, response_text: str | None) -> bool:
    """True when `quote` is a verbatim (whitespace-normalized) substring of
    `response_text`. This is the fabrication firewall — never relax it."""
    if not quote or not response_text:
        return False
    needle = normalize_ws(quote)
    if not needle:
        return False
    return needle in normalize_ws(response_text)


def parse_candidates(raw_json: str) -> list[Candidate]:
    """Parse Claude's JSON array into candidates, dropping anything malformed.

    Enum values are checked against the constants and `rule_key` against
    COMPLIANCE_RULES, so Claude cannot invent a category, a severity, or a
    regulation. Returns [] on any parse failure — the caller treats a failed
    detection as "nothing found", never as an error worth failing a scan over.
    """
    try:
        parsed = json.loads(strip_code_fences(raw_json))
    except (ValueError, TypeError):
        logger.warning("misinformation_parse_failed")
        return []
    if not isinstance(parsed, list):
        logger.warning("misinformation_parse_not_a_list")
        return []

    kept: list[Candidate] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        quote = (item.get("quote") or "").strip()
        category = item.get("category")
        severity = item.get("severity")
        explanation = (item.get("explanation") or "").strip()
        rule_key = item.get("rule_key") or None

        if not quote or not explanation:
            continue
        if category not in MISINFORMATION_CATEGORIES or severity not in MISINFORMATION_SEVERITIES:
            logger.warning("misinformation_candidate_bad_enum", category=category, severity=severity)
            continue
        if rule_key is not None and rule_key not in COMPLIANCE_RULES:
            logger.warning("misinformation_candidate_unknown_rule", rule_key=rule_key)
            continue
        if category == "prohibited_claim" and rule_key is None:
            # A prohibited-claim flag must name which checklist rule it breaks,
            # otherwise it is an opinion rather than a reviewed rule match.
            logger.warning("misinformation_candidate_missing_rule")
            continue
        kept.append(Candidate(
            quote=quote, category=category, rule_key=rule_key,
            severity=severity, explanation=explanation,
        ))
    return kept


def _call_claude(client: Client, result: ScanQueryResult, db: Session | None = None) -> str:
    """The only Claude seam in this module — tests mock this."""
    prompt = build_detection(client, result.query_text, result.response_text or "")
    response = anthropic_client().messages.create(
        model=MODEL,
        max_tokens=1024,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    record_llm_call(
        service="misinformation_detection",
        model=MODEL,
        response=response,
        client_id=client.id,
        db=db,
    )
    if getattr(response, "stop_reason", None) == "max_tokens":
        # Truncated JSON parses as garbage; log distinctly so it isn't mistaken
        # for a clean "nothing found" result.
        logger.warning("misinformation_response_truncated", result_id=str(result.id))
    return response.content[0].text.strip()


# A quote already sitting in any of these statuses is not re-proposed: the admin
# has either not looked yet, accepted it, or judged it a non-issue. Only
# "verified_fixed" is absent — a statement we already corrected coming back is a
# regression, and deserves a fresh finding.
_DEDUPE_BLOCKING_STATUSES = (
    "suggested", "confirmed", "dismissed", "corrected", "candidate_fixed",
)


def _rows_to_examine(scan_id: uuid.UUID, db: Session) -> list[ScanQueryResult]:
    """Client-owned, non-control rows worth a compliance pass, capped.

    A response can be visible AND non-compliant, so brand-mentioned rows are
    examined too — but that is up to ~80 rows on a 4-platform client, so the
    fan-out is bounded. Admin-flagged hallucinations always go first: they are
    the rows a human already suspects.
    """
    rows = (
        db.query(ScanQueryResult)
        .filter(
            ScanQueryResult.scan_id == scan_id,
            ScanQueryResult.competitor_id.is_(None),
            ScanQueryResult.is_control.is_(False),
            ScanQueryResult.response_text.isnot(None),
        )
        .all()
    )
    relevant = [
        r for r in rows
        if (r.hallucination_flagged or r.brand_detected)
        # Defensive: Pitch Mode (spec 6) will add is_pitch; those scans are sales
        # demos and must never create findings.
        and not getattr(r, "is_pitch", False)
    ]
    relevant.sort(key=lambda r: (not r.hallucination_flagged, r.platform, str(r.id)))
    return relevant[:MISINFORMATION_MAX_ROWS_PER_SCAN]


def detect(scan_id: uuid.UUID, db: Session) -> int:
    """Examine a completed scan's responses and store candidate findings.

    Returns the number of findings stored. Never raises: this runs post-commit
    inside the scan flow, where a compliance miss must never undo a good scan.
    """
    stored = 0
    try:
        scan = db.get(Scan, scan_id)
        if scan is None:
            return 0
        client = db.get(Client, scan.client_id)
        if client is None:
            return 0

        # Quotes already on the books for this client, normalized for comparison.
        seen_quotes = {
            normalize_ws(q)
            for (q,) in db.query(MisinformationFinding.quote).filter(
                MisinformationFinding.client_id == client.id,
                MisinformationFinding.status.in_(_DEDUPE_BLOCKING_STATUSES),
            ).all()
        }

        for result in _rows_to_examine(scan_id, db):
            try:
                raw = _call_claude(client, result, db)
            except Exception as exc:
                logger.warning(
                    "misinformation_call_failed", result_id=str(result.id), error=str(exc)
                )
                continue

            for candidate in parse_candidates(raw):
                if not quote_in_response(candidate.quote, result.response_text):
                    # The firewall doing its job — Claude quoted something the
                    # response does not actually say.
                    logger.warning(
                        "misinformation_quote_rejected",
                        result_id=str(result.id), quote=candidate.quote[:120],
                    )
                    continue
                key = normalize_ws(candidate.quote)
                if key in seen_quotes:
                    continue
                db.add(MisinformationFinding(
                    client_id=client.id,
                    scan_query_result_id=result.id,
                    quote=candidate.quote,
                    category=candidate.category,
                    rule_key=candidate.rule_key,
                    severity=candidate.severity,
                    explanation=candidate.explanation,
                ))
                seen_quotes.add(key)
                stored += 1

        if stored:
            db.commit()
            logger.info("misinformation_findings_stored", scan_id=str(scan_id), count=stored)
    except Exception as exc:
        db.rollback()
        logger.error("misinformation_detect_failed", scan_id=str(scan_id), error=str(exc))
        return 0

    # Same pass, opposite direction: statements that have stopped appearing.
    try:
        check_candidate_fixed(scan_id, db)
    except Exception as exc:
        db.rollback()
        logger.error("misinformation_candidate_check_failed", scan_id=str(scan_id), error=str(exc))
    return stored


# --- Review workflow --------------------------------------------------------
# Claude proposes, Faris disposes. Every transition below is admin-driven except
# candidate_fixed, which is only ever a suggestion for the admin to confirm.

_OPEN_STATUS_ORDER = {
    "suggested": 0, "candidate_fixed": 1, "confirmed": 2,
    "corrected": 3, "verified_fixed": 4, "dismissed": 5,
}


def get_findings(client_id: uuid.UUID, db: Session) -> list[MisinformationFinding]:
    """All findings for a client, work-needing ones first, newest within a group."""
    rows = (
        db.query(MisinformationFinding)
        .filter(MisinformationFinding.client_id == client_id)
        .all()
    )
    return sorted(
        rows,
        key=lambda f: (_OPEN_STATUS_ORDER.get(f.status, 9), -f.detected_at.timestamp()),
    )


def _paired_remediation_item(finding: MisinformationFinding, db: Session):
    """The RemediationItem spawned for this finding, if it still exists.

    Keyed exactly as _spawn_remediation created it, which is also the
    uq_remediation_dedupe key.
    """
    from app.models.remediation_item import RemediationItem

    result = db.get(ScanQueryResult, finding.scan_query_result_id)
    if result is None:
        return None
    return (
        db.query(RemediationItem)
        .filter(
            RemediationItem.client_id == finding.client_id,
            RemediationItem.item_type == "misinformation",
            RemediationItem.platform == result.platform,
            RemediationItem.label == result.query_text,
        )
        .first()
    )


def _spawn_remediation(finding: MisinformationFinding, db: Session) -> None:
    """Track the corrective work in the existing remediation loop (get-or-create,
    matching the uq_remediation_dedupe constraint)."""
    from app.core.constants import COMPLIANCE_RULES, MISINFORMATION_CATEGORY_LABELS
    from app.models.remediation_item import RemediationItem

    result = db.get(ScanQueryResult, finding.scan_query_result_id)
    if result is None:
        return
    detail = MISINFORMATION_CATEGORY_LABELS.get(finding.category, "Incorrect statement")
    # .get, not [] — COMPLIANCE_RULES is Faris-maintained, so a key can be
    # renamed or retired while findings that cite it are still in the queue.
    # A stale key must not make the finding permanently unconfirmable.
    rule_text = COMPLIANCE_RULES.get(finding.rule_key) if finding.rule_key else None
    if rule_text:
        detail = f"{detail} — {rule_text}"

    existing = _paired_remediation_item(finding, db)
    if existing is not None:
        # One AI answer can carry two different problems, and the remediation
        # dedupe key can't tell them apart — append rather than overwrite so the
        # first finding's category isn't silently lost.
        if detail not in (existing.detail or ""):
            existing.detail = f"{existing.detail}; {detail}" if existing.detail else detail
        return
    db.add(RemediationItem(
        client_id=finding.client_id,
        item_type="misinformation",
        platform=result.platform,
        label=result.query_text,
        detail=detail,
        status="flagged",
    ))


# Reviewing is a first look, or a change of mind about a dismissal. Once a
# finding is in the fix pipeline, re-reviewing it would re-stamp reviewed_at —
# which re-fires the weekly digest protection line and pulls an already-fixed
# statement back into the monthly PDF's open count.
_REVIEWABLE_STATUSES = ("suggested", "dismissed")


def review_finding(
    finding_id: uuid.UUID,
    action: str,
    db: Session,
    note: str | None = None,
    severity: str | None = None,
) -> MisinformationFinding | None:
    """Admin gate. `action` is "confirm" or "dismiss". Returns None when the
    finding does not exist or has already moved past review."""
    if action not in ("confirm", "dismiss"):
        raise ValueError('action must be "confirm" or "dismiss"')
    if severity is not None and severity not in MISINFORMATION_SEVERITIES:
        raise ValueError("severity must be high, medium, or low")
    finding = db.get(MisinformationFinding, finding_id)
    if finding is None or finding.status not in _REVIEWABLE_STATUSES:
        return None
    finding.status = "confirmed" if action == "confirm" else "dismissed"
    finding.reviewed_at = utcnow()
    if note:
        finding.admin_note = note
    if severity is not None:
        finding.severity = severity
    if action == "confirm":
        _spawn_remediation(finding, db)
    db.commit()
    db.refresh(finding)
    return finding


def store_truth_conflict_candidates(
    client_id: uuid.UUID,
    scan_query_result_id: uuid.UUID,
    candidates: list["TruthConflictCandidate"],
    db: Session,
) -> int:
    """Persist deterministic fact conflicts as admin-review candidates only.

    The comparison service supplies IDs and normalized evidence, but this
    boundary still validates client ownership and the verbatim quote firewall
    before storing anything.  A candidate can never self-confirm or classify a
    legal/professional violation.
    """
    from app.industry_packs import registry as pack_registry
    from app.models.truth_fact import TruthFact, TruthFactVersion
    from app.services.pack_risk_service import evaluate_pack_risk

    # The client's pack decides how each conflict is triaged. Resolved once per
    # call, not per candidate. A client with no reviewed pack, or one whose pack
    # module is not registered, keeps the pre-Phase-4 "low" default exactly.
    client = db.get(Client, client_id)
    pack = pack_registry.find_pack(getattr(client, "industry_pack", None))

    result = db.get(ScanQueryResult, scan_query_result_id)
    if result is None or db.get(Scan, result.scan_id) is None:
        return 0
    scan = db.get(Scan, result.scan_id)
    observed_at = scan.completed_at if scan is not None else None
    if scan is None or scan.client_id != client_id or observed_at is None:
        return 0

    stored = 0
    for candidate in candidates:
        if not isinstance(candidate, TruthConflictCandidate):
            continue
        fact = db.get(TruthFact, candidate.truth_fact_id)
        version = db.get(TruthFactVersion, candidate.truth_fact_version_id)
        if (
            fact is None
            or version is None
            or fact.client_id != client_id
            or version.truth_fact_id != fact.id
            or version.status != "approved"
            or version.effective_from is None
            or version.effective_from > observed_at
            or (version.effective_to is not None and version.effective_to < observed_at)
            or not quote_in_response(candidate.answer_quote, result.response_text)
        ):
            continue
        exists = db.query(MisinformationFinding.id).filter(
            MisinformationFinding.scan_query_result_id == scan_query_result_id,
            MisinformationFinding.truth_fact_version_id == version.id,
            MisinformationFinding.quote == candidate.answer_quote,
        ).first()
        if exists is not None:
            continue
        risk = evaluate_pack_risk(pack, candidate)
        db.add(MisinformationFinding(
            client_id=client_id,
            scan_query_result_id=scan_query_result_id,
            truth_fact_id=fact.id,
            truth_fact_version_id=version.id,
            quote=candidate.answer_quote,
            category="factual_error",
            severity=risk.finding_severity,
            rule_key=risk.provenance,
            explanation=(
                f"AI statement conflicts with approved {candidate.fact_type}/{candidate.fact_key} "
                f"using the {candidate.comparator} comparator. {risk.review_instruction}"
            ),
            status="suggested",
        ))
        stored += 1
    if stored:
        db.commit()
    return stored


def mark_corrected(finding_id: uuid.UUID, db: Session) -> MisinformationFinding | None:
    """The corrective work is done and awaiting proof from a later scan.
    Only a confirmed finding can be corrected."""
    finding = db.get(MisinformationFinding, finding_id)
    if finding is None or finding.status != "confirmed":
        return None
    finding.status = "corrected"
    # Keep the tracked item in step — sync_remediation_items deliberately skips
    # this type, so the finding workflow is the only thing that can move it.
    item = _paired_remediation_item(finding, db)
    if item is not None and item.status == "flagged":
        item.status = "in_progress"
    db.commit()
    db.refresh(finding)
    return finding


def resolve_finding(finding_id: uuid.UUID, db: Session) -> MisinformationFinding | None:
    """Admin confirms the fix held. Only from candidate_fixed: absence in one
    scan is a suggestion, never proof, so the good news is gated too."""
    finding = db.get(MisinformationFinding, finding_id)
    if finding is None or finding.status != "candidate_fixed":
        return None
    finding.status = "verified_fixed"
    finding.resolved_at = utcnow()
    # Close the spawned item too, otherwise it sits "Flagged" forever and the
    # admin's natural cleanup click is what finally stamps resolved_at.
    item = _paired_remediation_item(finding, db)
    if item is not None and item.status != "corrected":
        item.status = "corrected"
        item.resolved_at = finding.resolved_at
    db.commit()
    db.refresh(finding)
    return finding


def check_candidate_fixed(scan_id: uuid.UUID, db: Session) -> int:
    """Re-check open findings against this scan's responses. Returns how many
    findings changed status.

    Two directions, both conservative:
      - confirmed/corrected → candidate_fixed when the statement is gone.
      - candidate_fixed → confirmed when it comes back (AI answers are
        non-deterministic, so a single absence that later reverses is normal;
        without this the finding would be stuck offering "Confirm fixed").

    Comparison is scoped to the platform the finding came from. A platform that
    failed or was disabled contributes no rows this scan (scan_service isolates
    per-platform failures by design), and "we didn't ask" must never read as
    "the statement is gone".
    """
    scan = db.get(Scan, scan_id)
    if scan is None:
        return 0
    responses_by_platform: dict[str, list[str]] = {}
    for r in db.query(ScanQueryResult).filter(
        ScanQueryResult.scan_id == scan_id,
        ScanQueryResult.competitor_id.is_(None),
        ScanQueryResult.is_control.is_(False),
        ScanQueryResult.response_text.isnot(None),
    ).all():
        responses_by_platform.setdefault(r.platform, []).append(normalize_ws(r.response_text))
    if not responses_by_platform:
        return 0

    changed = 0
    findings = (
        db.query(MisinformationFinding)
        .filter(
            MisinformationFinding.client_id == scan.client_id,
            MisinformationFinding.status.in_(("confirmed", "corrected", "candidate_fixed")),
        )
        .all()
    )
    for finding in findings:
        source = db.get(ScanQueryResult, finding.scan_query_result_id)
        texts = responses_by_platform.get(source.platform) if source else None
        if not texts:
            continue  # that platform wasn't re-checked this scan
        needle = normalize_ws(finding.quote)
        present = any(needle in text for text in texts)
        if present and finding.status == "candidate_fixed":
            finding.status = "confirmed"
            changed += 1
        elif not present and finding.status in ("confirmed", "corrected"):
            finding.status = "candidate_fixed"
            changed += 1
    if changed:
        db.commit()
        logger.info("misinformation_status_rechecked", scan_id=str(scan_id), count=changed)
    return changed
