# backend/tests/test_api_client_view_deliverables.py
# Read-only client-view deliverable endpoints: toolkit, roadmap, content-gaps,
# activity. Verifies whitelisting (internal fields never leak), completed-only
# gating, friendly activity mapping, and uniform 404 on a bad token.
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.client import Client
from app.models.toolkit_files import ToolkitFiles
from app.models.content_roadmap import ContentRoadmap
from app.models.content_analysis import ContentAnalysis
from app.models.activity_log import ActivityLog

TOKEN = "x" * 40  # >= 20 chars to satisfy the path constraint


@pytest.fixture
def db():
    # StaticPool: a single shared in-memory connection so the schema is visible
    # from the threadpool TestClient runs sync endpoints in.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    engine.dispose()


def _app(db):
    from app.main import app
    from app.core.database import get_db
    app.dependency_overrides[get_db] = lambda: db
    return app


def _seed_client(db) -> Client:
    c = Client(
        name="Acme Corp",
        website="https://acme.example",
        industry="Technology",
        share_token=TOKEN,
        logo_url="https://cdn.example/acme.png",
    )
    db.add(c)
    db.commit()
    return c


def test_invalid_token_returns_404(db):
    _seed_client(db)
    client = TestClient(_app(db))
    try:
        res = client.get(f"/api/v1/view/{'z' * 40}/toolkit")
        assert res.status_code == 404
    finally:
        client.app.dependency_overrides.clear()


def test_prospect_view_blocks_competitors_and_reports(db):
    # Prospects get overview + scan only; competitors/reports return uniform 404.
    c = _seed_client(db)
    c.is_prospect = True
    db.commit()
    client = TestClient(_app(db))
    try:
        assert client.get(f"/api/v1/view/{TOKEN}/competitors").status_code == 404
        assert client.get(f"/api/v1/view/{TOKEN}/competitors/trends").status_code == 404
        assert client.get(f"/api/v1/view/{TOKEN}/reports").status_code == 404
        # Overview stays reachable for prospects.
        assert client.get(f"/api/v1/view/{TOKEN}/overview").status_code == 200
    finally:
        client.app.dependency_overrides.clear()


def test_toolkit_returns_files_and_verification(db):
    c = _seed_client(db)
    db.add(ToolkitFiles(
        client_id=c.id,
        llms_txt="# llms",
        schema_json="{}",
        robots_txt="User-agent: GPTBot",
        llms_verified=True,
        schema_verified=False,
        robots_verified=True,
        verified_at=datetime(2026, 6, 1),
    ))
    db.commit()
    client = TestClient(_app(db))
    try:
        res = client.get(f"/api/v1/view/{TOKEN}/toolkit")
        assert res.status_code == 200
        body = res.json()
        assert body["llms_txt"] == "# llms"
        assert body["llms_verified"] is True
        assert body["schema_verified"] is False
        assert body["robots_verified"] is True
    finally:
        client.app.dependency_overrides.clear()


def test_toolkit_absent_returns_null(db):
    _seed_client(db)
    client = TestClient(_app(db))
    try:
        res = client.get(f"/api/v1/view/{TOKEN}/toolkit")
        assert res.status_code == 200
        assert res.json() is None
    finally:
        client.app.dependency_overrides.clear()


def test_roadmap_only_completed(db):
    c = _seed_client(db)
    # A pending roadmap must NOT surface.
    db.add(ContentRoadmap(client_id=c.id, status="pending", roadmap_json=[], source_query_count=0))
    db.commit()
    client = TestClient(_app(db))
    try:
        res = client.get(f"/api/v1/view/{TOKEN}/roadmap")
        assert res.status_code == 200
        assert res.json() is None
    finally:
        client.app.dependency_overrides.clear()


