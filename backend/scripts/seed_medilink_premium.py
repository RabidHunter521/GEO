# backend/scripts/seed_medilink_premium.py
"""Rebuild Medilink Healthcare as the flagship, fully-loaded demo client.

Deletes the existing Medilink Healthcare client (cascades through every
related table) and recreates it with:
  - 5 months of tenure, 5 monthly scans with a clean upward trend across
    every score dimension (ai_citability, brand_authority, content_quality,
    technical_foundations, structured_data)
  - every premium feature populated with plausible, internally-consistent
    fabricated data: control queries + guarantees (causality proof), Truth
    Vault facts, Authority & Presence checklist, misinformation compliance
    findings (one resolved, one open), delivery workspace (outcome actions +
    work log), page/site AI-readiness audits, conversion events, tracked
    query portfolio, Search Console signals, dimension assessments, content
    studio deliverables, and a real generated PDF report.

No real scans or external API calls are made for the scan data itself —
response text is templated (see scripts/seed_helpers.py). The one real
side effect is a single generate_report_pdf() call, which does call Claude
+ WeasyPrint + R2 like a real report would.

Run from backend/ with the project venv:
    python -m scripts.seed_medilink_premium
"""
import importlib
import pkgutil
import random
from datetime import date, datetime, timedelta

from sqlalchemy import delete, select

import app.models as _models_pkg

# Import every model module so SQLAlchemy's mapper registry can resolve
# string-based relationship() targets (e.g. ScanQueryResult -> ScanQuerySource)
# regardless of which models app/models/__init__.py happens to import.
for _mod in pkgutil.iter_modules(_models_pkg.__path__):
    importlib.import_module(f"app.models.{_mod.name}")

from app.core.database import SessionLocal
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan import Scan
from app.models.geo_score import GeoScore
from app.models.scan_query_result import ScanQueryResult
from app.models.share_of_source_snapshot import ShareOfSourceSnapshot
from app.models.toolkit_files import ToolkitFiles
from app.models.content_analysis import ContentAnalysis
from app.models.content_roadmap import ContentRoadmap
from app.models.content_brief import ContentBrief
from app.models.content_deliverable import ContentDeliverable
from app.models.action_recommendation import ActionRecommendation
from app.models.activity_log import ActivityLog
from app.models.ai_traffic_snapshot import AiTrafficSnapshot
from app.models.control_query import ControlQuery
from app.models.guarantee import Guarantee
from app.models.truth_fact import TruthFact, TruthFactVersion
from app.models.authority_asset import AuthorityAsset
from app.models.misinformation_finding import MisinformationFinding
from app.models.outcome_action import OutcomeAction
from app.models.work_log_entry import WorkLogEntry
from app.models.page_audit import PageAudit
from app.models.site_audit import SiteAudit
from app.models.conversion_event import ConversionEvent
from app.models.business_location import BusinessLocation
from app.models.tracked_query import TrackedQuery
from app.models.search_query_signal import SearchQuerySignal
from app.models.dimension_assessment import DimensionAssessment
from app.models.report import Report
from app.services.toolkit_service import generate_robots_txt
from app.services.report_service import generate_report_pdf

from scripts.seed_demo_clients import MEDILINK
from scripts.seed_helpers import (
    build_client_scan_results,
    build_llms_txt,
    build_schema_json,
    build_roadmap_json,
    compute_action_impact,
    compute_action_priority,
    make_content_brief_fields,
    save_geo_score,
)

NOW = datetime.utcnow()

# ---------------------------------------------------------------------------
# Timeline: 5 months of tenure, 5 monthly scans, clean upward trend.
# ---------------------------------------------------------------------------
CLIENT_CREATED = NOW - timedelta(days=150)
SHARE_LINK_CREATED = CLIENT_CREATED + timedelta(days=1)
TOOLKIT_GENERATED = NOW - timedelta(days=95)
TOOLKIT_VERIFIED = NOW - timedelta(days=93)

SCAN_OFFSETS_DAYS = [120, 90, 60, 30, 2]
SCAN_DATES = [NOW - timedelta(days=d) for d in SCAN_OFFSETS_DAYS]
N_SCANS = len(SCAN_DATES)

# Per-scan trajectories — every dimension climbs steadily.
VISIBILITY_TRAJECTORY = [
    {"chatgpt": 0.125, "perplexity": 0.0,   "gemini": 0.125, "claude": 0.0},
    {"chatgpt": 0.25,  "perplexity": 0.125, "gemini": 0.25,  "claude": 0.125},
    {"chatgpt": 0.375, "perplexity": 0.25,  "gemini": 0.375, "claude": 0.25},
    {"chatgpt": 0.5,   "perplexity": 0.375, "gemini": 0.5,   "claude": 0.375},
    {"chatgpt": 0.75,  "perplexity": 0.625, "gemini": 0.75,  "claude": 0.625},
]
BA_TRAJECTORY = [40, 46, 50, 54, 58]
CQ_TRAJECTORY = [35, 41, 46, 51, 55]
TF_VERIFIED_TRAJECTORY = [False, True, True, True, True]
SD_VERIFIED_TRAJECTORY = [False, True, True, True, True]
ENTITY_COVERAGE_TRAJECTORY = [34.0, 41.0, 47.0, 52.0, 56.0]
PAGES_CRAWLED_TRAJECTORY = [14, 18, 21, 24, 27]
CONTENT_METRICS_TRAJECTORY = [
    {"word_count": 3200, "h1_count": 10, "faq_count": 2, "blog_count": 0, "schema_present": False},
    {"word_count": 4400, "h1_count": 14, "faq_count": 3, "blog_count": 0, "schema_present": True},
    {"word_count": 5400, "h1_count": 17, "faq_count": 4, "blog_count": 1, "schema_present": True},
    {"word_count": 6100, "h1_count": 19, "faq_count": 4, "blog_count": 1, "schema_present": True},
    {"word_count": 6800, "h1_count": 21, "faq_count": 4, "blog_count": 1, "schema_present": True},
]
AI_TRAFFIC_TRAJECTORY = [640, 890, 1180, 1420, 1680]
SHARE_OF_SOURCE_TRAJECTORY = [
    {"total": 12, "client_pct": 8.3,  "shares": [("Sentosa Healthcare", 58.4), ("Care Clinic Group", 25.0), ("Medipulse Healthcare", 8.3)]},
    {"total": 18, "client_pct": 16.7, "shares": [("Sentosa Healthcare", 50.0), ("Care Clinic Group", 22.2), ("Medipulse Healthcare", 11.1)]},
    {"total": 24, "client_pct": 25.0, "shares": [("Sentosa Healthcare", 41.7), ("Care Clinic Group", 20.8), ("Medipulse Healthcare", 12.5)]},
    {"total": 30, "client_pct": 30.0, "shares": [("Sentosa Healthcare", 36.7), ("Care Clinic Group", 20.0), ("Medipulse Healthcare", 13.3)]},
    {"total": 38, "client_pct": 36.8, "shares": [("Sentosa Healthcare", 31.6), ("Care Clinic Group", 18.4), ("Medipulse Healthcare", 13.2)]},
]
ACQUISITION_DOMAINS = [
    ["healthhub.my"],
    ["healthhub.my", "klangvalleyliving.com"],
    ["healthhub.my", "klangvalleyliving.com", "mytown.com.my"],
    ["healthhub.my", "klangvalleyliving.com", "mytown.com.my", "expatgo.com"],
    ["healthhub.my", "klangvalleyliving.com", "mytown.com.my", "expatgo.com", "malaysiakini.com"],
]

# ---------------------------------------------------------------------------
# Control queries — deliberately untouched, run every scan, excluded from
# scoring. Fixed outcome per query proves causation: optimized queries moved,
# these didn't.
# ---------------------------------------------------------------------------
CONTROL_QUERIES = [
    {"query_text": "Best hospital for cardiology in Kuala Lumpur", "category": "recommendation", "detected": False},
    {"query_text": "Where can I get a flu vaccine in KL", "category": "local", "detected": True},
    {"query_text": "Medilink Healthcare Instagram page", "category": "brand", "detected": False},
]

