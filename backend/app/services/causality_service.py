"""Optimized-vs-control visibility trend — the causal proof chart.

Pure compute-on-read over stored booleans (survives the 90-day raw-response
purge). Client-facing label: "queries we optimized" vs "queries we left
alone" — never "control group"."""
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult


@dataclass
class CausalPoint:
    scan_id: uuid.UUID
    completed_at: datetime
    optimized_frequency: float | None
    control_frequency: float | None


@dataclass
class CausalTrend:
    points: list[CausalPoint]


def _freq(rows) -> float | None:
    if not rows:
        return None
    return round(sum(1 for r in rows if r.brand_detected) / len(rows) * 100, 2)


def compute_causal_trend(client_id: uuid.UUID, db: Session) -> CausalTrend:
    # Note: if a pitch-mode scan flag (Scan.is_pitch) lands later, exclude
    # those scans here — pitch runs are demos, not retainer history.
    scans = (
        db.query(Scan)
        .filter(Scan.client_id == client_id, Scan.status == "completed")
        .order_by(Scan.completed_at)
        .all()
    )
    points: list[CausalPoint] = []
    for scan in scans:
        rows = (
            db.query(ScanQueryResult)
            .filter(
                ScanQueryResult.scan_id == scan.id,
                ScanQueryResult.competitor_id.is_(None),
            )
            .all()
        )
        optimized = [r for r in rows if not r.is_control]
        controls = [r for r in rows if r.is_control]
        points.append(CausalPoint(
            scan_id=scan.id,
            completed_at=scan.completed_at,
            optimized_frequency=_freq(optimized),
            control_frequency=_freq(controls),
        ))
    return CausalTrend(points=points)
