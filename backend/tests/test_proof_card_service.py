from dataclasses import dataclass

from app.services.proof_card_service import (
    result_excerpt,
    select_proof_cards,
)


@dataclass
class FakeResult:
    platform: str
    category: str
    brand_detected: bool
    recommendation_position: int | None
    response_text: str | None


def _win(platform="chatgpt", category="recommendation", pos=1):
    return FakeResult(platform, category, True, pos,
                      "Acme Dental is the top recommended clinic in KL.")


def _loss(platform="perplexity", category="local"):
    return FakeResult(platform, category, False, None,
                      "In KL, RivalCo is the most recommended dental clinic.")


def test_result_excerpt_win():
    kind, ex = result_excerpt(_win(), "Acme Dental", ["RivalCo"])
    assert kind == "win" and "Acme Dental" in ex


def test_result_excerpt_loss_redacts_competitor():
    kind, ex = result_excerpt(_loss(), "Acme Dental", ["RivalCo"])
    assert kind == "loss" and "[a competitor]" in ex and "RivalCo" not in ex


def test_result_excerpt_none_for_absent_brand_in_brand_category():
    r = FakeResult("chatgpt", "brand", False, None, "RivalCo is great.")
    assert result_excerpt(r, "Acme Dental", ["RivalCo"]) == (None, None)


def test_result_excerpt_none_when_excerpt_builder_returns_empty(monkeypatch):
    import app.services.proof_card_service as svc
    monkeypatch.setattr(svc.snippet_service, "build_excerpt", lambda *a, **k: "")
    kind, ex = result_excerpt(_win(), "Acme Dental", ["RivalCo"])
    assert (kind, ex) == (None, None)


def test_select_caps_two_wins_one_loss():
    results = [_win(pos=1), _win(pos=2), _win(pos=3), _loss(), _loss()]
    cards = select_proof_cards(results, "Acme Dental", ["RivalCo"])
    assert [c.kind for c in cards] == ["win", "win", "loss"]


def test_select_orders_wins_before_losses():
    cards = select_proof_cards([_loss(), _win()], "Acme Dental", ["RivalCo"])
    assert len(cards) == 2 and cards[0].kind == "win" and cards[1].kind == "loss"


def test_select_empty_when_no_qualifying_results():
    r = FakeResult("chatgpt", "comparison", False, None, "Many clinics exist.")
    assert select_proof_cards([r], "Acme Dental", ["RivalCo"]) == []


def test_proof_card_never_contains_response_text():
    cards = select_proof_cards([_win()], "Acme Dental", ["RivalCo"])
    assert all(not hasattr(c, "response_text") for c in cards)
    assert all(isinstance(c.excerpt, str) for c in cards)


# --- tests for redact_competitors parameter ---

def test_select_proof_cards_names_competitor_when_redact_false():
    results = [
        FakeResult(
            platform="chatgpt",
            category="recommendation",
            brand_detected=False,
            recommendation_position=None,
            response_text="In KL, RivalCo is the top recommended clinic.",
        ),
    ]
    cards = select_proof_cards(
        results, brand="Acme Dental", competitors=["RivalCo"], redact_competitors=False
    )
    assert len(cards) == 1
    assert cards[0].kind == "loss"
    assert "RivalCo" in cards[0].excerpt
    assert "[a competitor]" not in cards[0].excerpt


def test_select_proof_cards_default_redacts_competitor():
    results = [
        FakeResult(
            platform="chatgpt",
            category="recommendation",
            brand_detected=False,
            recommendation_position=None,
            response_text="In KL, RivalCo is the top recommended clinic.",
        ),
    ]
    cards = select_proof_cards(results, brand="Acme Dental", competitors=["RivalCo"])
    assert cards[0].excerpt and "RivalCo" not in cards[0].excerpt
    assert "[a competitor]" in cards[0].excerpt