PLATFORMS = ["chatgpt", "perplexity", "gemini", "claude"]


def _month_start_minus(d: date, months_back: int) -> date:
    y, m = d.year, d.month - months_back
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def _check(check_id, label, status, detail, fix=""):
    return {"id": check_id, "label": label, "status": status, "detail": detail, "fix": fix}


def build_site_audit_checks(tf_verified: bool, schema_present: bool, level: int) -> list[dict]:
    checks = []
    if tf_verified:
        checks.append(_check("robots_exists", "robots.txt present", "pass", "Found robots.txt at /robots.txt."))
        checks.append(_check("robots_ai_bots", "AI crawlers allowed", "pass", "GPTBot, PerplexityBot, ClaudeBot, and Google-Extended are explicitly allowed."))
        checks.append(_check("llms_txt", "llms.txt present", "pass", "Found llms.txt at /llms.txt."))
    else:
        checks.append(_check("robots_exists", "robots.txt present", "fail", "No robots.txt found at the site root.", "Generate and publish a robots.txt via the AI Readiness Toolkit."))
        checks.append(_check("robots_ai_bots", "AI crawlers allowed", "fail", "robots.txt does not explicitly allow AI crawlers.", "Allow GPTBot, PerplexityBot, ClaudeBot, and Google-Extended."))
        checks.append(_check("llms_txt", "llms.txt present", "fail", "No llms.txt found.", "Generate llms.txt via the AI Readiness Toolkit."))
    checks.append(_check(
        "llms_full_txt", "llms-full.txt present", "pass" if level >= 3 else "warn",
        "Found llms-full.txt at /llms-full.txt." if level >= 3 else "Optional file not yet generated.",
        "" if level >= 3 else "Generate llms-full.txt for deeper AI context (optional).",
    ))
    checks.append(_check("https", "Served over HTTPS", "pass", "The site is served over a secure connection."))
    sm_status = "pass" if level >= 1 else "warn"
    checks.append(_check("sitemap_exists", "Sitemap present", sm_status, "Found sitemap.xml." if sm_status == "pass" else "Sitemap present but not linked from robots.txt.", "" if sm_status == "pass" else "Link the sitemap from robots.txt."))
    checks.append(_check("sitemap_urls", "Sitemap URL count", "pass" if level >= 1 else "unknown", f"Sitemap lists {20 + level * 15} URLs." if level >= 1 else "Unable to determine URL count."))
    checks.append(_check("sitemap_fresh", "Sitemap freshness", "pass" if level >= 2 else "warn", "Sitemap last modified within 30 days." if level >= 2 else "Sitemap has not been updated recently.", "" if level >= 2 else "Regenerate the sitemap after publishing new pages."))
    title_status = "pass" if level >= 1 else "warn"
    checks.append(_check("title", "Page title", title_status, "Title found and descriptive." if title_status == "pass" else "Title is present but generic.", "" if title_status == "pass" else "Write a more specific, descriptive title."))
    meta_status = "pass" if level >= 2 else "fail"
    checks.append(_check("meta_description", "Meta description", meta_status, "Meta description found and descriptive." if meta_status == "pass" else "No meta description found.", "" if meta_status == "pass" else "Add a meta description summarizing the page."))
    checks.append(_check("canonical", "Canonical URL", "pass", "Preferred address declared."))
    og_status = "pass" if level >= 2 else "warn"
    checks.append(_check("open_graph", "Open Graph tags", og_status, "Open Graph tags present." if og_status == "pass" else "Partial Open Graph tags.", "" if og_status == "pass" else "Add missing Open Graph tags for social sharing."))
    checks.append(_check("h1", "Single main headline", "pass", "The homepage has exactly one main headline."))
    ho_status = "pass" if level >= 1 else "warn"
    checks.append(_check("heading_order", "Heading order", ho_status, "Headings follow a logical order." if ho_status == "pass" else "Heading levels skip (e.g. H1 to H3).", "" if ho_status == "pass" else "Fix heading hierarchy so levels are not skipped."))
    checks.append(_check("viewport", "Mobile viewport", "pass", "The page is set up for mobile screens."))
    il_status = "pass" if level >= 1 else "warn"
    checks.append(_check("internal_links", "Internal linking", il_status, "Pages link to related content." if il_status == "pass" else "Few internal links to related content.", "" if il_status == "pass" else "Add internal links between related service pages."))
    checks.append(_check("response_time", "Response time", "pass", "Homepage responded quickly."))
    if schema_present:
        checks.append(_check("jsonld_present", "Structured data present", "pass", "Found JSON-LD structured data."))
        checks.append(_check("jsonld_types", "Structured data types", "pass" if level >= 2 else "warn", "Organization, MedicalClinic, and FAQPage types found." if level >= 2 else "Organization type found; FAQPage missing.", "" if level >= 2 else "Add FAQPage structured data."))
    else:
        checks.append(_check("jsonld_present", "Structured data present", "fail", "No JSON-LD structured data found.", "Generate schema.json via the AI Readiness Toolkit."))
        checks.append(_check("jsonld_types", "Structured data types", "fail", "No structured data types found.", "Publish Organization, MedicalClinic, and FAQPage schema."))
    return checks


