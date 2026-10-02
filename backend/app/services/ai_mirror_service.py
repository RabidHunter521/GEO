"""Day-one 'AI Mirror': what one AI platform says about the client, side by side
with what it says about their top competitor.

Deterministic and LLM-free. Every scan already asks each platform about the
client ("Tell me about {brand}") and about each competitor ("Tell me about
{competitor}"), so the mirror reads rows the scan stored — no extra AI calls,
no second scan path. Every quote is a verbatim sentence of a stored answer and
every count comes from one scan, so the mirror is Observed evidence: one answer
per side, from one scan, on one day. AI answers vary between runs; the
surfaces say so.

Pairs come from the SAME scan and the SAME platform. The question is the same
wording on both sides when the client's scan asked it; packed clients are asked
their pack's brand questions instead, so their side falls back to the first
brand question and `same_question` is False — the surfaces then show both
questions as asked rather than implying a like-for-like test.
"""
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.constants import COMPETITOR_QUERY_TEMPLATES, PLATFORM_LABELS
from app.models.competitor import Competitor
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.schemas.ai_mirror import (
    AiMirrorPlatform,
    AiMirrorResponse,
    AiMirrorSide,
    ClientViewMirror,
    ClientViewMirrorPlatform,
    ClientViewMirrorSide,
)
from app.services import snippet_service
from app.services.win_loss_service import compute_win_loss

# ChatGPT leads: it is the assistant buyers use most, and the one the mirror is
# pitched on. The rest follow the platform label order.
_PLATFORM_ORDER = ["chatgpt", *[p for p in PLATFORM_LABELS if p != "chatgpt"]]
_MAX_EXCERPTS = 3
_MAX_EXCERPT_CHARS = 280


@dataclass
class MirrorSide:
    name: str
    question: str | None
    status: str  # "seen" | "not_seen" | "no_answer"
    excerpts: list[str] = field(default_factory=list)
    # Admin-only: never mapped onto a client-view schema.
    response_text: str | None = None
    flagged_inaccurate: bool = False


@dataclass
class MirrorPlatform:
    platform: str
    same_question: bool
    you: MirrorSide
    competitor: MirrorSide
    # Neutral buyer questions (recommendation + local) the client was asked on
    # this platform in this scan: one denominator for both counts.
    buyer_answers_total: int
    buyer_answers_you: int
    buyer_answers_competitor: int


@dataclass
class AiMirror:
    status: str  # "ready" | "no_scan" | "no_competitors"
    checked_at: object = None  # datetime | None
    competitor_name: str | None = None
    # "buyer_answers": named most often in the client's own buyer-question
    # answers. "visibility": nobody was named there, so the competitor seen by
    # AI most often in its own tracked questions.
    competitor_basis: str | None = None
    platforms: list[MirrorPlatform] = field(default_factory=list)


def _platform_rank(platform: str) -> int:
    return _PLATFORM_ORDER.index(platform) if platform in _PLATFORM_ORDER else len(_PLATFORM_ORDER)


def _trim(sentence: str) -> str:
    """Cap a quote at a word boundary, never mid-word."""
    if len(sentence) <= _MAX_EXCERPT_CHARS:
        return sentence
    cut = sentence[: _MAX_EXCERPT_CHARS - 1]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:-") + "…"


def mirror_excerpts(response_text: str | None, subject: str) -> list[str]:
    """Up to three verbatim sentences of an answer about `subject`.

    Sentences naming the subject come first; an answer that never repeats the
    name (e.g. "I don't have information on that business.") is still the
    answer to a question about it, so its opening sentences are used instead.
    Bare list rows are skipped, the same rule proof cards follow.
    """
    if not response_text:
        return []
    # Same sentence splitting and list-row rule as proof cards, so a mirror
    # quote and a proof card can never disagree on what counts as a sentence.
    sentences = [
        s for s in snippet_service._candidate_sentences(response_text)
        if snippet_service._substantial(s)
    ]
    pattern = re.compile(rf"(?<!\w){re.escape(subject.strip())}(?!\w)", re.IGNORECASE)
    naming = [s for s in sentences if pattern.search(s)]
    chosen = (naming or sentences)[:_MAX_EXCERPTS]
    return [_trim(s) for s in chosen]


def _side(row: ScanQueryResult | None, name: str, fallback_question: str | None) -> MirrorSide:
    if row is None:
        return MirrorSide(name=name, question=fallback_question, status="no_answer")
    if row.brand_detected:
        status = "seen"
    elif row.response_text:
        status = "not_seen"
    else:
        # Purged or never returned: we cannot say what the platform answered.
        status = "no_answer"
    return MirrorSide(
        name=name,
        question=row.query_text,
        status=status,
        excerpts=mirror_excerpts(row.response_text, name),
        response_text=row.response_text,
        flagged_inaccurate=bool(row.hallucination_flagged),
    )


def _first(rows: list[ScanQueryResult]) -> ScanQueryResult | None:
    rows = sorted(rows, key=lambda r: (r.sample_index or 1, r.created_at))
    return rows[0] if rows else None


