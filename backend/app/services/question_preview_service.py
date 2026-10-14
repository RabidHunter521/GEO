"""What a client will be asked on its next scan, and which facts it is missing.

Read-only, and it costs nothing: no model is called. Questions are built
through the same path `scan_service.run_scan` uses (`pack_scan_inputs` +
`build_client_queries`), so the preview cannot drift from the scan.

A packed client is measured only on questions its APPROVED facts can fill. A
template whose fact is missing is dropped without a trace in the scan, which
left staff unable to tell why a client was asked 9 questions instead of 20.
`preview` names every dropped question and what would restore it;
`fact_checklist` turns the same mapping into a to-do list for the Truth Vault.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.core.constants import DISCOVERY_CATEGORIES
from app.industry_packs.base import IndustryPack, placeholders_in
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.control_query import ControlQuery
from app.models.truth_fact import TruthFact, TruthFactVersion
from app.services import pack_query_service
from app.services.query_builder import build_client_queries, build_competitor_queries

# What a non-fact placeholder needs, in words an admin can act on.
_CLIENT_FIELD_NEEDS = {
    "brand": "The brand name",
    "industry": "An industry or what buyers call this business (Settings)",
    "country": "The client's country (Settings)",
    "city": "A city (Settings or a business location)",
    "area": "A city (Settings or a business location)",
    "location": "A city or state (Settings or a business location)",
    "competitor": "At least one competitor (Settings)",
}

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def preview(client: Client, db: Session) -> dict:
    """The client's own questions for the next scan, plus what was left out."""
    competitors = db.query(Competitor).filter(Competitor.client_id == client.id).all()
    pack, locations, facts = pack_query_service.pack_scan_inputs(client, db)
    queries = build_client_queries(
        client, competitors, pack=pack, locations=locations, approved_facts=facts,
    )
    custom_texts = {
        " ".join(str(item.get("text", "")).split()).casefold()
        for item in (getattr(client, "custom_questions", None) or ())
        if isinstance(item, dict)
    }

    questions = [
        {
            "text": q["query_text"],
            "category": q["category"],
            "counts_toward_score": q["category"] in DISCOVERY_CATEGORIES,
            "source": _source(q, pack, custom_texts),
        }
        for q in queries
    ]

    skipped = []
    if pack is not None:
        for template, missing in pack_query_service.skipped_templates(
            client, locations, facts, pack, competitors,
        ):
            skipped.append({
                "question": _readable(template.template),
                "needs": [_need(name, pack) for name in missing],
            })

    benchmark_count = (
        db.query(ControlQuery)
        .filter(ControlQuery.client_id == client.id, ControlQuery.active.is_(True))
        .count()
    )
    return {
        "pack_label": pack.label if pack is not None else None,
        "questions": questions,
        "skipped": skipped,
        "platform_count": len(client.enabled_platforms or []),
        "competitor_question_count": sum(
            len(build_competitor_queries(client, c)) for c in competitors
        ),
        "benchmark_question_count": benchmark_count,
    }


def fact_checklist(client: Client, db: Session) -> list[dict]:
    """The pack facts worth approving first, with where each one stands.

    A field is listed when the pack requires it, when it fills scan questions
    for this client's subcategory, or when it is risk-sensitive (AI answers
    are checked against it for accuracy issues). Anything else is optional.
    """
    pack, _locations, facts = pack_query_service.pack_scan_inputs(client, db)
    if pack is None:
        return []

    approved = {(f.fact_type, f.fact_key) for f in facts if _has_value(f.value)}
    drafted = {
        (fact_type, fact_key)
        for fact_type, fact_key in db.query(TruthFact.fact_type, TruthFact.fact_key)
        .join(TruthFactVersion, TruthFactVersion.truth_fact_id == TruthFact.id)
        .filter(TruthFact.client_id == client.id, TruthFactVersion.status == "draft")
        .distinct()
    }
    templates = pack_query_service.applicable_templates(
        pack, getattr(client, "industry_subcategory", None)
    )

    items = []
    for field in pack.truth_fields:
        pair = (field.fact_type, field.key)
        question_count = sum(
            1 for t in templates
            if any(
                pair in pack_query_service.fact_sources(name)
                for name in placeholders_in(t.template)
            )
        )
        if not (field.required or question_count or field.risk_sensitive):
            continue
        if pair in approved:
            status = "approved"
        elif pair in drafted:
            status = "draft"
        else:
            status = "missing"
        items.append({
            "fact_type": field.fact_type,
            "fact_key": field.key,
            "label": field.label,
            "required": field.required,
            "risk_sensitive": field.risk_sensitive,
            "question_count": question_count,
            "status": status,
        })
    return items


def _source(query: dict, pack: IndustryPack | None, custom_texts: set[str]) -> str:
    if query["query_text"].casefold() in custom_texts and "template_id" not in query:
        return "custom"
    return "pack" if pack is not None else "standard"


def _need(placeholder: str, pack: IndustryPack) -> str:
    if placeholder in _CLIENT_FIELD_NEEDS:
        return _CLIENT_FIELD_NEEDS[placeholder]
    labels = {(f.fact_type, f.key): f.label for f in pack.truth_fields}
    for pair in pack_query_service.fact_sources(placeholder):
        if pair in labels:
            return f"An approved fact: {labels[pair]}"
    return f"An approved fact for {placeholder.replace('_', ' ')}"


def _readable(template: str) -> str:
    """"Best {product} in {country}" -> "Best [product] in [country]"."""
    return _PLACEHOLDER.sub(lambda m: f"[{m.group(1).replace('_', ' ')}]", template)


def _has_value(value) -> bool:
    if isinstance(value, (list, tuple)):
        return any(str(v).strip() for v in value if v is not None)
    return value is not None and str(value).strip() != ""
