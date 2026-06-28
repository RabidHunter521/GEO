from unittest.mock import MagicMock
from types import SimpleNamespace

from app.services.revenue_service import estimate_pipeline, estimate_value_at_risk, ValueAtRisk


def _client(deal=None, v2l=2, l2c=20, avg_deal_value_rm=None, visitor_to_lead_pct=None, lead_to_customer_pct=None):
    """Create a client stub. Supports both old (positional) and new (SimpleNamespace) styles."""
    if avg_deal_value_rm is not None or visitor_to_lead_pct is not None or lead_to_customer_pct is not None:
        # New style: use SimpleNamespace for estimate_value_at_risk tests
        return SimpleNamespace(
            avg_deal_value_rm=avg_deal_value_rm,
            visitor_to_lead_pct=visitor_to_lead_pct,
            lead_to_customer_pct=lead_to_customer_pct,
        )
    # Old style: use MagicMock for estimate_pipeline tests
    c = MagicMock()
    c.avg_deal_value_rm = deal
    c.visitor_to_lead_pct = v2l
    c.lead_to_customer_pct = l2c
    return c


def test_returns_none_without_deal_value():
    assert estimate_pipeline(1000, _client(deal=None)) is None
    assert estimate_pipeline(1000, _client(deal=0)) is None


def test_returns_none_without_visitors():
    assert estimate_pipeline(None, _client(deal=5000)) is None


def test_computes_pipeline_chain():
    # 1000 visitors x 2% = 20 leads; x RM5000 = RM100,000 pipeline; x 20% = RM20,000 won
    est = estimate_pipeline(1000, _client(deal=5000, v2l=2, l2c=20))
    assert est is not None
    assert est.est_leads == 20
    assert est.est_pipeline_rm == 100_000
    assert est.est_won_rm == 20_000
    assert est.avg_deal_value_rm == 5000


def test_zero_visitors_is_zero_not_none():
    est = estimate_pipeline(0, _client(deal=5000))
    assert est is not None
    assert est.est_leads == 0
    assert est.est_pipeline_rm == 0
    assert est.est_won_rm == 0


# Tests for estimate_value_at_risk


def test_value_at_risk_none_without_deal_value():
    assert estimate_value_at_risk(100, 0.4, _client(avg_deal_value_rm=0)) is None
    assert estimate_value_at_risk(100, 0.4, _client(avg_deal_value_rm=None)) is None


def test_value_at_risk_none_without_inputs():
    assert estimate_value_at_risk(None, 0.4, _client(avg_deal_value_rm=1000)) is None
    assert estimate_value_at_risk(100, None, _client(avg_deal_value_rm=1000)) is None


def test_value_at_risk_gap_multiplier_at_40pct():
    # f=0.4 -> (1-0.4)/0.4 = 1.5; V=100 -> 150 missed visitors.
    r = estimate_value_at_risk(100, 0.4, _client(avg_deal_value_rm=1000))
    assert r is not None
    assert r.gap_multiplier == 1.5
    assert r.missed_visitors == 150
    # 150 visitors x 2% (default) = 3 leads; x RM1000 = RM3000 pipeline; x 20% = RM600 won.
    assert r.missed_leads == 3
    assert r.missed_pipeline_rm == 3000
    assert r.missed_won_rm == 600


def test_value_at_risk_full_visibility_is_zero():
    r = estimate_value_at_risk(100, 1.0, _client(avg_deal_value_rm=1000))
    assert r is not None
    assert r.gap_multiplier == 0.0
    assert r.missed_visitors == 0
    assert r.missed_pipeline_rm == 0


def test_value_at_risk_floors_low_visibility():
    # f=0.10 raw would be 9x; floored at MIN_VIS=0.25 -> (1-0.10)/0.25 = 3.6, capped to 3.0.
    r = estimate_value_at_risk(100, 0.10, _client(avg_deal_value_rm=1000))
    assert r is not None
    assert r.gap_multiplier == 3.0
    assert r.missed_visitors == 300


def test_value_at_risk_zero_visibility_no_divide_by_zero():
    r = estimate_value_at_risk(100, 0.0, _client(avg_deal_value_rm=1000))
    assert r is not None
    assert r.gap_multiplier == 3.0  # (1-0)/0.25 = 4.0, capped to 3.0


def test_value_at_risk_respects_custom_conversion_pcts():
    r = estimate_value_at_risk(100, 0.4, _client(avg_deal_value_rm=2000,
                                                 visitor_to_lead_pct=5,
                                                 lead_to_customer_pct=10))
    # 150 missed visitors x 5% = 7.5 leads (carried unrounded into pipeline);
    # 7.5 x RM2000 = RM15000 pipeline; x 10% = RM1500 won. (missed_leads alone rounds to 8.)
    assert r.visitor_to_lead_pct == 5
    assert r.missed_pipeline_rm == 15000