def _pick_competitor(competitors, wl_entries, competitor_rows) -> tuple[Competitor, str]:
    """The rival named most often in the client's own buyer-question answers;
    if nobody is named there, the one seen by AI most often in its own tracked
    questions. Ties break on name so the choice is stable between page loads."""
    named: dict[str, int] = {}
    for e in wl_entries:
        for n in e.competitors_seen:
            named[n] = named.get(n, 0) + 1
    if named:
        best = sorted(named.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        for c in competitors:
            if c.name == best:
                return c, "buyer_answers"

    def visibility(c) -> float:
        rows = [r for r in competitor_rows if r.competitor_id == c.id]
        return sum(1 for r in rows if r.brand_detected) / len(rows) if rows else 0.0

    return sorted(competitors, key=lambda c: (-visibility(c), c.name))[0], "visibility"


def build_ai_mirror(client, db: Session, *, include_flagged: bool = False) -> AiMirror:
    """The mirror for the client's latest completed scan.

    include_flagged=False (client view) drops answers flagged as inaccurate,
    the rule every client-facing surface follows. The admin surface passes
    True and shows the flag instead.
    """
    wl = compute_win_loss(client.id, db)
    if wl.scan_id is None:
        return AiMirror(status="no_scan")
    scan = db.get(Scan, wl.scan_id)

    competitors = (
        db.query(Competitor)
        .filter(Competitor.client_id == client.id)
        .order_by(Competitor.name)
        .all()
    )
    if not competitors:
        return AiMirror(status="no_competitors", checked_at=scan.completed_at)

    q = db.query(ScanQueryResult).filter(
        ScanQueryResult.scan_id == scan.id,
        ScanQueryResult.is_control.is_(False),
    )
    if not include_flagged:
        q = q.filter(ScanQueryResult.hallucination_flagged.is_(False))
    rows = q.all()
    competitor_rows = [
        r for r in rows if r.competitor_id is not None and not r.hallucination_flagged
    ]
    rival, basis = _pick_competitor(competitors, wl.entries, competitor_rows)

    mirror_q_you = COMPETITOR_QUERY_TEMPLATES["brand"].format(competitor=client.name)
    mirror_q_rival = COMPETITOR_QUERY_TEMPLATES["brand"].format(competitor=rival.name)

    platforms: list[MirrorPlatform] = []
    for platform in sorted({r.platform for r in rows}, key=_platform_rank):
        on_platform = [r for r in rows if r.platform == platform]
        your_brand = [
            r for r in on_platform if r.competitor_id is None and r.category == "brand"
        ]
        your_row = _first([r for r in your_brand if r.query_text == mirror_q_you]) or _first(your_brand)
        rival_row = _first([
            r for r in on_platform
            if r.competitor_id == rival.id and r.category == "brand"
        ])
        if your_row is None and rival_row is None:
            continue
        you = _side(your_row, client.name, mirror_q_you)
        them = _side(rival_row, rival.name, mirror_q_rival)

        buyer = [e for e in wl.entries if e.platform == platform]
        platforms.append(MirrorPlatform(
            platform=platform,
            same_question=(
                your_row is not None and rival_row is not None
                and your_row.query_text == mirror_q_you
            ),
            you=you,
            competitor=them,
            buyer_answers_total=len(buyer),
            buyer_answers_you=sum(1 for e in buyer if e.client_seen),
            buyer_answers_competitor=sum(1 for e in buyer if rival.name in e.competitors_seen),
        ))

    return AiMirror(
        status="ready",
        checked_at=scan.completed_at,
        competitor_name=rival.name,
        competitor_basis=basis,
        platforms=platforms,
    )


def _label(platform: str) -> str:
    return PLATFORM_LABELS.get(platform, platform.title())


def to_client_view(mirror: AiMirror) -> ClientViewMirror:
    """Whitelist for the public share view: excerpts and counts, never the raw
    answer or the internal inaccuracy flag."""
    def side(s: MirrorSide) -> ClientViewMirrorSide:
        return ClientViewMirrorSide(
            name=s.name, question=s.question, status=s.status, excerpts=s.excerpts
        )

    return ClientViewMirror(
        status=mirror.status,
        checked_at=mirror.checked_at,
        competitor_name=mirror.competitor_name,
        competitor_basis=mirror.competitor_basis,
        platforms=[
            ClientViewMirrorPlatform(
                platform_label=_label(p.platform),
                same_question=p.same_question,
                you=side(p.you),
                competitor=side(p.competitor),
                buyer_answers_total=p.buyer_answers_total,
                buyer_answers_you=p.buyer_answers_you,
                buyer_answers_competitor=p.buyer_answers_competitor,
            )
            for p in mirror.platforms
        ],
    )


def to_admin_response(mirror: AiMirror) -> AiMirrorResponse:
    def side(s: MirrorSide) -> AiMirrorSide:
        return AiMirrorSide(
            name=s.name,
            question=s.question,
            status=s.status,
            excerpts=s.excerpts,
            response_text=s.response_text,
            flagged_inaccurate=s.flagged_inaccurate,
        )

    return AiMirrorResponse(
        status=mirror.status,
        checked_at=mirror.checked_at,
        competitor_name=mirror.competitor_name,
        competitor_basis=mirror.competitor_basis,
        platforms=[
            AiMirrorPlatform(
                platform=p.platform,
                platform_label=_label(p.platform),
                same_question=p.same_question,
                you=side(p.you),
                competitor=side(p.competitor),
                buyer_answers_total=p.buyer_answers_total,
                buyer_answers_you=p.buyer_answers_you,
                buyer_answers_competitor=p.buyer_answers_competitor,
            )
            for p in mirror.platforms
        ],
    )
