# backend/app/prompts/report.py
"""Prompt template for the monthly report change narrative."""
from app.prompts.language import LANGUAGE_RULES

# v5: the prompt finally names the business. "Business:" held the period label,
# so the model wrote about a client it could not name (prompt audit M1).
# v4: shared LANGUAGE_RULES — the local list missed "mentioned"/"uncited" and
# this narrative is printed verbatim in the client PDF (prompt audit H2).
VERSION = "v5"  # v3: work-delivered counts added to the context block


def build_change_narrative(data) -> str:
    """Build the 'what changed this month' prompt. data is a ReportData instance."""
    winning = [c.name for c in data.competitors if c.is_winning]
    competitor_note = (
        f"Competitors currently ahead in AI visibility: {', '.join(winning)}."
        if winning else "No competitors are ahead in AI visibility this month."
    )

    # Surface specific query-level changes so Claude can write a concrete narrative
    # ("now seen for X but lost visibility for Y") instead of just restating numbers.
    query_lines = []
    if data.newly_seen_queries:
        query_lines.append(
            "Queries newly seen by AI this month: "
            + "; ".join(f'"{q}"' for q in data.newly_seen_queries)
            + "."
        )
    if data.newly_lost_queries:
        query_lines.append(
            "Queries no longer seen for: "
            + "; ".join(f'"{q}"' for q in data.newly_lost_queries)
            + "."
        )
    query_context = ("\n" + "\n".join(query_lines)) if query_lines else ""

    # Counts only — never the entry text. The narrative may reference the volume
    # of work delivered, but the work log speaks for itself in its own section.
    delivered = getattr(data, "work_log_counts", None) or {}
    delivered_line = (
        "Work delivered this period (counts by type): "
        + ", ".join(f"{k}: {v}" for k, v in sorted(delivered.items()))
        if delivered else "No delivery records were published for this period."
    )

    # Stability summary (Phase 5 Task 8)
    stability = getattr(data, "stability_summary", None)
    stability_line = ""
    if stability and stability.total_queries > 0:
        parts = []
        if stability.stable_count:
            parts.append(f"{stability.stable_count} stable")
        if stability.repeated_count:
            parts.append(f"{stability.repeated_count} repeated")
        if stability.emerging_count:
            parts.append(f"{stability.emerging_count} emerging")
        if stability.volatile_count:
            parts.append(f"{stability.volatile_count} volatile")
        if stability.insufficient_count:
            parts.append(f"{stability.insufficient_count} insufficient data")
        stability_line = (
            f"Query stability: {stability.total_queries} tracked queries — "
            + ", ".join(parts) + "."
        )

    # Impact summary (Phase 5 Task 8) — use "associated with" for correlation
    impact_summaries = getattr(data, "impact_summaries", None) or []
    impact_line = ""
    if impact_summaries:
        parts = []
        for imp in impact_summaries:
            observed_major = imp.observed_value_minor / 100
            if observed_major > 0:
                parts.append(
                    f"Business impact (observed, {imp.currency}): "
                    f"{imp.currency} {observed_major:,.2f} associated with AI visibility."
                )
        if parts:
            impact_line = " ".join(parts)

    return (
        "You are an AI visibility analyst writing a brief monthly summary for a client report. "
        "Write 2-3 sentences (plain text, no headings, under 70 words) explaining what changed this month. "
        "Where specific queries are provided, name them — say which questions the business is now seen for "
        "or lost visibility on. Be specific and factual. Never use internal jargon. "
        f"{LANGUAGE_RULES}\n\n"
        f"Business: {getattr(data, 'business_name', '') or 'this business'}.\n"
        f"Report period: {data.period_label}.\n"
        f"Overall score: {data.prev_overall_score:.0f} -> {data.overall_score:.0f}.\n"
        f"AI visibility frequency (citability): {data.ai_citability:.0f}%.\n"
        f"Seen by AI in {data.seen_count} of {data.total_count} tracked queries."
        f"{query_context}\n"
        f"Dimension scores now — Brand Authority {data.brand_authority:.0f}, Content Quality "
        f"{data.content_quality:.0f}, Technical Foundations {data.technical_foundations:.0f}, "
        f"Structured Data {data.structured_data:.0f}.\n"
        f"{competitor_note}\n"
        f"{delivered_line}"
        + (f"\n{stability_line}" if stability_line else "")
        + (f"\n{impact_line}" if impact_line else "")
    )
