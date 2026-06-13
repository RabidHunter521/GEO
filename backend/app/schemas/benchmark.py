# backend/app/schemas/benchmark.py
"""Admin-facing industry benchmark schema. The client view uses the separate
anonymous ClientViewBenchmark whitelist in schemas/client_view.py (no rank)."""
from pydantic import BaseModel


class IndustryBenchmarkResponse(BaseModel):
    industry: str
    peer_count: int          # scored, non-archived clients incl. this one
    client_score: float
    industry_average: float
    rank: int                # admin-only — never expose on the client view
    top_percent: int
