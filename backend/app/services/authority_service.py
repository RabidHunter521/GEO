"""Authority & Presence Tracker — per-client authority checklist (spec §4-§10).

Nothing is auto-created for a client: rows exist only after the admin picks
from AUTHORITY_ASSET_CATALOG or adds a custom asset. Verification is a single
SSRF-guarded page read (Task 3); provenance-driven priorities read
scan_query_sources (Task 4). No score is written here — assets feed evidence
into the assisted Brand Authority flow, admin still gates the number.
"""
import re
import uuid

import structlog
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.core.constants import AUTHORITY_ASSET_CATALOG, AUTHORITY_ASSET_STATUSES, AUTHORITY_ASSET_TYPES
from app.core.time import utcnow
from app.models.activity_log import ActivityLog
from app.models.authority_asset import AuthorityAsset
from app.models.client import Client
from app.services.brand_detection import detect_brand_mention
from app.services.url_safety import is_safe_crawl_url, safe_get

logger = structlog.get_logger()

CATALOG_BY_KEY: dict[str, dict] = {item["key"]: item for item in AUTHORITY_ASSET_CATALOG}
_TYPE_ORDER = {t: i for i, t in enumerate(AUTHORITY_ASSET_TYPES)}
_STATUS_LABELS = {
    "missing": "missing", "in_progress": "in progress",
    "live": "live", "verified": "verified",
}


def _industry_match(item: dict, industry: str) -> bool:
    """True when any of the item's suggested_industries appears in the client's
    industry text (case-insensitive substring) — a soft SORT hint only."""
    low = (industry or "").lower()
    return any(hint.lower() in low for hint in item.get("suggested_industries", []))


def get_catalog(client: Client, db: Session) -> list[dict]:
    """Full master catalog with an `added` flag per item, industry-sorted.

    Matching-industry items float to the top; ties keep the catalog's type
    order. Never auto-selects — the flag just tells the picker what to disable.
    """
    added_keys = {
        r.asset_key
        for r in db.query(AuthorityAsset.asset_key)
        .filter(AuthorityAsset.client_id == client.id, AuthorityAsset.asset_key.isnot(None))
        .all()
    }
    items = [
        {
            "key": item["key"], "name": item["name"], "type": item["type"],
            "provenance_domain": item["provenance_domain"], "url_hint": item["url_hint"],
            "suggested_industries": item["suggested_industries"],
            "added": item["key"] in added_keys,
        }
        for item in AUTHORITY_ASSET_CATALOG
    ]
    items.sort(key=lambda i: (
        0 if _industry_match(i, client.industry) else 1,
        _TYPE_ORDER.get(i["type"], 99),
    ))
    return items


def list_assets(
    client_id: uuid.UUID, db: Session, include_hidden: bool = False
) -> list[AuthorityAsset]:
    """Client's assets, ordered by type (catalog order) then created_at."""
    q = db.query(AuthorityAsset).filter(AuthorityAsset.client_id == client_id)
    if not include_hidden:
        q = q.filter(AuthorityAsset.hidden.is_(False))
    rows = q.all()
    rows.sort(key=lambda a: (_TYPE_ORDER.get(a.asset_type, 99), a.created_at))
    return rows


def add_assets(client: Client, items: list[dict], db: Session) -> list[AuthorityAsset]:
    """Add catalog and/or custom assets. Catalog keys are idempotent (upsert).

    - {"asset_key": "<key>"}  → copy catalog name/type/provenance_domain; skip
      if the client already has that key.
    - {"name","asset_type", optional "url","provenance_domain"} → custom row.
    Returns the AuthorityAsset rows corresponding to the submitted items
    (existing row for an already-present key; the new row otherwise).
    """
    existing = {
        r.asset_key: r
        for r in db.query(AuthorityAsset)
        .filter(AuthorityAsset.client_id == client.id, AuthorityAsset.asset_key.isnot(None))
        .all()
    }
    result: list[AuthorityAsset] = []
    to_add: list[AuthorityAsset] = []
    for item in items:
        key = item.get("asset_key")
        if key:
            if key in existing:
                result.append(existing[key])
                continue
            cat = CATALOG_BY_KEY.get(key)
            if cat is None:
                continue  # unknown key — ignore rather than 500
            row = AuthorityAsset(
                client_id=client.id, asset_key=key, name=cat["name"],
                asset_type=cat["type"], provenance_domain=cat["provenance_domain"],
                url=item.get("url") or None,
            )
        else:
            name = (item.get("name") or "").strip()
            asset_type = item.get("asset_type") or "other"
            if not name or asset_type not in AUTHORITY_ASSET_TYPES:
                continue
            row = AuthorityAsset(
                client_id=client.id, asset_key=None, name=name, asset_type=asset_type,
                url=item.get("url") or None,
                provenance_domain=(item.get("provenance_domain") or None),
            )
        to_add.append(row)
        if key:
            existing[key] = row  # dedupe repeated catalog keys within one call
        result.append(row)

    if to_add:
        db.add_all(to_add)
        db.add(ActivityLog(
            client_id=client.id, event_type="authority_assets_added",
            note=f"Added {len(to_add)} authority asset(s) to the checklist.",
        ))
        db.commit()
        for row in to_add:
            db.refresh(row)
    return result


