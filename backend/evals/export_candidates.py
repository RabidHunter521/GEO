# backend/evals/export_candidates.py
"""Pull real stored AI answers into a draft dataset for a person to label.

    railway ssh -s api -- python -m evals.export_candidates --suite brand_detection --limit 40 \
        > brand_detection.candidates.jsonl

Read-only. Each row is pre-filled with what PRODUCTION decided (`expected`) and
marked `needs_review`; the labeller corrects `expected` where production was
wrong, deletes `needs_review`, and appends the row to evals/datasets/.

Client and competitor names are replaced with fixed placeholders before
anything is printed, so a labelled row can be committed without naming a
paying client. Answers are sampled newest-first across clients and platforms.
Output goes to stdout only; nothing is written to the repo or the database.
"""
import argparse
import json
import re
import sys

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult

_BRAND = "Placeholder Brand"
_COMPETITOR = "Competitor {}"


def anonymise(text: str, client_name: str, competitor_names: list[str]) -> str:
    """Replace every name in ONE pass, longest first.

    Sequential replacement would turn a competitor called "Acme Dental Care"
    into "Placeholder Brand Care" when the client is "Acme Dental", which
    silently relabels a competitor mention as the client's.
    """
    placeholders = {client_name.lower(): _BRAND}
    for i, name in enumerate(competitor_names, start=1):
        placeholders.setdefault(name.lower(), _COMPETITOR.format(i))
    pattern = re.compile(
        "|".join(re.escape(n) for n in sorted(placeholders, key=len, reverse=True)), re.IGNORECASE
    )
    return pattern.sub(lambda m: placeholders[m.group(0).lower()], text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--suite", required=True, choices=["brand_detection", "position_extraction"])
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        stmt = (
            select(ScanQueryResult, Scan.client_id)
            .join(Scan, Scan.id == ScanQueryResult.scan_id)
            .where(ScanQueryResult.response_text.is_not(None))
            .where(ScanQueryResult.competitor_id.is_(None))
            .where(ScanQueryResult.answer_shown.is_not(False))
            .order_by(ScanQueryResult.created_at.desc())
            .limit(args.limit)
        )
        if args.suite == "position_extraction":
            stmt = stmt.where(ScanQueryResult.category.in_(("recommendation", "local")))

        names: dict = {}
        for row, client_id in db.execute(stmt):
            if client_id not in names:
                client = db.get(Client, client_id)
                comps = db.scalars(select(Competitor.name).where(Competitor.client_id == client_id)).all()
                names[client_id] = (client.name, list(comps))
            client_name, comps = names[client_id]
            expected = row.brand_detected if args.suite == "brand_detection" else row.recommendation_position
            print(json.dumps({
                "id": f"real-{row.platform}-{str(row.id)[:8]}",
                "source": "real",
                "needs_review": True,
                "brand": _BRAND,
                "answer": anonymise(row.response_text, client_name, comps),
                "expected": expected,
                "note": f"{row.platform} {row.category}, {row.created_at:%Y-%m-%d}",
            }, ensure_ascii=False))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
