"""GA4 AI-referral traffic sync. Pure classification/aggregation here is
unit-tested without Google; the API call itself is isolated in _fetch_rows so
tests mock exactly one seam."""
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import date

import structlog
from sqlalchemy.orm import Session

from app.core.constants import AI_REFERRER_DOMAINS
from app.models.ai_traffic_snapshot import AiTrafficSnapshot
from app.models.client import Client

logger = structlog.get_logger()


def classify_referrer(source: str) -> str | None:
    host = (source or "").strip().lower()
    for domain, label in AI_REFERRER_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return label
    return None


def _canonical_domain(source: str) -> str | None:
    host = (source or "").strip().lower()
    for domain in AI_REFERRER_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return domain
    return None


def aggregate_rows(rows: list[tuple[str, str, int]]) -> dict[date, dict]:
    out: dict[date, dict] = {}
    for yyyymm, source, sessions in rows:
        domain = _canonical_domain(source)
        if domain is None:
            continue
        period = date(int(yyyymm[:4]), int(yyyymm[4:6]), 1)
        bucket = out.setdefault(period, {"ai_visitors": 0, "breakdown": {}})
        bucket["ai_visitors"] += sessions
        bucket["breakdown"][domain] = bucket["breakdown"].get(domain, 0) + sessions
    return out