def test_roadmap_completed_returns_items(db):
    c = _seed_client(db)
    db.add(ContentRoadmap(
        client_id=c.id,
        status="completed",
        source_query_count=5,
        roadmap_json=[{
            "month": 1, "theme": "Local proof", "priority": "high",
            "content_type": "Blog post", "suggested_title": "Best in KL",
            "rationale": "Win back local queries",
            "target_queries": ["best tech in KL"],
            "competitors_winning": ["RivalCo"],
        }],
    ))
    db.commit()
    client = TestClient(_app(db))
    try:
        res = client.get(f"/api/v1/view/{TOKEN}/roadmap")
        assert res.status_code == 200
        body = res.json()
        assert body["source_query_count"] == 5
        assert len(body["items"]) == 1
        assert body["items"][0]["suggested_title"] == "Best in KL"
    finally:
        client.app.dependency_overrides.clear()


def test_content_gaps_excludes_internal_fields(db):
    c = _seed_client(db)
    db.add(ContentAnalysis(
        client_id=c.id,
        status="completed",
        topics_json=[{"topic": "Pricing", "status": "missing"}],
        entities_json=[{"entity": "KL office", "covered": False}],
        suggested_content_json=[{"topic": "Pricing", "title": "Pricing 101", "rationale": "Fill gap"}],
        entity_coverage_score=42.0,
        content_metrics_json={"word_count": 1200, "schema_present": True},
        content_quality_recommendation="Add an FAQ page.",
    ))
    db.commit()
    client = TestClient(_app(db))
    try:
        res = client.get(f"/api/v1/view/{TOKEN}/content-gaps")
        assert res.status_code == 200
        body = res.json()
        assert body["topics"][0]["topic"] == "Pricing"
        assert body["quality_recommendation"] == "Add an FAQ page."
        # Internal-only fields must never reach the client surface.
        assert "entity_coverage_score" not in body
        assert "content_metrics_json" not in body
        assert "content_metrics" not in body
    finally:
        client.app.dependency_overrides.clear()


def test_overview_section_flags(db):
    c = _seed_client(db)
    client = TestClient(_app(db))
    try:
        # No deliverables yet → both tabs hidden.
        res = client.get(f"/api/v1/view/{TOKEN}/overview")
        assert res.status_code == 200
        body = res.json()
        assert body["has_our_work"] is False
        assert body["has_content_plan"] is False
        assert body["profile"]["logo_url"] == "https://cdn.example/acme.png"

        # Add a toolkit → Our Work appears; a completed roadmap → Content Plan.
        db.add(ToolkitFiles(
            client_id=c.id, llms_txt="x", schema_json="{}", robots_txt="y",
        ))
        db.add(ContentRoadmap(
            client_id=c.id, status="completed", roadmap_json=[], source_query_count=0,
        ))
        db.commit()
        res2 = client.get(f"/api/v1/view/{TOKEN}/overview")
        body2 = res2.json()
        assert body2["has_our_work"] is True
        assert body2["has_content_plan"] is True
    finally:
        client.app.dependency_overrides.clear()


def test_activity_whitelist_and_mapping(db):
    c = _seed_client(db)
    db.add_all([
        ActivityLog(client_id=c.id, event_type="scan_completed", note="Scan done", created_at=datetime(2026, 6, 5)),
        ActivityLog(client_id=c.id, event_type="toolkit_verified", note="Live", created_at=datetime(2026, 6, 4)),
        # These must be filtered out of the client surface.
        ActivityLog(client_id=c.id, event_type="alert_sent", note="secret", created_at=datetime(2026, 6, 3)),
        ActivityLog(client_id=c.id, event_type="hallucination_flagged", note="secret", created_at=datetime(2026, 6, 2)),
        ActivityLog(client_id=c.id, event_type="share_link_revoked", note="secret", created_at=datetime(2026, 6, 1)),
    ])
    db.commit()
    client = TestClient(_app(db))
    try:
        res = client.get(f"/api/v1/view/{TOKEN}/activity")
        assert res.status_code == 200
        body = res.json()
        kinds = {e["kind"] for e in body}
        assert kinds == {"scan", "verified"}
        labels = {e["label"] for e in body}
        assert "AI visibility scan completed" in labels
        # No filtered events leaked.
        assert all(e["note"] != "secret" for e in body)
    finally:
        client.app.dependency_overrides.clear()
