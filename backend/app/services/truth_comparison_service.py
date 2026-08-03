"""Deterministic comparison of extracted AI claims with approved Truth Vault facts.

An LLM may identify the claim and quote it from an answer.  This module never
uses an LLM to decide whether that claim conflicts with a fact: every result is
produced by a named, deterministic comparator and remains a reviewer candidate.
"""
from __future__ import annotations

import json
import re
import unicodedata
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.models.truth_fact import TruthFact, TruthFactVersion


@dataclass(frozen=True)
class TruthClaim:
    """A structured statement extracted from one reviewed AI answer."""

    fact_type: str
    fact_key: str
    value: Any
    answer_quote: str
    observed_at: datetime | None = None
    location_id: uuid.UUID | None = None
    comparator: str | None = None


@dataclass(frozen=True)
class TruthConflictCandidate:
    """Evidence for an admin to review, never an automatic confirmed finding."""

    answer_quote: str
    claim_value: Any
    truth_fact_id: uuid.UUID
    truth_fact_version_id: uuid.UUID
    fact_type: str
    fact_key: str
    approved_value: Any
    source_url: str | None
    comparator: str
    category: str = "factual_error"
    severity: str = "low"
    status: str = "suggested"


_PHONE_KEYS = frozenset({"phone", "telephone", "mobile", "contact_number"})
_URL_KEYS = frozenset({"website", "url", "booking_url", "booking_link"})
_HOURS_KEYS = frozenset({"hours", "opening_hours", "business_hours"})
_TRUE_VALUES = frozenset({"true", "yes", "y", "1"})
_FALSE_VALUES = frozenset({"false", "no", "n", "0"})
_DAY_ALIASES = {
    "mon": "monday", "monday": "monday",
    "tue": "tuesday", "tues": "tuesday", "tuesday": "tuesday",
    "wed": "wednesday", "wednesday": "wednesday",
    "thu": "thursday", "thur": "thursday", "thurs": "thursday", "thursday": "thursday",
    "fri": "friday", "friday": "friday",
    "sat": "saturday", "saturday": "saturday",
    "sun": "sunday", "sunday": "sunday",
}


def compare_claims_to_truth(
    claims: Iterable[TruthClaim | Mapping[str, Any]],
    facts: Iterable[TruthFactVersion | tuple[TruthFact, TruthFactVersion] | Mapping[str, Any]],
) -> list[TruthConflictCandidate]:
    """Return unconfirmed candidates for claims that disagree with effective facts.

    `facts` may be the approved versions returned by ``facts_effective_at`` or
    explicit ``(TruthFact, TruthFactVersion)`` pairs.  Draft, retired, and
    temporally ineffective versions are always ignored.
    """
    resolved_facts = [_coerce_fact(item) for item in facts]
    candidates: list[TruthConflictCandidate] = []
    for raw_claim in claims:
        claim = _coerce_claim(raw_claim)
        if claim is None:
            continue
        for fact, version in resolved_facts:
            if not _is_effective_approved_fact(fact, version, claim):
                continue
            approved_value = _stored_value(version.value_json)
            comparator = _select_comparator(claim, approved_value)
            if _values_match(comparator, claim.value, approved_value):
                continue
            candidates.append(
                TruthConflictCandidate(
                    answer_quote=claim.answer_quote,
                    claim_value=claim.value,
                    truth_fact_id=fact.id,
                    truth_fact_version_id=version.id,
                    fact_type=fact.fact_type,
                    fact_key=fact.fact_key,
                    approved_value=approved_value,
                    source_url=version.source_url,
                    comparator=comparator,
                )
            )
    return candidates


def _coerce_claim(raw_claim: TruthClaim | Mapping[str, Any]) -> TruthClaim | None:
    if isinstance(raw_claim, TruthClaim):
        return raw_claim
    if not isinstance(raw_claim, Mapping):
        return None
    fact_type = raw_claim.get("fact_type")
    fact_key = raw_claim.get("fact_key")
    answer_quote = raw_claim.get("answer_quote") or raw_claim.get("quote")
    if not all(isinstance(value, str) and value.strip() for value in (fact_type, fact_key, answer_quote)):
        return None
    observed_at = raw_claim.get("observed_at") or raw_claim.get("scan_completed_at")
    if observed_at is not None and not isinstance(observed_at, datetime):
        return None
    location_id = raw_claim.get("location_id")
    if location_id is not None and not isinstance(location_id, uuid.UUID):
        return None
    return TruthClaim(
        fact_type=fact_type,
        fact_key=fact_key,
        value=raw_claim.get("value", raw_claim.get("claim_value")),
        answer_quote=answer_quote,
        observed_at=observed_at,
        location_id=location_id,
        comparator=raw_claim.get("comparator") or raw_claim.get("value_type"),
    )


