# backend/app/prompts/report.py
"""Prompt template for the monthly report change narrative."""

VERSION = "v1"


def build_change_narrative(data) -> str:
    """Build the 'what changed this month' prompt. data is a ReportData instance."""
    winning = [c.name for c in data.competitors if c.is_winning]
    competitor_note = (
        f"Competitors currently ahead in AI visibility: {', '.join(winning)}."
        if winning else "No competitors are ahead in AI visibility this month."
    )
    return (
        "You are an AI visibility analyst writing a brief monthly summary for a client report. "
        "Write 2-3 sentences (plain text, no headings, under 70 words) explaining what changed this month. "
        "Use the phrase 'seen by AI' rather than 'cited' or 'mentioned'; say 'visibility frequency' not "
        "'citation rate'; never use 'ranking', 'confidence score', or internal jargon. Be specific and factual.\n\n"
        f"Business: {data.period_label} report.\n"
        f"Overall score: {data.prev_overall_score:.0f} -> {data.overall_score:.0f}.\n"
        f"AI visibility frequency (citability): {data.ai_citability:.0f}%.\n"
        f"Seen by AI in {data.seen_count} of {data.total_count} tracked queries.\n"
        f"Dimension scores now — Brand Authority {data.brand_authority:.0f}, Content Quality "
        f"{data.content_quality:.0f}, Technical Foundations {data.technical_foundations:.0f}, "
        f"Structured Data {data.structured_data:.0f}.\n"
        f"{competitor_note}"
    )
