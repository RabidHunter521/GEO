# backend/app/prompts/citability.py
"""Prompt for the page-citability rewrite suggestions (assist-only —
the score is computed server-side; Claude only proposes text)."""
from app.models.client import Client

SUGGESTIONS_VERSION = "v1"


def build_citability_suggestions(client: Client, problem_checks: list[dict], excerpt: str) -> str:
    issues = "\n".join(
        f"- {c['label']} ({c['status']}): {c['detail']}" for c in problem_checks
    )
    return f"""You are a GEO (Generative Engine Optimization) editor helping a {client.industry} \
business called {client.name} make one web page easier for AI assistants to read and quote.

An automated audit of the page found these issues:
{issues}

Page content (first part):
---
{excerpt}
---

Propose up to 5 concrete rewrites that fix the audit issues. For each:
- section: which part of the page it applies to (short label, e.g. "Opening paragraph").
- issue: one plain-English sentence on what's wrong there.
- rewrite: publish-ready replacement text the business can paste in as-is. Write it in \
the page's own voice, factually grounded ONLY in what the page already says — never \
invent services, prices, statistics, or claims.

Never use the words "citation", "cited", "mentioned", "citation rate", "ranking position", \
or "visibility gap" — say "seen by AI" and "visibility frequency" instead.
Output ONLY valid JSON, no code fences, exactly:
{{"suggestions": [{{"section": "string", "issue": "string", "rewrite": "string"}}]}}"""
