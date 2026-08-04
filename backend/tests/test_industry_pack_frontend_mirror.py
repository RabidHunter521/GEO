"""The frontend pack catalog must not drift from the backend registry.

`frontend/src/lib/industry-packs.ts` is a hand-written mirror, because the admin
form needs pack metadata synchronously and there is no build-time codegen step
here. Duplication has caused real bugs in this codebase before, so it is only
acceptable with a guard: adding a truth field or subcategory in Python and
forgetting the TypeScript is caught here rather than by an admin noticing a
form field that never appears.

This asserts CONTAINMENT, not equality of formatting — it reads the TS as text
rather than pretending to parse TypeScript. That catches the realistic failure
(something added on one side only) without being brittle about layout.
"""
from pathlib import Path

import pytest

from app.core.constants import INDUSTRY_PACK_KEYS
from app.industry_packs import registry

MIRROR = (
    Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "lib" / "industry-packs.ts"
)


@pytest.fixture(scope="module")
def mirror_source() -> str:
    if not MIRROR.exists():
        pytest.fail(f"frontend pack catalog is missing at {MIRROR}")
    return MIRROR.read_text(encoding="utf-8")


def test_every_pack_key_is_mirrored(mirror_source):
    for key in INDUSTRY_PACK_KEYS:
        assert f'"{key}"' in mirror_source, f"pack {key} is missing from the frontend catalog"


def test_every_subcategory_is_mirrored(mirror_source):
    missing = [
        f"{pack.key}.{sub}"
        for pack in registry.all_packs()
        for sub in pack.subcategories
        if f'"{sub}"' not in mirror_source
    ]
    assert not missing, f"subcategories missing from the frontend catalog: {missing}"


def test_every_truth_field_is_mirrored(mirror_source):
    """A field the admin cannot enter is a field the Truth Vault never gets."""
    missing = []
    for pack in registry.all_packs():
        for field in pack.truth_fields:
            entry = f'factType: "{field.fact_type}", key: "{field.key}"'
            if entry not in mirror_source:
                missing.append(f"{pack.key}: {field.fact_type}.{field.key}")
    assert not missing, f"truth fields missing from the frontend catalog: {missing}"


def test_risk_sensitive_flags_are_mirrored(mirror_source):
    """A risk-sensitive fact rendered without its source requirement would let
    an admin approve a credential claim with no evidence behind it."""
    lines = mirror_source.splitlines()
    problems = []
    for pack in registry.all_packs():
        for field in pack.truth_fields:
            if not field.risk_sensitive:
                continue
            entry = f'factType: "{field.fact_type}", key: "{field.key}"'
            line = next((row for row in lines if entry in row), None)
            if line is None or "riskSensitive: true" not in line:
                problems.append(f"{pack.key}: {field.fact_type}.{field.key}")
    assert not problems, (
        f"these facts are risk-sensitive in Python but not in the frontend: {problems}"
    )


def test_value_types_are_mirrored(mirror_source):
    lines = mirror_source.splitlines()
    problems = []
    for pack in registry.all_packs():
        for field in pack.truth_fields:
            entry = f'factType: "{field.fact_type}", key: "{field.key}"'
            line = next((row for row in lines if entry in row), None)
            if line is None or f'valueType: "{field.value_type}"' not in line:
                problems.append(
                    f"{pack.key}: {field.fact_type}.{field.key} should be {field.value_type}"
                )
    assert not problems, f"value type drift: {problems}"


def test_the_mirror_declares_no_pack_the_backend_lacks(mirror_source):
    """Drift in the other direction: a frontend-only pack would offer an admin a
    selection the API rejects."""
    import re

    # Pack declarations put `label:` on the FOLLOWING line; per-field entries put
    # factType/key/label together on one line. Requiring the newline is what
    # separates the two, and without it this matches every field key too.
    declared = set(
        re.findall(r'^\s*key:\s*"([a-z_]+)",\s*\n\s*label:', mirror_source, re.MULTILINE)
    )
    assert declared, "found no pack declarations — the catalog's shape changed"
    unknown = declared - set(INDUSTRY_PACK_KEYS)
    assert not unknown, f"frontend declares packs the backend does not: {sorted(unknown)}"
