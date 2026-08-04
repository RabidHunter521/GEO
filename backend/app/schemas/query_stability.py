"""API response schema for per-query answer stability (Phase 5 Task 4).

This is deliberately INDEPENDENT from GeoScore / `app/schemas/geo_score.py` —
stability describes how CONSISTENT a tracked query's answers are across
repeated samples, not how favorable they are. It may be displayed alongside
the score, but nothing here ever feeds `overall_score` and nothing in the
scoring service imports this module. See
`app/services/query_stability_service.py` for the calculation this schema
serializes (`QueryStability`, a plain dataclass — this is its API-facing
mirror, matching the `ControlQueryResponse` / dataclass-then-schema split
used elsewhere in this codebase).

CLAUDE.md section 8: this schema never exposes raw AI responses, char
offsets, or confidence scores — `score` here is a 0.0-1.0 agreement ratio
between repeated samples, not a model confidence value, and is safe to
surface as "consistency" language on client-facing surfaces.
"""

import uuid
from typing import Literal

from pydantic import BaseModel

StabilityState = Literal["insufficient", "emerging", "repeated", "stable", "volatile"]


class QueryStabilityResponse(BaseModel):
    # Set by calculate_portfolio_stability (one row per tracked query);
    # left None by calculate_query_stability, where the caller already knows
    # which tracked query it asked about.
    tracked_query_id: uuid.UUID | None = None
    state: StabilityState
    score: float | None = None
    sample_count: int
    period_count: int
    agreement: dict[str, float] = {}
    calculation_version: str = "stability_v1"

    model_config = {"from_attributes": True}
