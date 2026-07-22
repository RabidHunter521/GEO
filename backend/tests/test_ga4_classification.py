from datetime import date

from app.services.ga4_traffic_service import aggregate_rows, classify_referrer


def test_classify_exact_and_subdomain_and_unknown():
    assert classify_referrer("chatgpt.com") == "ChatGPT"
    assert classify_referrer("www.perplexity.ai") == "Perplexity"
    assert classify_referrer("m.chat.openai.com") == "ChatGPT"
    assert classify_referrer("google.com") is None
    assert classify_referrer("notchatgpt.com") is None  # suffix must be dot-bounded


def test_aggregate_rows_by_month():
    rows = [
        ("202607", "chatgpt.com", 100),
        ("202607", "www.chatgpt.com", 40),
        ("202607", "perplexity.ai", 60),
        ("202606", "claude.ai", 10),
        ("202607", "google.com", 999),  # non-AI: dropped
    ]
    out = aggregate_rows(rows)
    assert out[date(2026, 7, 1)]["ai_visitors"] == 200
    assert out[date(2026, 7, 1)]["breakdown"]["chatgpt.com"] == 140
    assert out[date(2026, 6, 1)]["ai_visitors"] == 10
