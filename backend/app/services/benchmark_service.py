# backend/app/services/benchmark_service.py
"""Industry benchmarking — client's rank among same-industry SeenBy clients.

Anonymous by design: only counts, average, and percentile leave this module.
Hidden entirely below MIN_BENCHMARK_PEERS scored clients so small cohorts
can't be reverse-engineered.
"""
import math
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.constants import MIN_BENCHMARK_PEERS
from app.models.client import Client
from app.models.geo_score import GeoScore
from app.schemas.benchmark import IndustryBenchmarkResponse


def compute_percentile(
    scores_by_client: dict[uuid.UUID, float], client_id: uuid.UUID
) -> tuple[int, int] | None:
    """Rank-based percentile: rank = 1 + count(strictly better peers).

    Returns (rank, top_percent) or None when the client has no score.
    Rank-based so the best of 5 reads "top 20%", never "top 0%"; ties share
    the better rank.
    """
    if client_id not in scores_by_client:
        return None
    mine = scores_by_client[client_id]
    rank = 1 + sum(1 for score in scores_by_client.values() if score > mine)
    top_percent = math.ceil(rank / len(scores_by_client) * 100)
    return rank, top_percent


def compute_industry_benchmark(
    client: Client, db: Session
) -> IndustryBenchmarkResponse | None:
    if not client.industry:
        return None

    # Latest GeoScore per non-archived client in the same industry
    # (case/trim-insensitive match — free-form industry strings drift)
    latest_subq = (
        db.query(
            GeoScore.client_id,
            func.max(GeoScore.computed_at).label("max_computed_at"),
        )
        .join(Client, Client.id == GeoScore.client_id)
        .filter(
            Client.archived_at.is_(None),
            # Prospects are cold leads, not portfolio peers — excluding them keeps
            # the industry average/percentile a true peer comparison.
            Client.is_prospect.is_(False),
            func.lower(func.trim(Client.industry)) == client.industry.strip().lower(),
        )
        .group_by(GeoScore.client_id)
        .subquery()
    )
    rows = (
        db.query(GeoScore.client_id, GeoScore.overall_score)
        .join(
            latest_subq,
            (GeoScore.client_id == latest_subq.c.client_id)
            & (GeoScore.computed_at == latest_subq.c.max_computed_at),
        )
        .all()
    )

    scores_by_client = {row.client_id: row.overall_score for row in rows}
    if len(scores_by_client) < MIN_BENCHMARK_PEERS:
        return None

    placed = compute_percentile(scores_by_client, client.id)
    if placed is None:
        return None
    rank, top_percent = placed

    return IndustryBenchmarkResponse(
        industry=client.industry,
        peer_count=len(scores_by_client),
        client_score=scores_by_client[client.id],
        industry_average=round(sum(scores_by_client.values()) / len(scores_by_client), 1),
        rank=rank,
        top_percent=top_percent,
    )