def _score_check(check_id, label, status, detail, max_points, fix=""):
    earned = max_points if status == "pass" else (max_points // 2 if status == "warn" else 0)
    return {"id": check_id, "label": label, "status": status, "detail": detail, "points": earned, "fix": fix}


def build_page_audit(before: bool) -> tuple[int, list[dict], list[dict]]:
    if before:
        checks = [
            _score_check("answer_up_front", "Answer up front", "fail", "The page opens with a general intro rather than a direct answer.", 20, "Lead with the direct answer in the first two sentences."),
            _score_check("question_headings", "Question-style headings", "warn", "Only one heading is phrased as a question.", 15, "Rephrase key section headings as the questions patients actually ask."),
            _score_check("faq_block", "FAQ section", "fail", "No dedicated question-and-answer section.", 10, "Add a FAQ block covering the most common screening questions."),
            _score_check("scannable_structure", "Tables and lists", "warn", "Package details are in paragraphs rather than a comparison table.", 15, "Convert the package list into a scannable table."),
            _score_check("paragraph_length", "Paragraph length", "warn", "Several paragraphs run over 150 words.", 10, "Break long paragraphs into shorter, focused ones."),
            _score_check("heading_density", "Heading coverage", "fail", "Long stretches of text with no subheading.", 10, "Add subheadings every 200-300 words."),
            _score_check("definitions", "Plain definition", "fail", "Screening terms are used without a plain-language definition.", 10, "Define each screening term in plain language on first use."),
            _score_check("word_count", "Page length", "pass", "About 950 words.", 10),
        ]
        score = sum(c["points"] for c in checks)
        suggestions = [
            {"section": "Intro", "issue": "Doesn't answer the question in the first two sentences.", "rewrite": "Medilink Healthcare's health screening packages start from RM180 and include blood work, BMI, and blood pressure checks — here's what's included in each tier."},
            {"section": "Packages", "issue": "Package details are buried in paragraphs.", "rewrite": "Present Basic / Standard / Comprehensive packages as a table with price, tests included, and who it's for."},
        ]
        return score, checks, suggestions
    checks = [
        _score_check("answer_up_front", "Answer up front", "pass", "The page opens with the direct answer and price range.", 20),
        _score_check("question_headings", "Question-style headings", "pass", "Section headings are phrased as the questions patients ask.", 15),
        _score_check("faq_block", "FAQ section", "pass", "A dedicated FAQ section covers common screening questions.", 10),
        _score_check("scannable_structure", "Tables and lists", "pass", "Package details are presented in a comparison table.", 15),
        _score_check("paragraph_length", "Paragraph length", "pass", "Paragraphs are short and focused.", 10),
        _score_check("heading_density", "Heading coverage", "pass", "Subheadings appear every 200-300 words.", 10),
        _score_check("definitions", "Plain definition", "warn", "Most terms are defined; one abbreviation is still unexplained.", 10, "Define 'MOH panel' on first use."),
        _score_check("word_count", "Page length", "pass", "About 1,450 words.", 10),
    ]
    score = sum(c["points"] for c in checks)
    suggestions = [
        {"section": "Terminology", "issue": "'MOH panel' is used without explanation.", "rewrite": "Add a one-line definition: 'MOH panel clinics are registered with Malaysia's Ministry of Health to provide subsidised or employer-covered care.'"},
    ]
    return score, checks, suggestions


# Models to hard-delete-and-rebuild for Medilink. Deliberately EXCLUDES
# TruthFact / TruthFactVersion: an append-only Postgres trigger (migration
# b9e5a3d2c8f0) blocks both UPDATE and DELETE on truth_fact_versions, and the
# truth_facts -> truth_fact_versions FK has no ON DELETE, so any existing
# approved fact (e.g. the "official_name"/"website"/... rows the one-time
# truth_backfill_service already wrote for this client) is permanently
# undeletable. We keep those and only add new, non-colliding facts below.
_WIPE_MODELS = [
    ActionRecommendation, ContentDeliverable, ContentBrief, ContentRoadmap, ContentAnalysis,
    ShareOfSourceSnapshot, GeoScore, Scan, ToolkitFiles, ActivityLog,
    AiTrafficSnapshot, ControlQuery, Guarantee, AuthorityAsset, MisinformationFinding,
    OutcomeAction, WorkLogEntry, PageAudit, SiteAudit, ConversionEvent,
    TrackedQuery, SearchQuerySignal, DimensionAssessment, Report, Competitor,
]
# ScanQueryResult has no client_id column (only scan_id) — deleting Scan rows
# above cascades it at the DB level (scan_query_results.scan_id ON DELETE CASCADE).
# BusinessLocation is likewise excluded: the one-time truth_backfill_service
# already wrote location-scoped TruthFacts (fact_type="location") against the
# client's existing primary location, and truth_fact_versions is append-only
# (see TruthFact note above) — deleting that location would cascade-delete
# those facts and hit the same undeletable-version wall. We update it in place
# instead of replacing it.


def main() -> None:
    db = SessionLocal()
    try:
        client = db.query(Client).filter(Client.name == "Medilink Healthcare").first()
        if client is None:
            client_kwargs = dict(MEDILINK["client"])
            client = Client(**client_kwargs)
            db.add(client)
            db.flush()
            print(f"Created client {client.id}")
        else:
            print(f"Reusing existing client {client.id}; wiping rebuildable child tables...")
            for model in _WIPE_MODELS:
                db.execute(delete(model).where(model.client_id == client.id))
            db.flush()

        client_kwargs = dict(MEDILINK["client"])
        client_kwargs.pop("brand_authority_score", None)
        client_kwargs.pop("content_quality_score", None)
        for field, value in client_kwargs.items():
            setattr(client, field, value)
        client.brand_authority_score = BA_TRAJECTORY[0]
        client.content_quality_score = CQ_TRAJECTORY[0]
        client.technical_foundations_verified = False
        client.structured_data_verified = False
        client.created_at = CLIENT_CREATED
        client.share_token = "medilink-flagship-demo-" + str(int(NOW.timestamp()))
        client.share_token_created_at = SHARE_LINK_CREATED
        client.benchmark_opt_out = False
        client.archived_at = None
        client.is_prospect = False
        db.flush()

        competitors = []
        for comp in MEDILINK["competitors"]:
            c = Competitor(client_id=client.id, name=comp["name"], website=comp["website"])
            db.add(c)
            competitors.append(c)
        db.flush()

        # The primary location is truth_backfill_service-owned and undeletable
        # (see _WIPE_MODELS note) — update it in place rather than replacing it.
        primary_location = db.query(BusinessLocation).filter(
            BusinessLocation.client_id == client.id, BusinessLocation.is_primary.is_(True)
        ).first()
        if primary_location is None:
            primary_location = BusinessLocation(client_id=client.id, slug="bangsar", is_primary=True, created_at=CLIENT_CREATED + timedelta(days=1))
            db.add(primary_location)
        primary_location.name = "Medilink Healthcare — Bangsar"
        primary_location.website = client.website
        primary_location.address_line_1 = "12-1, Jalan Telawi 3, Bangsar Baru"
        primary_location.city = "Kuala Lumpur"
        primary_location.state = "Wilayah Persekutuan Kuala Lumpur"
        primary_location.postcode = "59100"
        primary_location.country = "MY"
        primary_location.phone = "+603-2282 1188"
        primary_location.hours_json = {
            "monday": [{"open": "08:00", "close": "20:00"}], "tuesday": [{"open": "08:00", "close": "20:00"}],
            "wednesday": [{"open": "08:00", "close": "20:00"}], "thursday": [{"open": "08:00", "close": "20:00"}],
            "friday": [{"open": "08:00", "close": "20:00"}], "saturday": [{"open": "08:00", "close": "17:00"}],
            "sunday": [{"open": "09:00", "close": "13:00"}],
        }
        primary_location.booking_url = "https://medilinkhealthcare.my/book/bangsar"
        primary_location.active = True
        db.flush()

        cheras_location = BusinessLocation(
            client_id=client.id, name="Medilink Healthcare — Cheras", slug="cheras",
            is_primary=False, website=client.website,
            address_line_1="G-3, Jalan Cheras Baru 5, Taman Cheras Baru",
            city="Kuala Lumpur", state="Wilayah Persekutuan Kuala Lumpur", postcode="56000", country="MY",
            phone="+603-9130 4477",
            hours_json={
                "monday": [{"open": "08:30", "close": "19:00"}], "tuesday": [{"open": "08:30", "close": "19:00"}],
                "wednesday": [{"open": "08:30", "close": "19:00"}], "thursday": [{"open": "08:30", "close": "19:00"}],
                "friday": [{"open": "08:30", "close": "19:00"}], "saturday": [{"open": "08:30", "close": "16:00"}],
                "sunday": [],
            },
            booking_url="https://medilinkhealthcare.my/book/cheras",
            created_at=CLIENT_CREATED + timedelta(days=45),
        )
        db.add(cheras_location)
        db.flush()
        locations = [primary_location, cheras_location]

        activity: list[tuple[datetime, str, str]] = [
            (CLIENT_CREATED, "client_created", "Client Medilink Healthcare created."),
            (SHARE_LINK_CREATED, "share_link_generated", "Client view share link generated."),
            (CLIENT_CREATED + timedelta(days=45), "location_added", "Second clinic location added: Medilink Healthcare — Cheras."),
        ]

        # -------------------------------------------------------------
        # Control queries (persisted definitions)
        # -------------------------------------------------------------
        for cq in CONTROL_QUERIES:
            db.add(ControlQuery(client_id=client.id, query_text=cq["query_text"], category=cq["category"], active=True, created_at=CLIENT_CREATED + timedelta(days=2)))
        db.flush()

        # -------------------------------------------------------------
        # 5 scans, ascending scores
        # -------------------------------------------------------------
        scan_profile_base = dict(MEDILINK["scan_profile"])
        last_geo_score = None
        latest_scan = None
        latest_results = None
        latest_lost = None
        misinfo_result_wrong_service = None
        misinfo_result_outdated = None

        for i in range(N_SCANS):
            scan_date = SCAN_DATES[i]
            scan = Scan(
                client_id=client.id, platform="multi", status="completed",
                triggered_at=scan_date - timedelta(minutes=25),
                completed_at=scan_date,
            )
            db.add(scan)
            db.flush()

            profile = dict(scan_profile_base)
            profile["client_visibility"] = VISIBILITY_TRAJECTORY[i]

            rng = random.Random(f"medilink-scan-{i}")
            results, lost = build_client_scan_results(profile, rng, scan.id, client.name, competitors)

            # Control query rows — fixed outcome, every platform, every scan.
            for platform in PLATFORMS:
                for cq in CONTROL_QUERIES:
                    opener = "I found" if cq["detected"] else "I do not have specific information about"
                    response = f"{opener} Medilink Healthcare for this query."
                    results.append(ScanQueryResult(
                        scan_id=scan.id, platform=platform, competitor_id=None,
                        category=cq["category"], query_text=cq["query_text"],
                        response_text=response, brand_detected=cq["detected"], is_control=True,
                    ))

            # Hand-written misinformation-bearing rows (see below).
            if i == 1:
                misinfo_result_wrong_service = ScanQueryResult(
                    scan_id=scan.id, platform="chatgpt", competitor_id=None, category="brand",
                    query_text="What services does Medilink Healthcare offer?",
                    response_text=(
                        "Based on what I know, Medilink Healthcare is a primary care and health screening "
                        "provider based in Kuala Lumpur. Medilink Healthcare also provides in-house dialysis "
                        "and 24-hour emergency trauma surgery across its Klang Valley clinics, alongside GP "
                        "consultations and health screening packages."
                    ),
                    brand_detected=True, hallucination_flagged=True,
                )
                results.append(misinfo_result_wrong_service)
            if i == N_SCANS - 1:
                misinfo_result_outdated = ScanQueryResult(
                    scan_id=scan.id, platform="perplexity", competitor_id=None, category="local",
                    query_text="Best health screening near me in Kuala Lumpur",
                    response_text=(
                        "According to recent sources, Medilink Healthcare's Bangsar clinic is open Monday to "
                        "Friday, 9am-5pm only, with no weekend hours, and offers health screening packages "
                        "alongside Sentosa Healthcare and Care Clinic Group."
                    ),
                    brand_detected=True, hallucination_flagged=True,
                )
                results.append(misinfo_result_outdated)

            db.add_all(results)
            db.flush()

            client.brand_authority_score = BA_TRAJECTORY[i]
            client.content_quality_score = CQ_TRAJECTORY[i]
            client.technical_foundations_verified = TF_VERIFIED_TRAJECTORY[i]
            client.structured_data_verified = SD_VERIFIED_TRAJECTORY[i]
            db.flush()

            geo_score = save_geo_score(db, client, scan, results, computed_at=scan_date)
            db.flush()

            sos = SHARE_OF_SOURCE_TRAJECTORY[i]
            db.add(ShareOfSourceSnapshot(
                client_id=client.id, scan_id=scan.id, computed_at=scan_date + timedelta(hours=1),
                total_third_party_sources=sos["total"], client_share_pct=sos["client_pct"],
                competitor_shares=[{"name": name, "share_pct": pct} for name, pct in sos["shares"]],
                acquisition_list=[{"domain": d, "count": idx + 1} for idx, d in enumerate(ACQUISITION_DOMAINS[i])],
            ))

            ca = MEDILINK["content_analysis"]
            db.add(ContentAnalysis(
                client_id=client.id, status="completed",
                topics_json=ca["topics_json"], entities_json=ca["entities_json"],
                suggested_content_json=ca["suggested_content_json"],
                entity_coverage_score=ENTITY_COVERAGE_TRAJECTORY[i],
                content_metrics_json=CONTENT_METRICS_TRAJECTORY[i],
                content_quality_recommendation=ca["content_quality_recommendation"],
                pages_crawled=PAGES_CRAWLED_TRAJECTORY[i],
                analyzed_at=scan_date + timedelta(hours=2),
            ))

            level = i  # 0..4, drives site audit maturity
            checks = build_site_audit_checks(TF_VERIFIED_TRAJECTORY[i], CONTENT_METRICS_TRAJECTORY[i]["schema_present"], level)
            counts = {"pass": 0, "warn": 0, "fail": 0, "unknown": 0}
            for c in checks:
                counts[c["status"]] += 1
            db.add(SiteAudit(
                client_id=client.id, checks=checks,
                passed=counts["pass"], warned=counts["warn"], failed=counts["fail"], unknown=counts["unknown"],
                created_at=scan_date + timedelta(hours=1),
            ))

            activity.append((scan_date, "scan_completed", f"Scan completed across 4 platforms. Overall score: {geo_score.overall_score:.0f}."))

            last_geo_score = geo_score
            latest_scan = scan
            latest_results = results
            latest_lost = lost

        db.flush()

        # -------------------------------------------------------------
        # AI Readiness Toolkit (verified from month 2 onward)
        # -------------------------------------------------------------
        toolkit = MEDILINK["toolkit"]
        llms_txt = build_llms_txt(client.name, client.website, toolkit["tagline"], toolkit["about"], toolkit["sections"])
        schema_json = build_schema_json(
            client.name, client.website, toolkit["tagline"], toolkit["business_type"],
            client.city, client.state, client.country, toolkit["faqs"],
        )
        robots_txt = generate_robots_txt(client)
        db.add(ToolkitFiles(
            client_id=client.id,
            llms_txt=llms_txt, schema_json=schema_json, robots_txt=robots_txt,
            generated_at=TOOLKIT_GENERATED,
            llms_verified=True, schema_verified=True, robots_verified=True,
            verified_at=TOOLKIT_VERIFIED,
        ))
        activity.append((TOOLKIT_GENERATED, "toolkit_generated", "AI Readiness Toolkit files generated (llms.txt, schema.json, robots.txt)."))
        activity.append((TOOLKIT_VERIFIED, "toolkit_verified", "Toolkit verification run. Files verified: llms.txt, schema.json, robots.txt."))

        # -------------------------------------------------------------
        # Content roadmap + briefs + deliverables (Content Studio)
        # -------------------------------------------------------------
        roadmap_json = build_roadmap_json(MEDILINK["roadmap_themes"], latest_lost)
        roadmap_json[0]["article_content"] = (
            "# Medilink Healthcare Health Screening Guide\n\n"
            "Medilink Healthcare offers three health screening tiers — Basic, Standard, and "
            "Comprehensive — starting from RM180. Each package includes a doctor consultation, "
            "blood work, BMI and blood pressure checks...\n\n"
            "*(Published to medilinkhealthcare.my in month 2 of the retainer.)*"
        )
        roadmap_json[1]["article_content"] = (
            "# Corporate Health Screening & Occupational Health with Medilink Healthcare\n\n"
            "For HR teams evaluating panel clinic options, Medilink Healthcare's corporate "
            "programme covers pre-employment screening, annual staff health checks, and "
            "on-site occupational health assessments across its Bangsar and Cheras clinics...\n\n"
            "*(Published to medilinkhealthcare.my in month 3 of the retainer.)*"
        )
        db.add(ContentRoadmap(
            client_id=client.id, status="completed",
            roadmap_json=roadmap_json, source_query_count=len(latest_lost),
            generated_at=NOW - timedelta(days=28), created_at=NOW - timedelta(days=28),
        ))
        activity.append((NOW - timedelta(days=28), "content_analyzed", "Content gap analysis and 90-day roadmap refreshed."))

        brief_notes = []
        for entry in latest_lost[:3]:
            result = entry["result"]
            title, angle, outline = make_content_brief_fields(
                client.name, MEDILINK["scan_profile"]["industry_phrase"],
                MEDILINK["scan_profile"]["location"], MEDILINK["scan_profile"]["city"],
                result.query_text, entry["competitors_seen"], result.category,
            )
            db.add(ContentBrief(
                client_id=client.id, scan_query_result_id=result.id,
                platform=result.platform, query_text=result.query_text,
                competitors_seen=entry["competitors_seen"],
                title=title, angle=angle, outline=outline,
                generated_at=NOW - timedelta(days=25),
            ))
            brief_notes.append(result.query_text)

        db.add_all([
            ContentDeliverable(
                client_id=client.id, type="faq_pack",
                title="Medilink Healthcare Health Screening & Corporate Health FAQ Pack",
                body_md=(
                    "## What services does Medilink Healthcare offer?\n"
                    "Medilink Healthcare offers GP consultations, health screening packages, "
                    "occupational and corporate health services, vaccinations, and specialist "
                    "referrals through its Klang Valley clinics.\n\n"
                    "## Does Medilink Healthcare provide corporate health screening?\n"
                    "Yes — Medilink Healthcare runs corporate and occupational health programmes, "
                    "including staff health screening and panel clinic arrangements for companies.\n\n"
                    "## How do I book a health screening?\n"
                    "Health screening appointments can be booked directly through either clinic or "
                    "via the booking form on medilinkhealthcare.my.\n\n"
                    "## Is Medilink Healthcare on any corporate insurance panels?\n"
                    "Medilink Healthcare participates in a number of corporate panel and cashless "
                    "arrangements; contact the clinic directly to confirm your specific panel."
                ),
                source_context={"scan_id": str(latest_scan.id)},
                status="reviewed", generated_at=NOW - timedelta(days=24), reviewed_at=NOW - timedelta(days=23),
            ),
            ContentDeliverable(
                client_id=client.id, type="comparison_page", competitor_id=competitors[0].id,
                title="Medilink Healthcare vs Sentosa Healthcare: Which Is Right for You?",
                body_md=(
                    "# Medilink Healthcare vs Sentosa Healthcare\n\n"
                    "Both Medilink Healthcare and Sentosa Healthcare serve patients across the Klang "
                    "Valley, but they specialize differently. Sentosa Healthcare is a hospital-grade "
                    "specialist group offering inpatient and diagnostic services. Medilink Healthcare "
                    "focuses on accessible primary care, health screening, and corporate occupational "
                    "health across its Bangsar and Cheras clinics — a better fit for routine checkups, "
                    "staff health screening, and same-week GP appointments.\n\n"
                    "Choose Medilink Healthcare if you need fast, affordable primary care or a "
                    "corporate screening partner. Choose Sentosa Healthcare if you need specialist or "
                    "inpatient hospital care."
                ),
                source_context={"scan_id": str(latest_scan.id)},
                status="reviewed", generated_at=NOW - timedelta(days=20), reviewed_at=NOW - timedelta(days=19),
            ),
            ContentDeliverable(
                client_id=client.id, type="glossary",
                title="Health Screening & Occupational Health Glossary",
                body_md=(
                    "**GP consultation** — a general practitioner visit for diagnosis, treatment, and "
                    "referrals.\n\n"
                    "**Health screening package** — a bundled set of tests (blood work, BMI, blood "
                    "pressure, and more) offered at a fixed price.\n\n"
                    "**Occupational health services** — workplace-focused health services such as "
                    "pre-employment screening and fitness-for-work assessments.\n\n"
                    "**MOH panel clinic** — a clinic registered with Malaysia's Ministry of Health, "
                    "often used for employer or insurer panel arrangements.\n\n"
                    "**Corporate wellness programme** — an employer-sponsored package of screening and "
                    "preventive care for staff."
                ),
                source_context={},
                status="reviewed", generated_at=NOW - timedelta(days=15), reviewed_at=NOW - timedelta(days=14),
            ),
        ])
        for q in brief_notes:
            activity.append((NOW - timedelta(days=25), "brief_generated", f"Content brief generated for query: {q[:100]}"))

        # -------------------------------------------------------------
        # Action recommendations — some resolved historically, some open now
        # -------------------------------------------------------------
        dimension_scores = {
            "ai_citability": last_geo_score.ai_citability,
            "brand_authority": last_geo_score.brand_authority,
            "content_quality": last_geo_score.content_quality,
            "technical_foundations": last_geo_score.technical_foundations,
            "structured_data": last_geo_score.structured_data,
        }
        for action in MEDILINK["actions"]:
            impact = compute_action_impact(action["dimension"], dimension_scores[action["dimension"]], action["closable_fraction"])
            db.add(ActionRecommendation(
                client_id=client.id, geo_score_id=last_geo_score.id,
                action_text=action["action_text"], dimension=action["dimension"],
                estimated_impact=impact, priority=compute_action_priority(impact),
                status="open", generated_at=NOW - timedelta(hours=20),
            ))
        # Two historical actions already closed out, to show a working loop.
        db.add_all([
            ActionRecommendation(
                client_id=client.id, geo_score_id=None,
                action_text="Publish health-screening explainer pages so AI assistants have a Medilink source to cite for screening questions.",
                dimension="ai_citability", estimated_impact=7.4, priority="high",
                status="done", generated_at=NOW - timedelta(days=88), resolved_at=NOW - timedelta(days=58),
            ),
            ActionRecommendation(
                client_id=client.id, geo_score_id=None,
                action_text="Ship llms.txt, schema.json, and an AI-crawler-open robots.txt via the AI Readiness Toolkit.",
                dimension="technical_foundations", estimated_impact=4.0, priority="high",
                status="done", generated_at=NOW - timedelta(days=96), resolved_at=NOW - timedelta(days=93),
            ),
        ])

        # -------------------------------------------------------------
        # AI traffic snapshots — 5 months, ascending
        # -------------------------------------------------------------
        current_month = NOW.date().replace(day=1)
        for k in range(N_SCANS - 1, -1, -1):
            period = _month_start_minus(current_month, k)
            db.add(AiTrafficSnapshot(client_id=client.id, period=period, ai_visitors=AI_TRAFFIC_TRAJECTORY[N_SCANS - 1 - k]))
        activity.append((NOW - timedelta(hours=18), "traffic_updated", "AI traffic snapshot recorded for this month."))

        # -------------------------------------------------------------
        # Guarantee engine — one met, one active
        # -------------------------------------------------------------
        db.add(Guarantee(
            client_id=client.id, metric="ai_citability",
            baseline_value=18, target_value=55,
            start_date=(CLIENT_CREATED + timedelta(days=5)).date(),
            deadline_date=(NOW - timedelta(days=20)).date(),
            status="met", last_state="met",
            resolved_at=NOW - timedelta(days=18),
            admin_note=(
                "Guarantee met — AI Citability grew from 18 to 61 across the retainer, driven by the "
                "health-screening explainer hub and corporate health content shipped in months 2-3. "
                "Remedy: one free month applied per engagement letter."
            ),
            created_at=CLIENT_CREATED + timedelta(days=5),
        ))
        db.add(Guarantee(
            client_id=client.id, metric="overall",
            baseline_value=41, target_value=68,
            start_date=(NOW - timedelta(days=25)).date(),
            deadline_date=(NOW + timedelta(days=65)).date(),
            status="active", last_state="on_track",
            admin_note="Second guarantee opened after the first was met — extending the commitment to overall Growth Readiness.",
            created_at=NOW - timedelta(days=25),
        ))
        activity.append((CLIENT_CREATED + timedelta(days=5), "guarantee_opened", "Guarantee opened: AI Citability 18 -> 55."))
        activity.append((NOW - timedelta(days=18), "guarantee_met", "Guarantee met: AI Citability reached 61 (target 55)."))
        activity.append((NOW - timedelta(days=25), "guarantee_opened", "Second guarantee opened: overall Growth Readiness 41 -> 68."))

        # -------------------------------------------------------------
        # Truth Vault
        # -------------------------------------------------------------
        truth_specs = [
            ("business_hours", "general", {"mon_fri": "8:00 AM - 8:00 PM", "sat": "8:00 AM - 5:00 PM", "sun": "9:00 AM - 1:00 PM"},
             "Mon-Fri 8:00 AM - 8:00 PM, Sat 8:00 AM - 5:00 PM, Sun 9:00 AM - 1:00 PM"),
            ("contact", "phone", "+603-2282 1188", "+603-2282 1188"),
            ("contact", "email", "enquiry@medilinkhealthcare.my", "enquiry@medilinkhealthcare.my"),
            ("service", "health_screening_packages", {"basic": "RM180", "standard": "RM320", "comprehensive": "RM580"},
             "Basic RM180, Standard RM320, Comprehensive RM580"),
            ("service", "occupational_health",
             "On-site pre-employment screening, annual staff health checks, and fitness-for-work assessments for corporate clients.",
             "On-site pre-employment screening, annual staff health checks, and fitness-for-work assessments for corporate clients."),
            ("credential", "clinic_registration",
             "Registered under the Ministry of Health Malaysia; facility code MHC-KL-0417.",
             "Registered under the Ministry of Health Malaysia; facility code MHC-KL-0417."),
        ]
        truth_fact_by_key = {}
        for fact_type, fact_key, value, display_value in truth_specs:
            tf = TruthFact(client_id=client.id, location_id=None, fact_type=fact_type, fact_key=fact_key, created_at=CLIENT_CREATED + timedelta(days=10))
            db.add(tf)
            db.flush()
            version = TruthFactVersion(
                truth_fact_id=tf.id, value_json={"value": value, "display_value": display_value}, status="approved",
                source_url=client.website, reviewer_note="Confirmed against clinic records.",
                effective_from=CLIENT_CREATED + timedelta(days=10), effective_to=None,
                approved_at=CLIENT_CREATED + timedelta(days=10), approved_by="Faris",
                created_at=CLIENT_CREATED + timedelta(days=10),
            )
            db.add(version)
            db.flush()
            truth_fact_by_key[(fact_type, fact_key)] = (tf, version)
        activity.append((CLIENT_CREATED + timedelta(days=10), "truth_vault_seeded", "Truth Vault populated with 6 approved business facts."))

        # -------------------------------------------------------------
        # Authority & Presence checklist
        # -------------------------------------------------------------
        db.add_all([
            AuthorityAsset(
                client_id=client.id, asset_key="gbp", name="Google Business Profile", asset_type="review_platform",
                url="https://business.google.com/", status="verified", provenance_domain="google.com",
                review_snapshots=[
                    {"date": (CLIENT_CREATED + timedelta(days=20)).date().isoformat(), "rating": 4.1, "count": 62},
                    {"date": (NOW - timedelta(days=60)).date().isoformat(), "rating": 4.3, "count": 128},
                    {"date": (NOW - timedelta(days=5)).date().isoformat(), "rating": 4.6, "count": 214},
                ],
                found_nap={"name": "Medilink Healthcare", "phone": "+603-2282 1188", "address_text": "12-1, Jalan Telawi 3, Bangsar Baru, Kuala Lumpur"},
                nap_mismatch=False, last_checked_at=NOW - timedelta(days=5),
                created_at=CLIENT_CREATED + timedelta(days=20),
            ),
            AuthorityAsset(
                client_id=client.id, asset_key="facebook_reviews", name="Facebook Page reviews", asset_type="review_platform",
                url="https://www.facebook.com/medilinkhealthcare", status="live", provenance_domain="facebook.com",
                review_snapshots=[
                    {"date": (NOW - timedelta(days=90)).date().isoformat(), "rating": 4.0, "count": 34},
                    {"date": (NOW - timedelta(days=10)).date().isoformat(), "rating": 4.4, "count": 79},
                ],
                last_checked_at=NOW - timedelta(days=10), created_at=CLIENT_CREATED + timedelta(days=30),
            ),
            AuthorityAsset(
                client_id=client.id, asset_key="myhealth_clinic", name="MyHEALTH / MMC clinic directory", asset_type="directory",
                url="http://www.myhealth.gov.my/", status="verified", provenance_domain="myhealth.gov.my",
                found_nap={"name": "Medilink Healthcare", "phone": "+603-2282 1188", "address_text": "Bangsar Baru, Kuala Lumpur"},
                nap_mismatch=False, last_checked_at=NOW - timedelta(days=12), created_at=CLIENT_CREATED + timedelta(days=25),
            ),
            AuthorityAsset(
                client_id=client.id, asset_key="linkedin", name="LinkedIn company page", asset_type="social",
                url="https://www.linkedin.com/company/medilink-healthcare", status="live", provenance_domain="linkedin.com",
                last_checked_at=NOW - timedelta(days=15), created_at=CLIENT_CREATED + timedelta(days=35),
            ),
            AuthorityAsset(
                client_id=client.id, asset_key="facebook", name="Facebook page", asset_type="social",
                url="https://www.facebook.com/medilinkhealthcare", status="verified", provenance_domain="facebook.com",
                last_checked_at=NOW - timedelta(days=10), created_at=CLIENT_CREATED + timedelta(days=30),
            ),
            AuthorityAsset(
                client_id=client.id, asset_key="instagram", name="Instagram profile", asset_type="social",
                url="https://www.instagram.com/medilinkhealthcare", status="in_progress", provenance_domain="instagram.com",
                notes="Account created; content calendar pending.", created_at=CLIENT_CREATED + timedelta(days=100),
            ),
            AuthorityAsset(
                client_id=client.id, asset_key="foursquare", name="Foursquare / Apple Maps listing", asset_type="directory",
                status="missing", notes="Not yet claimed — queued for month 6.", created_at=CLIENT_CREATED + timedelta(days=100),
            ),
        ])
        activity.append((NOW - timedelta(days=5), "authority_asset_verified", "Google Business Profile re-verified: 4.6 stars across 214 reviews."))

        # -------------------------------------------------------------
        # Misinformation compliance findings
        # -------------------------------------------------------------
        db.flush()
        finding_resolved = MisinformationFinding(
            client_id=client.id, scan_query_result_id=misinfo_result_wrong_service.id,
            quote="Medilink Healthcare also provides in-house dialysis and 24-hour emergency trauma surgery",
            category="wrong_service", rule_key=None, severity="medium",
            explanation="AI response claims Medilink offers in-house dialysis and emergency trauma surgery — services outside its GP, screening, and occupational-health scope. Could set false patient expectations in an emergency.",
            status="verified_fixed",
            detected_at=SCAN_DATES[1], reviewed_at=SCAN_DATES[1] + timedelta(days=2), resolved_at=SCAN_DATES[2],
            admin_note="Confirmed in review; service pages updated to explicitly scope services. Re-scan in month 3 no longer surfaces this claim.",
        )
        tf_hours, version_hours = truth_fact_by_key[("business_hours", "general")]
        finding_open = MisinformationFinding(
            client_id=client.id, scan_query_result_id=misinfo_result_outdated.id,
            truth_fact_id=tf_hours.id, truth_fact_version_id=version_hours.id,
            quote="Medilink Healthcare's Bangsar clinic is open Monday to Friday, 9am-5pm only, with no weekend hours",
            category="outdated_info", rule_key=None, severity="low",
            explanation="AI states weekday-only hours; Medilink's verified Truth Vault hours include Saturday and Sunday coverage at the Bangsar clinic — could cause a missed visit.",
            status="suggested",
            detected_at=SCAN_DATES[-1],
        )
        db.add_all([finding_resolved, finding_open])
        activity.append((SCAN_DATES[1], "misinformation_flagged", "Compliance finding flagged: incorrect service claim (dialysis/trauma surgery)."))
        activity.append((SCAN_DATES[2], "misinformation_resolved", "Compliance finding resolved: service page corrected; claim no longer appears."))
        activity.append((SCAN_DATES[-1], "misinformation_flagged", "Compliance finding flagged: outdated Bangsar clinic hours (awaiting review)."))

        # -------------------------------------------------------------
        # Delivery workspace — work log + outcome actions
        # -------------------------------------------------------------
        def _work_log(category, description, entry_date, source="manual"):
            wl = WorkLogEntry(
                client_id=client.id, category=category, description=description,
                source=source, status="published", entry_date=entry_date,
                created_at=datetime.combine(entry_date, datetime.min.time()),
                published_at=datetime.combine(entry_date, datetime.min.time()) + timedelta(hours=2),
            )
            db.add(wl)
            db.flush()
            return wl

        wl1 = _work_log("content", "Published a health-screening explainer hub covering all three package tiers.", (SCAN_DATES[1] + timedelta(days=3)).date())
        wl2 = _work_log("technical", "Shipped llms.txt, schema.json, and an AI-crawler-open robots.txt via the AI Readiness Toolkit.", (TOOLKIT_VERIFIED).date())
        wl3 = _work_log("content", "Launched a corporate & occupational health hub for HR decision-makers.", (SCAN_DATES[2] + timedelta(days=4)).date())
        wl4 = _work_log("authority", "Verified Google Business Profile and responded to outstanding reviews.", (SCAN_DATES[2] + timedelta(days=8)).date())
        wl5 = _work_log("correction", "Corrected an AI response claiming Medilink offers dialysis and trauma surgery.", (SCAN_DATES[2]).date())
        wl6 = _work_log("content", "Published a condition-screening guide covering diabetes and hypertension checks.", (SCAN_DATES[3] + timedelta(days=6)).date())

        db.add_all([
            OutcomeAction(
                client_id=client.id, scan_id=None, work_log_entry_id=wl1.id,
                source_kind="content_roadmap", source_ref="roadmap:health-screening-hub",
                title="Publish health screening explainer hub", action_type="content",
                rationale="AI assistants surface Sentosa Healthcare and Care Clinic Group for health-screening questions; a dedicated hub gives Medilink a citable answer.",
                priority="high", priority_score=9, confidence="high", status="verified",
                owner="Faris", client_safe_summary="Published a full explainer hub for health screening packages.",
                published_at=wl1.published_at, verified_at=wl1.published_at + timedelta(days=10),
                created_at=wl1.created_at,
            ),
            OutcomeAction(
                client_id=client.id, scan_id=None, work_log_entry_id=wl2.id,
                source_kind="site_audit", source_ref="toolkit:v1",
                title="Ship llms.txt, schema.json, and AI-crawler-open robots.txt", action_type="technical",
                rationale="Technical Foundations and Structured Data were both at 0 pre-toolkit.",
                priority="high", priority_score=10, confidence="high", status="verified",
                owner="Faris", client_safe_summary="Shipped the AI Readiness Toolkit — robots.txt, schema.json, and llms.txt are now live and verified.",
                published_at=wl2.published_at, verified_at=wl2.published_at,
                created_at=wl2.created_at,
            ),
            OutcomeAction(
                client_id=client.id, scan_id=None, work_log_entry_id=wl3.id,
                source_kind="content_roadmap", source_ref="roadmap:corporate-health-hub",
                title="Launch corporate & occupational health hub", action_type="content",
                rationale="Corporate and occupational-health queries currently favor Medipulse Healthcare.",
                priority="high", priority_score=8, confidence="medium", status="published",
                owner="Faris", client_safe_summary="Published a corporate health hub for HR teams evaluating panel clinic options.",
                published_at=wl3.published_at, created_at=wl3.created_at,
            ),
            OutcomeAction(
                client_id=client.id, scan_id=None, work_log_entry_id=wl4.id,
                source_kind="authority_asset", source_ref="authority:gbp",
                title="Verify Google Business Profile & respond to reviews", action_type="authority",
                rationale="Unverified GBP listing risked NAP mismatches and unanswered reviews.",
                priority="medium", priority_score=6, confidence="high", status="verified",
                owner="Faris", client_safe_summary="Verified the Google Business Profile listing and cleared the review response backlog.",
                published_at=wl4.published_at, verified_at=wl4.published_at + timedelta(days=5),
                created_at=wl4.created_at,
            ),
            OutcomeAction(
                client_id=client.id, scan_id=None, work_log_entry_id=wl5.id,
                source_kind="misinformation_finding", source_ref=f"misinformation:{finding_resolved.id}",
                title="Correct outdated occupational-health service claim", action_type="fact_correction",
                rationale="Confirmed compliance finding: AI response attributed dialysis and trauma surgery services Medilink does not offer.",
                priority="high", priority_score=9, confidence="high", status="verified",
                owner="Faris", client_safe_summary="Corrected a factual error about services offered; confirmed fixed on re-scan.",
                published_at=wl5.published_at, verified_at=wl5.published_at + timedelta(days=3),
                created_at=wl5.created_at,
            ),
            OutcomeAction(
                client_id=client.id, scan_id=None, work_log_entry_id=wl6.id,
                source_kind="content_roadmap", source_ref="roadmap:condition-guides",
                title="Publish condition-screening guide (diabetes & hypertension)", action_type="content",
                rationale="Condition/symptom explainers are how AI assistants surface clinics for health questions.",
                priority="medium", priority_score=6, confidence="medium", status="published",
                owner="Faris", client_safe_summary="Published a plain-language guide to diabetes and hypertension screening.",
                published_at=wl6.published_at, created_at=wl6.created_at,
            ),
            OutcomeAction(
                client_id=client.id, scan_id=None, work_log_entry_id=None,
                source_kind="page_audit", source_ref=None,
                title="Rewrite health-screening landing page for citability", action_type="content",
                rationale="Page citability audit scored the health-screening page 65/100 pre-rewrite.",
                priority="medium", priority_score=6, confidence="medium", status="in_progress",
                owner="Faris", due_date=(NOW + timedelta(days=10)).date(),
                created_at=NOW - timedelta(days=6),
            ),
            OutcomeAction(
                client_id=client.id, scan_id=None, work_log_entry_id=None,
                source_kind="competitor_response", source_ref=None,
                title="Draft comparison page vs Sentosa Healthcare", action_type="competitor_response",
                rationale="Comparison queries currently favor Sentosa Healthcare's broader specialist network.",
                priority="medium", priority_score=5, confidence="medium", status="waiting_client",
                owner="Faris", client_safe_summary="Drafted a Medilink vs Sentosa Healthcare comparison page — awaiting your go-ahead to publish.",
                created_at=NOW - timedelta(days=4),
            ),
            OutcomeAction(
                client_id=client.id, scan_id=None, work_log_entry_id=None,
                source_kind="manual", source_ref=None,
                title="List second clinic (Cheras) on Google Business Profile", action_type="local_presence",
                rationale="The Cheras clinic opened in month 2 and has no directory presence yet.",
                priority="low", priority_score=4, confidence="medium", status="recommended",
                owner="Faris", created_at=NOW - timedelta(days=3),
            ),
            OutcomeAction(
                client_id=client.id, scan_id=None, work_log_entry_id=None,
                source_kind="manual", source_ref=None,
                title="Connect GA4 property for automated AI-referral tracking", action_type="measurement",
                rationale="AI traffic is currently tracked manually month to month.",
                priority="low", priority_score=2, confidence="low", status="dismissed",
                owner="Faris", client_comment="Client prefers manual traffic entry for now.",
                client_decision="declined", client_decided_at=NOW - timedelta(days=2),
                created_at=NOW - timedelta(days=8),
            ),
        ])
        for wl, note in [
            (wl1, "Work log published: health-screening explainer hub."),
            (wl2, "Work log published: AI Readiness Toolkit shipped."),
            (wl3, "Work log published: corporate & occupational health hub."),
            (wl4, "Work log published: Google Business Profile verified."),
            (wl5, "Work log published: service-claim correction verified fixed."),
            (wl6, "Work log published: diabetes/hypertension screening guide."),
        ]:
            activity.append((wl.published_at, "work_log_published", note))

        # -------------------------------------------------------------
        # Page-citability audits — before/after on 2 URLs
        # -------------------------------------------------------------
        for url in [
            "https://medilinkhealthcare.my/services/health-screening",
            "https://medilinkhealthcare.my/",
        ]:
            score_before, checks_before, suggestions_before = build_page_audit(before=True)
            db.add(PageAudit(client_id=client.id, url=url, score=score_before, checks=checks_before, suggestions=suggestions_before, suggestions_failed=False, created_at=SCAN_DATES[1] + timedelta(days=1)))
            score_after, checks_after, suggestions_after = build_page_audit(before=False)
            db.add(PageAudit(client_id=client.id, url=url, score=score_after, checks=checks_after, suggestions=suggestions_after, suggestions_failed=False, created_at=SCAN_DATES[-1] - timedelta(days=1)))

        # -------------------------------------------------------------
        # Conversion events (business proof)
        # -------------------------------------------------------------
        counts_per_scan_window = [2, 3, 4, 5, 6]
        event_id_counter = 1
        for i, count in enumerate(counts_per_scan_window):
            window_start = SCAN_DATES[i] - timedelta(days=25)
            for j in range(count):
                occurred = window_start + timedelta(days=int(20 * j / max(count, 1)), hours=9)
                event_type = ["lead", "booking", "call"][j % 3]
                if event_type == "booking":
                    value_minor = 48000
                    evidence_level = "assisted"
                else:
                    value_minor = 0
                    evidence_level = "assisted"
                if j == 0 and i in (2, 4):
                    # A couple of directly-attributed CRM bookings.
                    evidence_level = "observed"
                    source = "crm"
                    external_event_id = f"crm-medilink-{event_id_counter}"
                else:
                    source = "manual"
                    external_event_id = None
                db.add(ConversionEvent(
                    client_id=client.id, location_id=locations[0].id,
                    event_type=event_type, source=source, external_event_id=external_event_id,
                    evidence_level=evidence_level, occurred_at=occurred,
                    value_minor=value_minor, currency="MYR",
                    notes="AI-referral visitor converted after landing on the health-screening explainer hub." if event_type == "booking" else None,
                ))
                event_id_counter += 1
        # Two modeled/estimated pipeline entries.
        for i in (1, 3):
            db.add(ConversionEvent(
                client_id=client.id, location_id=None,
                event_type="lead", source="estimate", external_event_id=None,
                evidence_level="estimated", occurred_at=SCAN_DATES[i],
                value_minor=0, currency="MYR",
                calculation_method="visitor_to_lead_pipeline_v1", calculation_version="v1",
                notes="Modeled AI-referral pipeline contribution for this period.",
            ))

        # -------------------------------------------------------------
        # Tracked query portfolio
        # -------------------------------------------------------------
        tracked_specs = [
            ("Best health screening in Kuala Lumpur", "scan_derived", "recommendation", "consideration", "standard", 8.0, 7.5),
            ("Medilink Healthcare reviews", "scan_derived", "brand", "decision", "standard", 6.0, 6.0),
            ("Corporate health screening Klang Valley", "manual", "recommendation", "consideration", "standard", 9.0, 8.5),
            ("Medilink Healthcare vs Sentosa Healthcare", "scan_derived", "comparison", "decision", "standard", 7.0, 6.5),
            ("Best clinic near me in Kuala Lumpur", "scan_derived", "local", "awareness", "standard", 5.5, 5.0),
            ("How much does a health screening cost in Kuala Lumpur", "gsc_import", "recommendation", "consideration", "elevated", 6.5, 6.0),
            ("Occupational health services Malaysia", "manual", "recommendation", "consideration", "standard", 5.0, 4.5),
            ("Medilink Healthcare Bangsar opening hours", "gsc_import", "local", "decision", "standard", 4.0, 3.5),
        ]
        for text, source, intent, buyer_stage, risk_level, demand_weight, priority_score in tracked_specs:
            db.add(TrackedQuery(
                client_id=client.id, location_id=None, text=text, normalized_text=text.lower().strip(),
                source=source, intent=intent, buyer_stage=buyer_stage, risk_level=risk_level,
                demand_weight=demand_weight, priority_score=priority_score, is_active=True,
                created_at=NOW - timedelta(days=40),
            ))

        # -------------------------------------------------------------
        # Search Console signals
        # -------------------------------------------------------------
        gsc_queries = [
            ("medilink healthcare", "https://medilinkhealthcare.my/", 6.0, 40, 18.0),
            ("health screening klang valley", "https://medilinkhealthcare.my/services/health-screening", 14.0, 15, 9.0),
            ("corporate health screening malaysia", "https://medilinkhealthcare.my/services/corporate-health", 22.0, 10, 6.0),
        ]
        for query, page, start_pos, start_impr, end_impr in gsc_queries:
            for d in range(45, 0, -1):
                signal_date = (NOW - timedelta(days=d)).date()
                progress = (45 - d) / 45.0
                position = max(1.5, start_pos - (start_pos - 3.0) * progress)
                impressions = int(start_impr + (end_impr - start_impr) * progress)
                clicks = max(0, int(impressions * (0.03 + 0.10 * progress)))
                ctr = round(clicks / impressions, 4) if impressions else 0.0
                db.add(SearchQuerySignal(
                    client_id=client.id, location_id=None, property_uri=client.website,
                    signal_date=signal_date, query=query, page=page,
                    country="MYS", device="DESKTOP" if d % 2 == 0 else "MOBILE",
                    clicks=clicks, impressions=impressions, ctr=ctr, position=round(position, 1),
                ))

        # -------------------------------------------------------------
        # Dimension assessments (assisted Brand Authority / Content Quality)
        # -------------------------------------------------------------
        db.add(DimensionAssessment(
            client_id=client.id, dimension="brand_authority",
            suggested_score=56, final_score=BA_TRAJECTORY[-1],
            evidence_bullets=[
                "Google Business Profile verified with 4.6 stars across 214 reviews (up from 4.1/62 at onboarding).",
                "Featured in 5 third-party sources this scan (healthhub.my, klangvalleyliving.com, and others), up from 1 at onboarding.",
                "Corporate panel relationships with several Klang Valley employers, but still fewer authoritative health-media backlinks than Sentosa Healthcare.",
            ],
            raw_narrative="Admin-reviewed narrative: steady authority growth driven by GBP verification and directory coverage; press/media mentions remain the largest gap versus Sentosa Healthcare.",
            status="adjusted", generated_at=NOW - timedelta(days=3), reviewed_at=NOW - timedelta(days=2),
        ))
        db.add(DimensionAssessment(
            client_id=client.id, dimension="content_quality",
            suggested_score=52, final_score=CQ_TRAJECTORY[-1],
            evidence_bullets=[
                "Health screening explainer hub, corporate health hub, and a condition-screening guide published since onboarding.",
                "Word count grew from ~3,200 to ~6,800 words with schema.json now live across key pages.",
                "Patient guides (insurance/panel, walk-in vs appointment) and comparisons with other Klang Valley clinics are still missing.",
            ],
            raw_narrative="Admin-reviewed narrative: content maturity has roughly doubled since onboarding; patient-guide and comparison content are the clearest next gaps.",
            status="adjusted", generated_at=NOW - timedelta(days=3), reviewed_at=NOW - timedelta(days=2),
        ))

        # -------------------------------------------------------------
        # Activity log
        # -------------------------------------------------------------
        activity.sort(key=lambda t: t[0])
        for ts, event_type, note in activity:
            db.add(ActivityLog(client_id=client.id, event_type=event_type, note=note, created_at=ts))

        db.commit()
        print(f"Seeded Medilink Healthcare (client_id={client.id}) with {N_SCANS} scans; final overall_score={last_geo_score.overall_score:.1f}")

        print("Generating PDF report...")
        try:
            report = generate_report_pdf(client.id, db)
        except Exception as exc:  # R2/WeasyPrint may be unconfigured locally
            print(f"  -> report generation failed ({exc}); all other data is seeded")
        else:
            if report:
                print(f"  -> {report.r2_url}")
            else:
                print("  -> report generation skipped (no scan data in range)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