def _coerce_fact(
    raw_fact: TruthFactVersion | tuple[TruthFact, TruthFactVersion] | Mapping[str, Any],
) -> tuple[TruthFact, TruthFactVersion]:
    if isinstance(raw_fact, tuple) and len(raw_fact) == 2:
        fact, version = raw_fact
        if isinstance(fact, TruthFact) and isinstance(version, TruthFactVersion):
            return fact, version
    if isinstance(raw_fact, TruthFactVersion):
        return raw_fact.truth_fact, raw_fact
    if isinstance(raw_fact, Mapping):
        fact = raw_fact.get("truth_fact") or raw_fact.get("fact")
        version = raw_fact.get("truth_fact_version") or raw_fact.get("version")
        if isinstance(fact, TruthFact) and isinstance(version, TruthFactVersion):
            return fact, version
    raise TypeError("facts must contain TruthFactVersion values or (TruthFact, TruthFactVersion) pairs")


def _is_effective_approved_fact(
    fact: TruthFact, version: TruthFactVersion, claim: TruthClaim
) -> bool:
    if version.status != "approved":
        return False
    if _normal_text(fact.fact_type) != _normal_text(claim.fact_type):
        return False
    if _normal_text(fact.fact_key) != _normal_text(claim.fact_key):
        return False
    if fact.location_id != claim.location_id:
        return False
    if claim.observed_at is None:
        return True
    return (
        version.effective_from is not None
        and version.effective_from <= claim.observed_at
        and (version.effective_to is None or version.effective_to >= claim.observed_at)
    )


def _stored_value(value_json: Any) -> Any:
    if isinstance(value_json, Mapping) and "value" in value_json:
        return value_json["value"]
    return value_json


def _select_comparator(claim: TruthClaim, approved_value: Any) -> str:
    requested = (claim.comparator or "").strip().lower()
    if requested in {"text", "phone", "url", "boolean", "hours", "list_containment"}:
        return requested
    key = _normal_text(claim.fact_key).replace(" ", "_")
    if key in _PHONE_KEYS:
        return "phone"
    if key in _URL_KEYS or key.endswith("_url") or key.endswith("_website"):
        return "url"
    if key in _HOURS_KEYS or key.endswith("_hours"):
        return "hours"
    if isinstance(approved_value, bool):
        return "boolean"
    if isinstance(approved_value, list):
        return "list_containment"
    return "text"


def _values_match(comparator: str, claimed: Any, approved: Any) -> bool:
    if comparator == "phone":
        return _phone_digits(claimed) == _phone_digits(approved) and bool(_phone_digits(approved))
    if comparator == "url":
        return _normal_url(claimed) == _normal_url(approved) and bool(_normal_url(approved))
    if comparator == "boolean":
        return _normal_bool(claimed) is not None and _normal_bool(claimed) == _normal_bool(approved)
    if comparator == "hours":
        return _normal_hours(claimed) == _normal_hours(approved)
    if comparator == "list_containment":
        approved_items = {_canonical_item(item) for item in approved if _canonical_item(item)} if isinstance(approved, list) else set()
        claimed_values = claimed if isinstance(claimed, list) else [claimed]
        claimed_items = {_canonical_item(item) for item in claimed_values if _canonical_item(item)}
        return bool(claimed_items) and claimed_items.issubset(approved_items)
    return _normal_text(claimed) == _normal_text(approved) and bool(_normal_text(approved))


def _normal_text(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def _phone_digits(value: Any) -> str:
    return "".join(character for character in str(value or "") if character.isdigit())


def _normal_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    split = urlsplit(raw if "://" in raw else f"//{raw}")
    host = (split.hostname or "").casefold().rstrip(".")
    if not host:
        return ""
    port = f":{split.port}" if split.port else ""
    path = split.path.rstrip("/")
    query = urlencode(sorted(parse_qsl(split.query, keep_blank_values=True)))
    return urlunsplit(("", host + port, path, query, ""))


def _normal_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = _normal_text(value)
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return None


def _normal_hours(value: Any) -> str:
    if isinstance(value, Mapping):
        normalized = {
            _DAY_ALIASES.get(_normal_text(day), _normal_text(day)): _normal_periods(periods)
            for day, periods in value.items()
        }
        return json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return _normal_text(value)


def _normal_periods(periods: Any) -> list[str]:
    if isinstance(periods, str):
        periods = [periods]
    if not isinstance(periods, list):
        return [_normal_text(periods)]
    normalized = [_normal_period(period) for period in periods]
    return sorted(period for period in normalized if period and period != "closed")


def _normal_period(period: Any) -> str:
    value = _normal_text(period).replace("–", "-")
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*-\s*(\d{1,2})(?::(\d{2}))?", value)
    if not match:
        return value
    start_hour, start_minute, end_hour, end_minute = match.groups()
    return f"{int(start_hour):02d}:{start_minute or '00'}-{int(end_hour):02d}:{end_minute or '00'}"


def _canonical_item(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _normal_text(value)
