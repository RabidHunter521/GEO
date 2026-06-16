import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.database import get_db
from app.models.client import Client
from app.models.llm_call_log import LlmCallLog

router = APIRouter(prefix="/clients/{client_id}/costs", tags=["costs"])


class ServiceBreakdown(BaseModel):
    service: str
    prompt_version: str
    model: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


class CostSummaryResponse(BaseModel):
    client_id: uuid.UUID
    total_calls: int
    total_cost_usd: float
    last_30_days_cost_usd: float
    by_service: list[ServiceBreakdown]


@router.get("", response_model=CostSummaryResponse, dependencies=[Depends(require_api_key)])
def get_client_costs(client_id: uuid.UUID, db: Session = Depends(get_db)):
    if not db.get(Client, client_id):
        raise HTTPException(status_code=404, detail="Client not found")

    rows = (
        db.query(
            LlmCallLog.service,
            LlmCallLog.prompt_version,
            LlmCallLog.model,
            func.count(LlmCallLog.id).label("calls"),
            func.sum(LlmCallLog.input_tokens).label("input_tokens"),
            func.sum(LlmCallLog.output_tokens).label("output_tokens"),
            func.sum(LlmCallLog.cost_usd).label("cost_usd"),
        )
        .filter(LlmCallLog.client_id == client_id)
        .group_by(LlmCallLog.service, LlmCallLog.prompt_version, LlmCallLog.model)
        .order_by(func.sum(LlmCallLog.cost_usd).desc())
        .all()
    )

    since_30 = datetime.utcnow() - timedelta(days=30)
    last_30_cost: Decimal = (
        db.query(func.sum(LlmCallLog.cost_usd))
        .filter(LlmCallLog.client_id == client_id, LlmCallLog.called_at >= since_30)
        .scalar() or Decimal("0")
    )

    by_service = [
        ServiceBreakdown(
            service=r.service,
            prompt_version=r.prompt_version,
            model=r.model,
            calls=r.calls,
            input_tokens=int(r.input_tokens or 0),
            output_tokens=int(r.output_tokens or 0),
            cost_usd=float(r.cost_usd or 0),
        )
        for r in rows
    ]

    return CostSummaryResponse(
        client_id=client_id,
        total_calls=sum(r.calls for r in by_service),
        total_cost_usd=sum(r.cost_usd for r in by_service),
        last_30_days_cost_usd=float(last_30_cost),
        by_service=by_service,
    )
