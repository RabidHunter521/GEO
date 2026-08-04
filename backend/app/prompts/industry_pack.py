# backend/app/prompts/industry_pack.py
"""The single prompt-side statement of a client's industry pack context.

Every content prompt that should speak in an industry's terms imports
`build_pack_context` from here rather than assembling its own block. The same
reasoning as `language.py`: per-prompt copies drift, and a drifted copy here
would mean one surface is told not to invent a credential while another is not.

What goes in is deliberately narrow — the pack's identity, the client's APPROVED
facts, and the claim rules that follow from which of those facts are
risk-sensitive. What stays out is everything a model could repeat back into a
client-facing surface without it having been reviewed:

  * draft or retired fact values (only approved, currently-effective values)
  * reviewer notes and admin commentary
  * raw conflict/finding records
  * internal identifiers

The pack's own `review_instruction` text is never included either. Those are
written for a human reviewer deciding what to check, not for a model writing
marketing copy, and a model handed "confirm the stated qualification" tends to
assert that it did confirm it.
"""
from __future__ import annotations

from typing import Iterable

# v1: initial pack context block (Phase 4 Task 9).
PACK_CONTEXT_VERSION = "v1"

_MAX_VALUES_PER_FACT = 8


def build_pack_context(client, pack, facts: Iterable = ()) -> str:
    """Return the pack context block, or "" when the client has no pack.

    An empty string is important: prompts concatenate this, and an unpacked
    client must produce byte-identical output to before Phase 4.
    """
    if pack is None:
        return ""

    lines = [
        "",
        f"Industry specialisation: {pack.label}"
        + (f" ({_humanise(client.industry_subcategory)})" if client.industry_subcategory else ""),
    ]

    approved = _approved_lines(pack, facts)
    if approved:
        lines.append("")
        lines.append(
            "Verified business facts. These have been checked and approved by the "
            "business. Use them as the source of truth:"
        )
        lines.extend(approved)

    sensitive = _sensitive_labels(pack)
    if sensitive:
        lines.append("")
        lines.append(
            "Sensitive claims — do NOT state anything about "
            f"{_join(sensitive)} unless it appears in the verified facts above. "
            "If a fact is not listed, write around it rather than guessing. "
            "Never imply that this business has been endorsed, certified, "
            "licensed or approved by any professional or regulatory body."
        )

    lines.append("")
    lines.append(
        "Do not invent facts about this business. Anything not given above is "
        "unknown to you."
    )
    return "\n".join(lines)


def _approved_lines(pack, facts: Iterable) -> list[str]:
    """One line per approved fact, labelled with the pack's own wording.

    Facts the pack does not declare are skipped: they carry no label, and an
    unlabelled internal key is not something to put in front of a model that is
    writing client-facing prose.
    """
    labels = {(f.fact_type, f.key): f.label for f in pack.truth_fields}
    out: list[str] = []
    for fact in facts:
        label = labels.get((fact.fact_type, fact.fact_key))
        if label is None:
            continue
        rendered = _render(fact.value)
        if rendered:
            out.append(f"- {label}: {rendered}")
    return out


def _sensitive_labels(pack) -> list[str]:
    seen: list[str] = []
    for field in pack.truth_fields:
        if field.risk_sensitive and field.label not in seen:
            seen.append(field.label.lower())
    return seen


def _render(value) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        items = [_render(item) for item in value]
        items = [item for item in items if item][:_MAX_VALUES_PER_FACT]
        return ", ".join(items)
    if isinstance(value, dict):
        parts = [f"{key} {_render(val)}" for key, val in list(value.items())[:_MAX_VALUES_PER_FACT]]
        return "; ".join(part for part in parts if part.strip())
    if value is None:
        return ""
    return " ".join(str(value).split())


def _humanise(value: str) -> str:
    spaced = value.replace("_", " ")
    return spaced[:1].upper() + spaced[1:]


def _join(values: list[str]) -> str:
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + f" or {values[-1]}"