def update_asset(asset: AuthorityAsset, patch: dict, db: Session) -> AuthorityAsset:
    """Apply status/url/notes/hidden. Logs only when status actually changes."""
    status_changed = False
    if ("status" in patch and patch["status"] in AUTHORITY_ASSET_STATUSES
            and patch["status"] != asset.status):
        asset.status = patch["status"]
        status_changed = True
    if "url" in patch:
        asset.url = patch["url"] or None
    if "notes" in patch:
        asset.notes = patch["notes"] or None
    if "hidden" in patch and patch["hidden"] is not None:
        asset.hidden = bool(patch["hidden"])

    if status_changed:
        db.add(ActivityLog(
            client_id=asset.client_id, event_type="authority_status_changed",
            note=f"{asset.name} moved to {_STATUS_LABELS.get(asset.status, asset.status)}.",
        ))
    db.commit()
    db.refresh(asset)
    return asset


_VERIFY_TIMEOUT = 10.0
# A phone candidate: a run starting with an optional + then digits/space/-/()/.
_PHONE_RE = re.compile(r"\+?\d[\d\s\-().]{6,16}\d")


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def _phone_candidates(text: str) -> list[str]:
    """Digit-only phone candidates (9-13 significant digits) found in page text."""
    out: list[str] = []
    for match in _PHONE_RE.findall(text):
        digits = _digits(match)
        if 9 <= len(digits) <= 13:
            out.append(digits)
    return out


def _page_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(" ", strip=True)


def extract_nap(page_text: str, client: Client) -> dict:
    """Best-effort Name/Address/Phone signals from a directory page's text.

    Name = the client name when present (normalized). Phone = the first
    candidate that matches the client's phone by last-9-digit suffix, else the
    first candidate found. Address = a short window around the client's city.
    """
    name = client.name if detect_brand_mention(page_text, client.name) else None

    candidates = _phone_candidates(page_text)
    client_digits = _digits(client.phone)
    phone = None
    if client_digits:
        phone = next((c for c in candidates if c[-9:] == client_digits[-9:]), None)
    if phone is None and candidates:
        phone = candidates[0]

    address_text = None
    if client.city:
        idx = page_text.lower().find(client.city.lower())
        if idx != -1:
            start = max(0, idx - 40)
            address_text = page_text[start:idx + len(client.city) + 20].strip()

    return {"name": name, "phone": phone, "address_text": address_text}


def _nap_has_mismatch(found_nap: dict, client: Client) -> bool:
    """True only when a phone was found that disagrees with client.phone.

    No client phone on file, or no phone found on the page → not a mismatch
    (nothing to contradict). Compares the last 9 significant digits to tolerate
    country-code and separator formatting differences (spec §6)."""
    client_digits = _digits(client.phone)
    found_digits = _digits(found_nap.get("phone"))
    if not client_digits or not found_digits:
        return False
    return client_digits[-9:] != found_digits[-9:]


def verify_asset(asset: AuthorityAsset, client: Client, db: Session) -> tuple[AuthorityAsset, str]:
    """Single-page verification. Never raises; a failure sets last_checked_at
    and returns an honest note without touching status (spec §6, §10)."""
    if not asset.url:
        return asset, "Add the profile URL first, then run the check."

    note: str
    asset.last_checked_at = utcnow()
    try:
        if not is_safe_crawl_url(asset.url):
            note = "Couldn't reach that page safely — check the address."
        else:
            resp = safe_get(asset.url, timeout=_VERIFY_TIMEOUT)
            ctype = resp.headers.get("content-type", "").lower()
            if resp.status_code != 200 or ("html" not in ctype and ctype != ""):
                note = "Couldn't load that page — it didn't return a readable web page."
            else:
                text = _page_text(resp.text)
                found = extract_nap(text, client)
                asset.found_nap = found
                asset.nap_mismatch = _nap_has_mismatch(found, client)
                if found["name"]:
                    if asset.status != "verified":
                        asset.status = "verified"
                        db.add(ActivityLog(
                            client_id=asset.client_id,
                            event_type="authority_status_changed",
                            note=f"{asset.name} verified — the page names {client.name}.",
                        ))
                    note = "Verified — the page names this business."
                    if asset.nap_mismatch:
                        note += " Heads up: the phone number on the page differs from the one on file."
                else:
                    note = ("Couldn't confirm automatically — many directories load their "
                            "content in the browser. Verify by hand if the listing looks right.")
    except Exception as exc:  # network/parse — honest shrug, no status change
        logger.warning("authority_verify_failed", asset_id=str(asset.id), error=str(exc))
        note = "Couldn't reach that page — try again in a moment."

    db.commit()
    db.refresh(asset)
    return asset, note


def add_review_snapshot(
    asset: AuthorityAsset, rating: float, count: int, db: Session
) -> AuthorityAsset:
    """Append this month's {date, rating, count} to the review sparkline history."""
    snapshot = {
        "date": utcnow().date().isoformat(),
        "rating": round(float(rating), 2),
        "count": int(count),
    }
    # JSONB list needs reassignment for SQLAlchemy to detect the change.
    asset.review_snapshots = list(asset.review_snapshots or []) + [snapshot]
    db.add(ActivityLog(
        client_id=asset.client_id, event_type="review_snapshot_added",
        note=f"{asset.name}: {rating} stars, {count} reviews.",
    ))
    db.commit()
    db.refresh(asset)
    return asset
