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
from app.models.client import Client
from app.models.misinformation_finding import MisinformationFinding
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.prompts.misinformation import build_detection
from app.services.claude_client import MODEL, anthropic_client, strip_code_fences
from app.services.cost_tracker import record_llm_call

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
    return stored
