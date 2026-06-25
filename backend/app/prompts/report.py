# backend/app/prompts/report.py
"""Prompt template for the monthly report change narrative."""

VERSION = "v2"


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

    return (
        "You are an AI visibility analyst writing a brief monthly summary for a client report. "
        "Write 2-3 sentences (plain text, no headings, under 70 words) explaining what changed this month. "
        "Where specific queries are provided, name them — say which questions the business is now seen for "
        "or lost visibility on. Use 'seen by AI' not 'cited'; 'visibility frequency' not 'citation rate'; "
        "never use 'ranking', 'confidence score', or internal jargon. Be specific and factual.\n\n"
        f"Business: {data.period_label} report.\n"
        f"Overall score: {data.prev_overall_score:.0f} -> {data.overall_score:.0f}.\n"
        f"AI visibility frequency (citability): {data.ai_citability:.0f}%.\n"
        f"Seen by AI in {data.seen_count} of {data.total_count} tracked queries."
        f"{query_context}\n"
        f"Dimension scores now — Brand Authority {data.brand_authority:.0f}, Content Quality "
        f"{data.content_quality:.0f}, Technical Foundations {data.technical_foundations:.0f}, "
        f"Structured Data {data.structured_data:.0f}.\n"
        f"{competitor_note}"
    )
