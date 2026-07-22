"""Guarantee engine — commitment tracking. System derives pace; only the admin
flips terminal outcomes (assessment-service pattern: suggest, never auto-tell
a client "missed")."""
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.constants import GUARANTEE_GRACE_FRACTION, GUARANTEE_METRICS
from app.core.time import utcnow
from app.models.geo_score import GeoScore
from app.models.guarantee import Guarantee


@dataclass
class GuaranteeProgress:
    guarantee: Guarantee
    current_value: float | None
    points_needed: int
    points_gained: float
    days_total: int
    days_remaining: int
    state: str


def _latest_metric_value(client_id: uuid.UUID, metric: str, db: Session) -> float | None:
    gs = (
        db.query(GeoScore)
        .filter(GeoScore.client_id == client_id)
        .order_by(desc(GeoScore.computed_at))
        .first()
    )
    if gs is None:
        return None
    return gs.ai_citability if metric == "ai_citability" else gs.overall_score


def _active(client_id: uuid.UUID, db: Session) -> Guarantee | None:
    return (
        db.query(Guarantee)
        .filter(Guarantee.client_id == client_id, Guarantee.status == "active")
        .first()
    )


def create_guarantee(
    client_id: uuid.UUID, metric: str, target_value: int, deadline_date: date,
    db: Session, baseline_override: int | None = None, start_date: date | None = None,
) -> Guarantee:
    if metric not in GUARANTEE_METRICS:
        raise ValueError(f"Invalid metric: {metric}")
    if _active(client_id, db) is not None:
        raise ValueError("active guarantee exists")
    baseline = baseline_override
    if baseline is None:
        current = _latest_metric_value(client_id, metric, db)
        if current is None:
            raise ValueError("no completed scan to baseline from")
        baseline = round(current)
    g = Guarantee(
        client_id=client_id, metric=metric, baseline_value=baseline,
        target_value=target_value, start_date=start_date or date.today(),
        deadline_date=deadline_date,
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


def derive_state(g: Guarantee, current_value: float | None, today: date) -> str:
    if current_value is not None and current_value >= g.target_value:
        return "met"
    if today > g.deadline_date:
        return "deadline_passed"
    days_total = max((g.deadline_date - g.start_date).days, 1)
    elapsed = max((today - g.start_date).days, 0)
    if elapsed / days_total <= GUARANTEE_GRACE_FRACTION:
        return "on_track"
    if current_value is None:
        return "on_track"  # no scan yet in period — nothing to judge
    needed = g.target_value - g.baseline_value
    gained = current_value - g.baseline_value
    expected = (elapsed / days_total) * needed
    return "on_track" if gained >= expected else "at_risk"


def get_guarantee_progress(client_id: uuid.UUID, db: Session) -> GuaranteeProgress | None:
    g = _active(client_id, db)
    if g is None:
        return None
    current = _latest_metric_value(client_id, g.metric, db)
    today = date.today()
    return GuaranteeProgress(
        guarantee=g,
        current_value=current,
        points_needed=g.target_value - g.baseline_value,
        points_gained=round((current - g.baseline_value), 2) if current is not None else 0.0,
        days_total=max((g.deadline_date - g.start_date).days, 1),
        days_remaining=max((g.deadline_date - today).days, 0),
        state=derive_state(g, current, today),
    )


@dataclass
class ClientCommitment:
    """Collapsed, client-safe view of the guarantee. state is one of
    "achieved" | "in_progress" | "missed" — internal pace states never leave
    the server, and a client never learns "missed" before the admin resolves."""
    metric_label: str
    baseline: int
    target: int
    current: float | None
    deadline: date
    state: str


def get_client_commitment(client_id: uuid.UUID, db: Session) -> ClientCommitment | None:
    g = (
        db.query(Guarantee)
        .filter(Guarantee.client_id == client_id)
        .order_by(desc(Guarantee.created_at))
        .first()
    )
    if g is None or g.status == "void":
        return None
    current = _latest_metric_value(client_id, g.metric, db)
    if g.status == "active":
        state = derive_state(g, current, date.today())
        if state == "met":
            client_state = "achieved"
        elif state == "deadline_passed":
            return None  # hidden until the admin resolves the outcome
        else:
            client_state = "in_progress"  # on_track AND at_risk — numbers speak
    elif g.status == "met":
        client_state = "achieved"
    elif g.status == "missed":
        client_state = "missed"
    else:
        return None
    return ClientCommitment(
        metric_label="AI visibility" if g.metric == "ai_citability" else "Overall score",
        baseline=g.baseline_value,
        target=g.target_value,
        current=current,
        deadline=g.deadline_date,
        state=client_state,
    )


def resolve_guarantee(
    guarantee_id: uuid.UUID, outcome: str, db: Session, note: str | None = None
) -> Guarantee:
    if outcome not in ("met", "missed", "void"):
        raise ValueError(f"Invalid outcome: {outcome}")
    g = db.get(Guarantee, guarantee_id)
    if g is None:
        raise ValueError("guarantee not found")
    if g.status != "active":
        raise ValueError("guarantee already resolved")
    g.status = outcome
    g.resolved_at = utcnow()
    if note:
        g.admin_note = note
    db.commit()
    db.refresh(g)
    return g
