from unittest.mock import MagicMock

from app.services.revenue_service import estimate_pipeline


def _client(deal=None, v2l=2, l2c=20):
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
