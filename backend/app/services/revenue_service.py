# backend/app/services/revenue_service.py
"""Turn raw AI-referral visitor counts into a single pipeline/revenue number.

The CEO question is "what did AI visibility get me in RM?". We can't measure
closed revenue, so we give a transparent, admin-tunable estimate:

    leads        = visitors        x visitor_to_lead_pct
    pipeline_rm  = leads           x avg_deal_value_rm
    est_won_rm   = pipeline_rm     x lead_to_customer_pct (close rate)

Never fabricated: returns None unless the admin has set avg_deal_value_rm for the
client. Conversion percentages fall back to sane platform defaults.
"""
from dataclasses import dataclass

from app.models.client import Client
from app.core.constants import (
    DEFAULT_VISITOR_TO_LEAD_PCT,
    DEFAULT_LEAD_TO_CUSTOMER_PCT,
    VALUE_AT_RISK_MIN_VISIBILITY,
    VALUE_AT_RISK_MAX_MULTIPLIER,
)


@dataclass
class PipelineEstimate:
    ai_visitors: int
    est_leads: int
    est_pipeline_rm: int
    est_won_rm: int
    avg_deal_value_rm: int
    visitor_to_lead_pct: int
    lead_to_customer_pct: int


def estimate_pipeline(ai_visitors: int | None, client: Client) -> PipelineEstimate | None:
    """Estimate pipeline from a month's AI-referral visitors. None when the deal
    value isn't configured (we never invent a revenue number)."""
    deal_value = client.avg_deal_value_rm
    if not deal_value or deal_value <= 0 or ai_visitors is None:
        return None

    v2l = client.visitor_to_lead_pct if client.visitor_to_lead_pct is not None else DEFAULT_VISITOR_TO_LEAD_PCT
    l2c = client.lead_to_customer_pct if client.lead_to_customer_pct is not None else DEFAULT_LEAD_TO_CUSTOMER_PCT

    leads = ai_visitors * v2l / 100.0
    pipeline_rm = leads * deal_value
    won_rm = pipeline_rm * l2c / 100.0

    return PipelineEstimate(
        ai_visitors=ai_visitors,
        est_leads=round(leads),
        est_pipeline_rm=round(pipeline_rm),
        est_won_rm=round(won_rm),
        avg_deal_value_rm=deal_value,
        visitor_to_lead_pct=v2l,
        lead_to_customer_pct=l2c,
    )


@dataclass
class ValueAtRisk:
    ai_visitors: int
    missed_visitors: int
    missed_leads: int
    missed_pipeline_rm: int
    missed_won_rm: int
    avg_deal_value_rm: int
    visitor_to_lead_pct: int
    lead_to_customer_pct: int
    gap_multiplier: float


def estimate_value_at_risk(
    ai_visitors: int | None, visibility_frequency: float | None, client: Client
) -> ValueAtRisk | None:
    """Estimate the pipeline missed because of AI invisibility, by scaling the
    realized visitor count by the visibility gap and running it through the same
    chain as estimate_pipeline. Conservative: visibility is floored at
    VALUE_AT_RISK_MIN_VISIBILITY and the gap multiplier capped at
    VALUE_AT_RISK_MAX_MULTIPLIER. None when the deal value or inputs are missing
    (we never invent a revenue number)."""
    deal_value = client.avg_deal_value_rm
    if not deal_value or deal_value <= 0 or ai_visitors is None or visibility_frequency is None:
        return None

    v2l = client.visitor_to_lead_pct if client.visitor_to_lead_pct is not None else DEFAULT_VISITOR_TO_LEAD_PCT
    l2c = client.lead_to_customer_pct if client.lead_to_customer_pct is not None else DEFAULT_LEAD_TO_CUSTOMER_PCT

    f = max(visibility_frequency, VALUE_AT_RISK_MIN_VISIBILITY)
    gap_multiplier = min((1.0 - visibility_frequency) / f, VALUE_AT_RISK_MAX_MULTIPLIER)
    gap_multiplier = max(gap_multiplier, 0.0)  # full visibility -> 0, never negative

    missed_visitors = ai_visitors * gap_multiplier
    missed_leads = missed_visitors * v2l / 100.0
    missed_pipeline = missed_leads * deal_value
    missed_won = missed_pipeline * l2c / 100.0

    return ValueAtRisk(
        ai_visitors=ai_visitors,
        missed_visitors=round(missed_visitors),
        missed_leads=round(missed_leads),
        missed_pipeline_rm=round(missed_pipeline),
        missed_won_rm=round(missed_won),
        avg_deal_value_rm=deal_value,
        visitor_to_lead_pct=v2l,
        lead_to_customer_pct=l2c,
        gap_multiplier=round(gap_multiplier, 4),
    )
