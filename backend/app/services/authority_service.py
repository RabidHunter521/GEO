"""Authority & Presence Tracker — per-client authority checklist (spec §4-§10).

Nothing is auto-created for a client: rows exist only after the admin picks
from AUTHORITY_ASSET_CATALOG or adds a custom asset. Verification is a single
SSRF-guarded page read (Task 3); provenance-driven priorities read
scan_query_sources (Task 4). No score is written here — assets feed evidence
into the assisted Brand Authority flow, admin still gates the number.
"""
import uuid

import structlog
from sqlalchemy.orm import Session

from app.core.constants import AUTHORITY_ASSET_CATALOG, AUTHORITY_ASSET_STATUSES, AUTHORITY_ASSET_TYPES
from app.models.activity_log import ActivityLog
from app.models.authority_asset import AuthorityAsset
from app.models.client import Client

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
