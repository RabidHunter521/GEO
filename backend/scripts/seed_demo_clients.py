# backend/scripts/seed_demo_clients.py
"""Seed 4 fully-fabricated demo clients for presentation purposes.

No real scans or external API calls are made — query results, scores, and
all supporting data (toolkit files, content gaps, roadmap, actions, traffic,
activity log) are generated/hand-written so every dashboard section looks
populated as if a real scan ran.

Run from backend/ with the project venv:
    python -m scripts.seed_demo_clients
"""
import secrets
from datetime import datetime, timedelta

from app.core.database import SessionLocal
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan import Scan
from app.models.toolkit_files import ToolkitFiles
from app.models.content_analysis import ContentAnalysis
from app.models.content_roadmap import ContentRoadmap
from app.models.content_brief import ContentBrief
from app.models.action_recommendation import ActionRecommendation
from app.models.activity_log import ActivityLog
from app.models.ai_traffic_snapshot import AiTrafficSnapshot
from app.services.toolkit_service import generate_robots_txt
from app.services.report_service import generate_report_pdf

from scripts.seed_helpers import (
    build_client_scan_results,
    build_llms_txt,
    build_schema_json,
    build_roadmap_json,
    compute_action_impact,
    compute_action_priority,
    derate_profile,
    make_content_brief_fields,
    save_geo_score,
)

import random


NOW = datetime.utcnow()
NEW_SCAN_COMPLETED = NOW - timedelta(days=2)
OLD_SCAN_COMPLETED = NOW - timedelta(days=35)
TOOLKIT_GENERATED = NOW - timedelta(days=34)
TOOLKIT_VERIFIED = NOW - timedelta(days=33)
CLIENT_CREATED = NOW - timedelta(days=36)
SHARE_LINK_CREATED = NOW - timedelta(days=2)


# ---------------------------------------------------------------------------
# CLIENT 1: Glad2Glow
# ---------------------------------------------------------------------------
GLAD2GLOW = {
    "client": dict(
        name="Glad2Glow",
        website="https://glad2glow.com/",
        industry="E-commerce",
        description=(
            "Affordable, ingredient-led skincare brand built for Gen Z and millennial "
            "shoppers across Malaysia and Indonesia, sold primarily through Shopee, "
            "Lazada, TikTok Shop, and its own DTC site."
        ),
        target_audience=(
            "Gen Z and millennial shoppers in Malaysia and Indonesia seeking affordable, "
            "active-ingredient skincare"
        ),
        city="Kuala Lumpur",
        state="Wilayah Persekutuan Kuala Lumpur",
        country="Malaysia",
        brand_authority_score=52,
        brand_authority_evidence=(
            "Strong TikTok and Shopee presence with active Gen Z community engagement, "
            "but minimal press/PR coverage outside social platforms — limited backlinks "
            "from beauty media."
        ),
        content_quality_score=56,
        content_quality_evidence=(
            "Product pages are clear and benefit-led, but the blog/education hub is "
            "thin — few ingredient deep-dives, routine guides, or comparison posts "
            "that AI models can draw from."
        ),
    ),
    "competitors": [
        {"name": "Skintific", "website": None},
        {"name": "Wardah", "website": None},
        {"name": "SomeByMi", "website": None},
    ],
    "scan_profile": {
        "industry_phrase": "affordable, ingredient-led skincare brand",
        "location": "Kuala Lumpur, Malaysia",
        "city": "Kuala Lumpur",
        "client_visibility": {"chatgpt": 0.625, "perplexity": 0.5, "gemini": 0.375, "claude": 0.375},
        "client_trait": (
            "affordable, ingredient-led products such as niacinamide serums, centella "
            "moisturizers, and barrier-repair creams aimed at Gen Z skincare routines"
        ),
        "client_extra": "The brand has built a loyal following through TikTok Shop livestreams and Shopee flash sales.",
        "client_comparison_trait": (
            "focuses on budget-friendly, ingredient-led formulas marketed heavily "
            "through social commerce and Gen Z creators"
        ),
        "competitor_traits": {
            "Skintific": {
                "trait": "viral, science-backed skincare with ceramide and salicylic acid formulas that frequently trend on TikTok",
                "extra": "It has become one of the most searched skincare brands in Southeast Asia.",
                "comparison_trait": "is known for viral, science-backed TikTok skincare with strong Shopee sales",
            },
            "Wardah": {
                "trait": "halal-certified cosmetics and skincare with strong brand recognition across Malaysia and Indonesia",
                "extra": "It is one of the most established beauty brands in the region.",
                "comparison_trait": "is a long-established halal-certified beauty brand with broad retail distribution",
            },
            "SomeByMi": {
                "trait": "ingredient-forward K-beauty skincare, especially its AHA-BHA-PHA line",
                "extra": "It has a loyal following among skincare enthusiasts who track active ingredients closely.",
                "comparison_trait": "is an ingredient-forward K-beauty brand best known for its AHA-BHA-PHA line",
            },
        },
        "competitor_visibility": {
            "Skintific": {"chatgpt": 0.75, "perplexity": 0.75, "gemini": 0.5, "claude": 0.5},
            "Wardah": {"chatgpt": 0.75, "perplexity": 0.5, "gemini": 0.75, "claude": 0.5},
            "SomeByMi": {"chatgpt": 0.5, "perplexity": 0.5, "gemini": 0.25, "claude": 0.5},
        },
        "filler_names": ["Cosrx", "The Ordinary"],
    },
    "toolkit": {
        "tagline": (
            "Affordable, ingredient-led skincare for Gen Z — niacinamide, centella, and "
            "barrier-repair formulas made for everyday routines in Malaysia and Indonesia."
        ),
        "about": (
            "Glad2Glow is a Malaysia-based skincare brand offering budget-friendly, "
            "ingredient-led products for Gen Z and millennial skin concerns. Products "
            "are formulated around proven actives like niacinamide, centella asiatica, "
            "and ceramides, and sold through Shopee, Lazada, TikTok Shop, and the brand's "
            "own site."
        ),
        "sections": [
            (
                "Products",
                "- Niacinamide Brightening Serum\n- Centella Calming Moisturizer\n"
                "- Ceramide Barrier Repair Cream\n- Gentle Foaming Cleanser",
            ),
            (
                "Where to Buy",
                "Glad2Glow products are available on Shopee, Lazada, TikTok Shop, and glad2glow.com.",
            ),
        ],
        "business_type": "OnlineStore",
        "faqs": [
            ("What ingredients does Glad2Glow use?", "Glad2Glow formulates products around proven actives such as niacinamide, centella asiatica, and ceramides, targeting common Gen Z skin concerns like oiliness, sensitivity, and barrier damage."),
            ("Where can I buy Glad2Glow products?", "Glad2Glow products are sold on Shopee, Lazada, TikTok Shop, and via glad2glow.com, with delivery across Malaysia and Indonesia."),
            ("Is Glad2Glow suitable for sensitive skin?", "Many Glad2Glow products are formulated with calming ingredients like centella asiatica and are designed to be gentle for everyday use, though individuals with specific sensitivities should patch-test new products."),
            ("Does Glad2Glow ship to Indonesia?", "Yes, Glad2Glow ships to customers in both Malaysia and Indonesia through its marketplace stores."),
        ],
    },
    "content_analysis": {
        "topics_json": [
            {"topic": "Ingredient education (niacinamide, centella, ceramides)", "status": "weak"},
            {"topic": "Skincare routines for oily/acne-prone skin", "status": "strong"},
            {"topic": "Halal certification & ingredient sourcing", "status": "missing"},
            {"topic": "Comparisons vs K-beauty and TikTok skincare brands", "status": "missing"},
            {"topic": "Customer reviews & before/after results", "status": "strong"},
            {"topic": "Shipping, returns & marketplace store info", "status": "strong"},
        ],
        "entities_json": [
            {"entity": "Niacinamide", "covered": True},
            {"entity": "Centella Asiatica", "covered": True},
            {"entity": "Ceramide", "covered": False},
            {"entity": "Halal Certification", "covered": False},
            {"entity": "Shopee Mall", "covered": True},
            {"entity": "Dermatologically Tested", "covered": False},
        ],
        "suggested_content_json": [
            {
                "topic": "Ingredient education",
                "title": "Niacinamide vs Centella: Which Glad2Glow Serum Should You Use First?",
                "rationale": "AI assistants frequently answer ingredient-comparison questions — a dedicated guide gives them a citable source featuring Glad2Glow products.",
            },
            {
                "topic": "Halal certification",
                "title": "Is Glad2Glow Halal-Certified? A Full Ingredient & Sourcing Breakdown",
                "rationale": "Competitors like Wardah lead on halal trust signals — publishing certification details closes this gap for AI answers about halal skincare.",
            },
            {
                "topic": "Brand comparisons",
                "title": "Glad2Glow vs Skintific: Which Affordable Skincare Brand Fits Your Routine?",
                "rationale": "Comparison queries are common in AI search — an honest comparison page increases the chance Glad2Glow is surfaced alongside Skintific.",
            },
        ],
        "content_metrics_json": {"word_count": 7600, "h1_count": 18, "faq_count": 5, "blog_count": 2, "schema_present": False},
        "content_quality_recommendation": (
            "Build out an ingredients/education hub with dedicated pages for each hero "
            "ingredient (niacinamide, centella, ceramide) and add a halal/sourcing FAQ — "
            "both are missing entity signals that AI assistants look for when answering "
            "skincare questions."
        ),
        "entity_coverage_score": 58.0,
        "pages_crawled": 24,
    },
    "roadmap_themes": [
        {
            "month": 1, "theme": "Ingredient Education Hub", "priority": "high",
            "content_type": "Blog series",
            "suggested_title": "The Glad2Glow Ingredient Guide: Niacinamide, Centella & Ceramide Explained",
            "rationale": (
                "Closes the ingredient-education gap AI assistants rely on when answering "
                "skincare questions, and gives AI models specific Glad2Glow pages to cite "
                "for ingredient-led queries."
            ),
        },
        {
            "month": 2, "theme": "Halal & Trust Signals", "priority": "medium",
            "content_type": "Dedicated page + FAQ",
            "suggested_title": "Glad2Glow Halal Certification & Ingredient Sourcing",
            "rationale": (
                "Wardah currently wins halal-related trust queries — publishing "
                "certification details gives AI assistants a clear answer that includes "
                "Glad2Glow."
            ),
        },
        {
            "month": 3, "theme": "Comparison & Best-Of Content", "priority": "medium",
            "content_type": "Comparison landing pages",
            "suggested_title": "Glad2Glow vs Skintific vs SomeByMi: Which Affordable Skincare Brand Should You Choose?",
            "rationale": (
                "Recommendation and local 'best skincare brand' queries currently favor "
                "Skintific and SomeByMi — comparison pages increase the odds Glad2Glow "
                "appears in these AI-generated shortlists."
            ),
        },
    ],
    "actions": [
        {"dimension": "ai_citability", "closable_fraction": 0.35, "action_text": "Publish ingredient-education pages for niacinamide, centella, and ceramide so AI assistants have a Glad2Glow source to cite for skincare-ingredient questions."},
        {"dimension": "content_quality", "closable_fraction": 0.30, "action_text": "Add a dedicated halal certification and ingredient-sourcing FAQ page to match the trust signals Wardah already provides."},
        {"dimension": "brand_authority", "closable_fraction": 0.25, "action_text": "Pursue placements in Malaysian/Indonesian beauty media (e.g. round-up articles on affordable skincare brands) to build backlinks and third-party mentions beyond TikTok and Shopee."},
        {"dimension": "ai_citability", "closable_fraction": 0.30, "action_text": "Create direct comparison pages (Glad2Glow vs Skintific, Glad2Glow vs SomeByMi) to capture AI-generated 'best affordable skincare' shortlists."},
    ],
    "ai_traffic": {"current": 1450, "prev": 1180},
}


# ---------------------------------------------------------------------------
# CLIENT 2: Avisena Healthcare
# ---------------------------------------------------------------------------
AVISENA = {
    "client": dict(
        name="Avisena Healthcare",
        website="https://avisena.com.my/",
        industry="Healthcare",
        description=(
            "Private specialist hospital group operating in Shah Alam and the greater "
            "Klang Valley, offering multidisciplinary specialist care, diagnostics, and "
            "24-hour emergency services."
        ),
        target_audience=(
            "Patients and families in Shah Alam and the Klang Valley seeking private "
            "specialist hospital care"
        ),
        city="Shah Alam",
        state="Selangor",
        country="Malaysia",
        brand_authority_score=64,
        brand_authority_evidence=(
            "Established hospital group with local press coverage and doctor-directory "
            "listings, but fewer authoritative health-content backlinks than larger "
            "groups like Sunway Healthcare."
        ),
        content_quality_score=60,
        content_quality_evidence=(
            "Department and doctor pages are informative, but condition/treatment "
            "explainer content is limited compared to SJMC and Sunway Medical Centre's "
            "health information hubs."
        ),
    ),
    "competitors": [
        {"name": "Subang Jaya Medical Centre (SJMC)", "website": None},
        {"name": "Sunway Medical Centre", "website": None},
        {"name": "Ara Damansara Medical Centre (ADMC)", "website": None},
    ],
    "scan_profile": {
        "industry_phrase": "private specialist hospital",
        "location": "Shah Alam, Selangor, Malaysia",
        "city": "Shah Alam",
        "client_visibility": {"chatgpt": 0.5, "perplexity": 0.375, "gemini": 0.5, "claude": 0.375},
        "client_trait": (
            "multidisciplinary specialist care, diagnostic imaging, and 24-hour "
            "emergency services for the Shah Alam and Klang Valley community"
        ),
        "client_extra": "It is recognized locally as a key private healthcare provider in Shah Alam.",
        "client_comparison_trait": "offers multidisciplinary specialist care and emergency services focused on the Shah Alam area",
        "competitor_traits": {
            "Subang Jaya Medical Centre (SJMC)": {
                "trait": "a large multidisciplinary private hospital with a wide range of specialist centres and a long-standing reputation in Subang Jaya",
                "extra": "It is one of the most recognized private hospitals in the Klang Valley.",
                "comparison_trait": "is a large, long-established multidisciplinary hospital with a broad specialist network in Subang Jaya",
            },
            "Sunway Medical Centre": {
                "trait": "a major private hospital known for advanced cancer care, cardiology, and a comprehensive health information hub",
                "extra": "It is part of the wider Sunway Healthcare network and is highly ranked among private hospitals in Malaysia.",
                "comparison_trait": "is a major private hospital known for advanced specialist centres and an extensive online health content library",
            },
            "Ara Damansara Medical Centre (ADMC)": {
                "trait": "a private hospital offering specialist and emergency services for the Ara Damansara and Petaling Jaya area",
                "extra": "It is part of the KPJ Healthcare network.",
                "comparison_trait": "is a KPJ-network private hospital serving the Ara Damansara and Petaling Jaya area",
            },
        },
        "competitor_visibility": {
            "Subang Jaya Medical Centre (SJMC)": {"chatgpt": 0.75, "perplexity": 0.75, "gemini": 0.75, "claude": 0.5},
            "Sunway Medical Centre": {"chatgpt": 1.0, "perplexity": 0.75, "gemini": 0.75, "claude": 0.75},
            "Ara Damansara Medical Centre (ADMC)": {"chatgpt": 0.5, "perplexity": 0.5, "gemini": 0.5, "claude": 0.25},
        },
        "filler_names": ["Gleneagles Kuala Lumpur", "Pantai Hospital"],
    },
    "toolkit": {
        "tagline": (
            "Private specialist hospital care in Shah Alam — multidisciplinary "
            "specialists, diagnostics, and 24-hour emergency services."
        ),
        "about": (
            "Avisena Healthcare is a private specialist hospital group based in Shah "
            "Alam, Selangor, serving patients across the Klang Valley with "
            "multidisciplinary specialist clinics, diagnostic imaging, day surgery, and "
            "round-the-clock emergency care."
        ),
        "sections": [
            (
                "Specialist Centres",
                "- Cardiology\n- Orthopaedics\n- Paediatrics\n- Women's Health\n- General Surgery",
            ),
            (
                "Emergency & Diagnostics",
                "Avisena Healthcare operates a 24-hour Emergency Department alongside "
                "diagnostic imaging and laboratory services.",
            ),
        ],
        "business_type": "Hospital",
        "faqs": [
            ("What specialist services does Avisena Healthcare offer?", "Avisena Healthcare offers multidisciplinary specialist care including cardiology, orthopaedics, paediatrics, women's health, and general surgery, alongside diagnostic imaging and day surgery services."),
            ("Where is Avisena Healthcare located?", "Avisena Healthcare is located in Shah Alam, Selangor, serving patients across the greater Klang Valley."),
            ("Does Avisena Healthcare have 24-hour emergency care?", "Yes, Avisena Healthcare operates a 24-hour Emergency Department staffed for urgent and emergency cases."),
            ("How do I book an appointment with a specialist at Avisena Healthcare?", "Appointments with Avisena Healthcare specialists can be booked by contacting the hospital directly or through the appointment request form on its website."),
        ],
    },
    "content_analysis": {
        "topics_json": [
            {"topic": "Condition & treatment explainers (e.g. cardiology, orthopaedics)", "status": "weak"},
            {"topic": "Doctor directory & specialist profiles", "status": "strong"},
            {"topic": "Emergency & 24-hour services information", "status": "strong"},
            {"topic": "Health screening & packages", "status": "weak"},
            {"topic": "Patient guides (insurance, admission process)", "status": "missing"},
            {"topic": "Comparisons with other Klang Valley hospitals", "status": "missing"},
        ],
        "entities_json": [
            {"entity": "24-Hour Emergency Department", "covered": True},
            {"entity": "Specialist Doctor Directory", "covered": True},
            {"entity": "Health Screening Packages", "covered": False},
            {"entity": "Insurance Panel / Cashless Admission", "covered": False},
            {"entity": "Cardiology Centre", "covered": True},
            {"entity": "MRI / CT Diagnostic Imaging", "covered": False},
        ],
        "suggested_content_json": [
            {
                "topic": "Condition explainers",
                "title": "Understanding Heart Health: When to See a Cardiologist at Avisena Healthcare",
                "rationale": "Condition-explainer content is how AI assistants surface hospitals for symptom and treatment questions — Sunway and SJMC dominate this space.",
            },
            {
                "topic": "Patient guides",
                "title": "A Guide to Insurance Panels and Cashless Admission at Avisena Healthcare",
                "rationale": "Practical admission/insurance questions are commonly asked of AI assistants; publishing clear answers gives Avisena a citable page.",
            },
            {
                "topic": "Health screening",
                "title": "Avisena Healthcare Health Screening Packages: What's Included and How to Choose",
                "rationale": "Health-screening queries are a recommendation-category gap where competitors currently appear instead of Avisena.",
            },
        ],
        "content_metrics_json": {"word_count": 9200, "h1_count": 26, "faq_count": 4, "blog_count": 1, "schema_present": False},
        "content_quality_recommendation": (
            "Build out condition/treatment explainer pages for each specialist centre "
            "and publish patient-guide content (insurance, admission, health screening) "
            "— these are the query types where Sunway Medical Centre and SJMC currently "
            "appear instead of Avisena in AI answers."
        ),
        "entity_coverage_score": 54.0,
        "pages_crawled": 31,
    },
    "roadmap_themes": [
        {
            "month": 1, "theme": "Condition & Treatment Explainer Hub", "priority": "high",
            "content_type": "Specialist explainer pages",
            "suggested_title": "Avisena Healthcare Specialist Guides: Cardiology, Orthopaedics & Women's Health Explained",
            "rationale": (
                "AI assistants currently surface Sunway Medical Centre and SJMC for "
                "symptom/treatment questions — dedicated explainer pages per specialist "
                "centre give Avisena a citable answer for these queries."
            ),
        },
        {
            "month": 2, "theme": "Health Screening & Packages", "priority": "medium",
            "content_type": "Service landing pages",
            "suggested_title": "Avisena Healthcare Health Screening Packages for the Klang Valley",
            "rationale": (
                "Recommendation-style 'best hospital for health screening' queries "
                "currently favor larger competitors — a clear packages page helps "
                "Avisena appear in these shortlists."
            ),
        },
        {
            "month": 3, "theme": "Patient Guides & Local Trust Content", "priority": "medium",
            "content_type": "Patient guide articles",
            "suggested_title": "Choosing a Private Hospital in Shah Alam: A Patient's Guide to Avisena Healthcare",
            "rationale": (
                "Local 'best hospital near me' queries in Shah Alam are where Avisena "
                "should have a natural advantage — patient-guide content reinforces this "
                "local relevance for AI assistants."
            ),
        },
    ],
    "actions": [
        {"dimension": "ai_citability", "closable_fraction": 0.35, "action_text": "Publish condition/treatment explainer pages for each specialist centre (cardiology, orthopaedics, women's health) so AI assistants have an Avisena source for symptom and treatment questions."},
        {"dimension": "content_quality", "closable_fraction": 0.30, "action_text": "Add a health screening packages page and a patient guide covering insurance panels and admission process — both are missing entity signals competitors already cover."},
        {"dimension": "brand_authority", "closable_fraction": 0.25, "action_text": "Pursue local press and health-directory coverage in Shah Alam/Klang Valley publications to build third-party mentions and backlinks beyond the hospital's own site."},
        {"dimension": "ai_citability", "closable_fraction": 0.30, "action_text": "Publish a 'best private hospital in Shah Alam' style local guide to strengthen Avisena's presence in local recommendation queries where SJMC and ADMC currently appear."},
    ],
    "ai_traffic": {"current": 2100, "prev": 1850},
}


# ---------------------------------------------------------------------------
# CLIENT 3: Newnormz
# ---------------------------------------------------------------------------
NEWNORMZ = {
    "client": dict(
        name="Newnormz",
        website="https://www.newnormz.com.my/",
        industry="Other",
        description=(
            "Digital marketing agency based in Malaysia offering SEO, content marketing, "
            "social media management, SEM/paid ads, and web design & development "
            "services for SMEs and growing brands."
        ),
        target_audience=(
            "Malaysian SMEs and growth-stage brands looking for an integrated digital "
            "marketing partner (SEO, content, social, SEM, web)"
        ),
        city="Petaling Jaya",
        state="Selangor",
        country="Malaysia",
        brand_authority_score=48,
        brand_authority_evidence=(
            "Active on LinkedIn and has a portfolio of client case studies, but limited "
            "coverage in marketing/business press compared to larger agencies like "
            "Primal Malaysia."
        ),
        content_quality_score=50,
        content_quality_evidence=(
            "Service pages are clear, but the resources/blog section is thin — few "
            "in-depth guides on SEO, content strategy, or paid ads that would establish "
            "topical authority."
        ),
    ),
    "competitors": [
        {"name": "Primal Malaysia", "website": None},
        {"name": "One Search Pro", "website": None},
        {"name": "Locus-T", "website": None},
    ],
    "scan_profile": {
        "industry_phrase": "digital marketing agency",
        "location": "Petaling Jaya, Malaysia",
        "city": "Petaling Jaya",
        "client_visibility": {"chatgpt": 0.375, "perplexity": 0.25, "gemini": 0.375, "claude": 0.25},
        "client_trait": (
            "full-funnel digital marketing services — SEO, content marketing, social "
            "media management, SEM, and web design — for Malaysian SMEs"
        ),
        "client_extra": "It positions itself as an integrated digital partner for growing brands.",
        "client_comparison_trait": "offers integrated SEO, content, social, SEM, and web services aimed at Malaysian SMEs",
        "competitor_traits": {
            "Primal Malaysia": {
                "trait": "a well-established full-service digital marketing agency known for SEO and content marketing work with larger Malaysian brands",
                "extra": "It is frequently cited as one of the top digital agencies in Malaysia.",
                "comparison_trait": "is a well-established full-service agency known for SEO and content work with larger brands",
            },
            "One Search Pro": {
                "trait": "an SEO-focused digital marketing agency with a strong content library of SEO guides and case studies",
                "extra": "It has built strong topical authority around SEO and search marketing.",
                "comparison_trait": "is an SEO-focused agency with a strong library of search-marketing guides",
            },
            "Locus-T": {
                "trait": "a digital marketing agency offering SEO, social media, and web development services for SMEs",
                "extra": "It has a growing presence among small and medium businesses in Malaysia.",
                "comparison_trait": "is a digital agency offering SEO, social, and web services for SMEs",
            },
        },
        "competitor_visibility": {
            "Primal Malaysia": {"chatgpt": 0.75, "perplexity": 0.75, "gemini": 0.75, "claude": 0.5},
            "One Search Pro": {"chatgpt": 0.75, "perplexity": 0.5, "gemini": 0.5, "claude": 0.5},
            "Locus-T": {"chatgpt": 0.5, "perplexity": 0.25, "gemini": 0.5, "claude": 0.25},
        },
        "filler_names": ["MGAG Media", "Ivy Digital"],
    },
    "toolkit": {
        "tagline": "Integrated digital marketing for Malaysian SMEs — SEO, content, social, SEM, and web, under one roof.",
        "about": (
            "Newnormz is a Malaysia-based digital marketing agency helping SMEs and "
            "growth-stage brands grow through SEO, content marketing, social media "
            "management, paid search/social (SEM), and web design & development."
        ),
        "sections": [
            (
                "Our Services",
                "- SEO\n- Content Marketing\n- Social Media Management\n- SEM / Paid Ads\n- Web Design & Development",
            ),
            (
                "Who We Work With",
                "Newnormz works with Malaysian SMEs and growth-stage brands across "
                "industries looking for an integrated digital marketing partner.",
            ),
        ],
        "business_type": "ProfessionalService",
        "faqs": [
            ("What services does Newnormz offer?", "Newnormz offers SEO, content marketing, social media management, SEM/paid ads, and web design & development as part of an integrated digital marketing service."),
            ("Does Newnormz work with small businesses?", "Yes, Newnormz primarily serves Malaysian SMEs and growth-stage brands looking for an integrated digital marketing partner."),
            ("Where is Newnormz based?", "Newnormz is based in Petaling Jaya, Selangor, Malaysia."),
            ("How can I get a digital marketing proposal from Newnormz?", "Businesses can request a proposal by contacting Newnormz through the contact form on its website."),
        ],
    },
    "content_analysis": {
        "topics_json": [
            {"topic": "SEO guides & how-to content", "status": "weak"},
            {"topic": "Case studies & client results", "status": "strong"},
            {"topic": "Content marketing strategy guides", "status": "missing"},
            {"topic": "Paid ads (SEM) educational content", "status": "weak"},
            {"topic": "Pricing & packages transparency", "status": "missing"},
            {"topic": "Comparisons vs other Malaysian agencies", "status": "missing"},
        ],
        "entities_json": [
            {"entity": "SEO Services", "covered": True},
            {"entity": "Content Marketing", "covered": True},
            {"entity": "SEM / Paid Ads", "covered": True},
            {"entity": "Case Studies", "covered": True},
            {"entity": "Pricing Packages", "covered": False},
            {"entity": "SEO Guides / Resource Hub", "covered": False},
        ],
        "suggested_content_json": [
            {
                "topic": "SEO guides",
                "title": "The Newnormz SEO Guide for Malaysian SMEs: A Step-by-Step Framework",
                "rationale": "One Search Pro dominates 'best SEO agency in Malaysia' answers largely through its guide content — a comparable resource hub gives AI assistants a Newnormz source to cite.",
            },
            {
                "topic": "Pricing transparency",
                "title": "How Much Does Digital Marketing Cost in Malaysia? A Pricing Guide from Newnormz",
                "rationale": "Pricing questions are common in AI search for service businesses; a clear pricing guide increases the chance Newnormz is recommended.",
            },
            {
                "topic": "Comparisons",
                "title": "Newnormz vs Primal Malaysia: Choosing the Right Digital Marketing Agency for Your SME",
                "rationale": "Comparison queries currently favor larger agencies — an honest comparison page increases Newnormz's odds of being surfaced alongside them.",
            },
        ],
        "content_metrics_json": {"word_count": 5400, "h1_count": 12, "faq_count": 4, "blog_count": 2, "schema_present": False},
        "content_quality_recommendation": (
            "Build an SEO/content marketing resource hub similar to One Search Pro's, "
            "and publish a pricing guide — both are high-traffic AI query types where "
            "Newnormz currently has no citable page."
        ),
        "entity_coverage_score": 47.0,
        "pages_crawled": 18,
    },
    "roadmap_themes": [
        {
            "month": 1, "theme": "SEO & Content Marketing Resource Hub", "priority": "high",
            "content_type": "Guide series",
            "suggested_title": "The Newnormz SEO & Content Marketing Playbook for Malaysian SMEs",
            "rationale": (
                "One Search Pro and Primal Malaysia win most 'best digital marketing "
                "agency' AI answers through strong guide content — matching this builds "
                "the topical authority AI assistants look for."
            ),
        },
        {
            "month": 2, "theme": "Pricing & Service Transparency", "priority": "medium",
            "content_type": "Pricing guide page",
            "suggested_title": "Digital Marketing Pricing in Malaysia: What SMEs Should Expect to Pay",
            "rationale": (
                "Pricing-related queries are common and currently unanswered by "
                "Newnormz — a transparent pricing guide is a quick win for AI citability."
            ),
        },
        {
            "month": 3, "theme": "Agency Comparison Content", "priority": "medium",
            "content_type": "Comparison landing pages",
            "suggested_title": "Newnormz vs Primal Malaysia vs One Search Pro: Which Agency Fits Your Business?",
            "rationale": (
                "Comparison and recommendation queries currently favor larger agencies "
                "— comparison content increases the odds Newnormz appears in "
                "AI-generated agency shortlists."
            ),
        },
    ],
    "actions": [
        {"dimension": "ai_citability", "closable_fraction": 0.35, "action_text": "Publish an SEO and content marketing resource hub (guides, frameworks, checklists) to match the topical authority One Search Pro already has with AI assistants."},
        {"dimension": "content_quality", "closable_fraction": 0.30, "action_text": "Add a transparent pricing/packages guide — pricing questions are a common AI query type Newnormz currently has no page to answer."},
        {"dimension": "brand_authority", "closable_fraction": 0.25, "action_text": "Pursue guest posts and case-study features in Malaysian marketing/business publications to build third-party mentions beyond LinkedIn."},
        {"dimension": "ai_citability", "closable_fraction": 0.30, "action_text": "Publish agency-comparison pages (Newnormz vs Primal Malaysia, vs One Search Pro) to capture AI-generated 'best digital marketing agency in Malaysia' shortlists."},
    ],
    "ai_traffic": {"current": 620, "prev": 480},
}


# ---------------------------------------------------------------------------
# CLIENT 4: Ayam Gepuk Tokmat
# ---------------------------------------------------------------------------
AYAM_GEPUK_TOKMAT = {
    "client": dict(
        name="Ayam Gepuk Tokmat",
        website="https://www.ayamgepuktokmat.com/",
        industry="Food & Beverage",
        description=(
            "Malaysian fried chicken restaurant chain known for its signature 'ayam "
            "gepuk' (smashed fried chicken) served with sambal, operating multiple "
            "outlets across Malaysia."
        ),
        target_audience=(
            "Malaysian diners looking for affordable, spicy Indonesian-style fried "
            "chicken (ayam gepuk/penyet) for dine-in, takeaway, and delivery"
        ),
        city="Kuala Lumpur",
        state="Wilayah Persekutuan Kuala Lumpur",
        country="Malaysia",
        brand_authority_score=60,
        brand_authority_evidence=(
            "Well-known chain with food-blogger and review coverage across Malaysia, "
            "but less consistent online presence than Ayam Gepuk Pak Gembus across all "
            "outlet locations."
        ),
        content_quality_score=52,
        content_quality_evidence=(
            "Outlet/location listings are present, but menu detail, halal info, and "
            "franchise information pages are thin compared to competitors."
        ),
    ),
    "competitors": [
        {"name": "Ayam Gepuk Pak Gembus", "website": None},
        {"name": "Ayam Gepuk Top Global", "website": None},
        {"name": "Ayam Gepuk Artisan", "website": None},
    ],
    "scan_profile": {
        "industry_phrase": "ayam gepuk (smashed fried chicken) restaurant",
        "location": "Kuala Lumpur, Malaysia",
        "city": "Kuala Lumpur",
        "client_visibility": {"chatgpt": 0.5, "perplexity": 0.375, "gemini": 0.5, "claude": 0.25},
        "client_trait": (
            "its signature ayam gepuk — smashed fried chicken served with sambal — "
            "across multiple outlets in Malaysia"
        ),
        "client_extra": "It is a popular choice for affordable, spicy Indonesian-style fried chicken.",
        "client_comparison_trait": "is known for its signature ayam gepuk with sambal across its Malaysian outlets",
        "competitor_traits": {
            "Ayam Gepuk Pak Gembus": {
                "trait": "one of the largest ayam gepuk chains in Malaysia with many outlets and strong brand recognition",
                "extra": "It is often considered the pioneer of the ayam gepuk trend in Malaysia.",
                "comparison_trait": "is one of the largest and most recognized ayam gepuk chains in Malaysia",
            },
            "Ayam Gepuk Top Global": {
                "trait": "an ayam gepuk chain with a growing number of outlets across Malaysia",
                "extra": "It has been expanding its presence in shopping malls and food courts.",
                "comparison_trait": "is a growing ayam gepuk chain expanding across malls and food courts",
            },
            "Ayam Gepuk Artisan": {
                "trait": "an ayam gepuk restaurant brand offering a more premium, artisanal take on the dish",
                "extra": "It appeals to diners looking for a more upscale ayam gepuk experience.",
                "comparison_trait": "offers a more premium, artisanal take on ayam gepuk",
            },
        },
        "competitor_visibility": {
            "Ayam Gepuk Pak Gembus": {"chatgpt": 1.0, "perplexity": 0.75, "gemini": 0.75, "claude": 0.75},
            "Ayam Gepuk Top Global": {"chatgpt": 0.5, "perplexity": 0.5, "gemini": 0.5, "claude": 0.25},
            "Ayam Gepuk Artisan": {"chatgpt": 0.25, "perplexity": 0.25, "gemini": 0.25, "claude": 0.25},
        },
        "filler_names": ["KFC", "Ayam Penyet Ria"],
    },
    "toolkit": {
        "tagline": "Ayam Gepuk Tokmat — signature smashed fried chicken with sambal, served fresh across Malaysia.",
        "about": (
            "Ayam Gepuk Tokmat is a Malaysian restaurant chain specializing in ayam "
            "gepuk (smashed fried chicken) served with sambal, offering dine-in, "
            "takeaway, and delivery across its outlets."
        ),
        "sections": [
            (
                "Menu Highlights",
                "- Original Ayam Gepuk with Sambal\n- Ayam Gepuk Special (extra spicy)\n"
                "- Fried Rice & Sides\n- Iced Beverages",
            ),
            (
                "Outlets & Delivery",
                "Ayam Gepuk Tokmat operates multiple outlets across Malaysia with "
                "dine-in, takeaway, and delivery via major food delivery platforms.",
            ),
        ],
        "business_type": "Restaurant",
        "faqs": [
            ("What is ayam gepuk?", "Ayam gepuk is an Indonesian-style fried chicken dish that is smashed/pounded and served with sambal. Ayam Gepuk Tokmat serves its own version of this dish across its outlets in Malaysia."),
            ("Is Ayam Gepuk Tokmat halal?", "Ayam Gepuk Tokmat operates in accordance with halal practices common to Malaysian fried chicken restaurants; customers can check with individual outlets for specific certification details."),
            ("Where are Ayam Gepuk Tokmat outlets located?", "Ayam Gepuk Tokmat has multiple outlets across Malaysia. Exact locations and opening hours are listed on its website."),
            ("Does Ayam Gepuk Tokmat offer delivery?", "Yes, Ayam Gepuk Tokmat offers delivery through major food delivery platforms in addition to dine-in and takeaway."),
        ],
    },
    "content_analysis": {
        "topics_json": [
            {"topic": "Menu details & spice level guide", "status": "weak"},
            {"topic": "Halal certification information", "status": "missing"},
            {"topic": "Outlet locations & opening hours", "status": "strong"},
            {"topic": "Delivery & online ordering info", "status": "strong"},
            {"topic": "Franchise/business opportunity info", "status": "missing"},
            {"topic": "Comparisons vs other ayam gepuk chains", "status": "missing"},
        ],
        "entities_json": [
            {"entity": "Ayam Gepuk (Smashed Fried Chicken)", "covered": True},
            {"entity": "Sambal", "covered": True},
            {"entity": "Halal Certification", "covered": False},
            {"entity": "Outlet Locator", "covered": True},
            {"entity": "Delivery Partners (GrabFood, foodpanda)", "covered": True},
            {"entity": "Franchise Information", "covered": False},
        ],
        "suggested_content_json": [
            {
                "topic": "Halal certification",
                "title": "Is Ayam Gepuk Tokmat Halal? Certification & Sourcing Explained",
                "rationale": "Halal status is one of the most common questions for Malaysian food brands in AI search — a clear page closes a missing entity gap.",
            },
            {
                "topic": "Menu & spice guide",
                "title": "Ayam Gepuk Tokmat Menu Guide: Sambal Levels, Sides & What to Order",
                "rationale": "Detailed menu/spice-level content helps AI assistants answer 'what should I order' style questions with Tokmat-specific detail.",
            },
            {
                "topic": "Franchise info",
                "title": "Franchise with Ayam Gepuk Tokmat: Requirements & How to Apply",
                "rationale": "Franchise queries are a recommendation-category gap — Pak Gembus currently appears here instead of Tokmat.",
            },
        ],
        "content_metrics_json": {"word_count": 3200, "h1_count": 9, "faq_count": 4, "blog_count": 0, "schema_present": False},
        "content_quality_recommendation": (
            "Publish a halal certification page and a detailed menu/spice-level guide — "
            "both are commonly asked questions where Ayam Gepuk Pak Gembus currently has "
            "stronger AI visibility."
        ),
        "entity_coverage_score": 50.0,
        "pages_crawled": 14,
    },
    "roadmap_themes": [
        {
            "month": 1, "theme": "Halal & Trust Information", "priority": "high",
            "content_type": "Dedicated page + FAQ",
            "suggested_title": "Ayam Gepuk Tokmat Halal Certification & Sourcing",
            "rationale": (
                "Halal status is a top question for Malaysian F&B brands in AI search — "
                "publishing certification details gives AI assistants a direct, citable "
                "answer."
            ),
        },
        {
            "month": 2, "theme": "Menu & Spice Level Guide", "priority": "medium",
            "content_type": "Menu guide page",
            "suggested_title": "Ayam Gepuk Tokmat Menu Guide: Sambal Levels, Sides & Combos",
            "rationale": (
                "Detailed menu content helps Tokmat appear in 'what to order' and local "
                "recommendation queries where Pak Gembus currently dominates."
            ),
        },
        {
            "month": 3, "theme": "Outlet & Franchise Expansion Content", "priority": "low",
            "content_type": "Location + franchise pages",
            "suggested_title": "Ayam Gepuk Tokmat Outlets & Franchise Opportunities in Malaysia",
            "rationale": (
                "Franchise and 'near me' queries currently favor larger chains — "
                "expanded location and franchise content improves local AI visibility."
            ),
        },
    ],
    "actions": [
        {"dimension": "ai_citability", "closable_fraction": 0.35, "action_text": "Publish a halal certification and sourcing page — this is one of the most common AI search questions for Malaysian F&B brands and Tokmat currently has no page answering it."},
        {"dimension": "content_quality", "closable_fraction": 0.30, "action_text": "Add a detailed menu and spice-level guide so AI assistants can recommend specific Tokmat dishes when answering 'what to order' questions."},
        {"dimension": "brand_authority", "closable_fraction": 0.25, "action_text": "Pursue food-blogger and review coverage for outlets that currently lack it, to close the gap with Ayam Gepuk Pak Gembus's broader media presence."},
        {"dimension": "ai_citability", "closable_fraction": 0.30, "action_text": "Publish an outlet locator and franchise information page to improve visibility for local 'near me' and franchise-related queries."},
    ],
    "ai_traffic": {"current": 890, "prev": 760},
}


# ---------------------------------------------------------------------------
# CLIENT 5: Medilink Healthcare
# ---------------------------------------------------------------------------
MEDILINK = {
    "client": dict(
        name="Medilink Healthcare",
        website="https://medilinkhealthcare.my/",
        industry="Healthcare",
        description=(
            "Malaysian healthcare group operating a network of medical clinics and "
            "health screening centres across the Klang Valley, offering GP consultations, "
            "health screening packages, occupational health services, and specialist "
            "referrals for individuals and corporate clients."
        ),
        target_audience=(
            "Individuals, families, and corporate HR teams in the Klang Valley seeking "
            "accessible primary care, health screening, and occupational health services"
        ),
        city="Kuala Lumpur",
        state="Wilayah Persekutuan Kuala Lumpur",
        country="Malaysia",
        contact_email="enquiry@medilinkhealthcare.my",
        brand_authority_score=58,
        brand_authority_evidence=(
            "Recognised primary-care and health-screening provider with corporate "
            "panel relationships and local directory listings, but fewer authoritative "
            "health-content backlinks and press mentions than larger specialist groups "
            "like Sentosa Healthcare."
        ),
        content_quality_score=55,
        content_quality_evidence=(
            "Service and clinic-location pages are clear and useful, but health-screening "
            "explainers, condition guides, and corporate/occupational-health content are "
            "thin compared to competitors that publish dedicated patient-education hubs."
        ),
        avg_deal_value_rm=480,
    ),
    "competitors": [
        {"name": "Sentosa Healthcare", "website": "https://www.sshmedicare.com/"},
        {"name": "Care Clinic Group", "website": "https://careclinics.com.my/"},
        {"name": "Medipulse Healthcare", "website": "https://www.medipulse.com.my/"},
    ],
    "scan_profile": {
        "industry_phrase": "primary care and health screening provider",
        "location": "Kuala Lumpur, Klang Valley, Malaysia",
        "city": "Kuala Lumpur",
        "client_visibility": {"chatgpt": 0.5, "perplexity": 0.375, "gemini": 0.5, "claude": 0.375},
        "client_trait": (
            "accessible GP consultations, comprehensive health screening packages, and "
            "occupational health services delivered through a network of clinics across "
            "the Klang Valley"
        ),
        "client_extra": "It is increasingly used by corporate clients for staff health screening and panel clinic services.",
        "client_comparison_trait": (
            "focuses on accessible primary care, health screening, and corporate "
            "occupational health across multiple Klang Valley clinics"
        ),
        "competitor_traits": {
            "Sentosa Healthcare": {
                "trait": "a private specialist healthcare group offering specialist consultations, diagnostics, and inpatient services with a long-standing local reputation",
                "extra": "It is well known in the Klang Valley for its specialist and hospital-grade services.",
                "comparison_trait": "is a private specialist healthcare group with broader hospital-grade specialist and diagnostic services",
            },
            "Care Clinic Group": {
                "trait": "a network of family and GP clinics across Malaysia offering primary care, vaccinations, and health screening",
                "extra": "It has a wide clinic footprint and strong recognition for everyday family healthcare.",
                "comparison_trait": "is a widely-distributed family-clinic network strong in everyday primary care",
            },
            "Medipulse Healthcare": {
                "trait": "a healthcare provider offering GP services, health screening, and corporate wellness programmes",
                "extra": "It competes closely on corporate health screening and panel clinic services.",
                "comparison_trait": "is a close competitor on GP services, health screening, and corporate wellness",
            },
        },
        "competitor_visibility": {
            "Sentosa Healthcare": {"chatgpt": 0.75, "perplexity": 0.75, "gemini": 0.75, "claude": 0.5},
            "Care Clinic Group": {"chatgpt": 0.75, "perplexity": 0.5, "gemini": 0.5, "claude": 0.5},
            "Medipulse Healthcare": {"chatgpt": 0.5, "perplexity": 0.5, "gemini": 0.25, "claude": 0.25},
        },
        "filler_names": ["BookDoc", "Qualitas Health"],
    },
    "toolkit": {
        "tagline": (
            "Accessible primary care, health screening, and occupational health across "
            "the Klang Valley — GP consultations, screening packages, and corporate "
            "health services under one network."
        ),
        "about": (
            "Medilink Healthcare is a Malaysian healthcare group operating a network of "
            "medical clinics and health screening centres across the Klang Valley. It "
            "provides GP consultations, comprehensive health screening packages, "
            "occupational health services, and specialist referrals for both individual "
            "patients and corporate clients."
        ),
        "sections": [
            (
                "Our Services",
                "- GP Consultations & Primary Care\n- Health Screening Packages\n"
                "- Occupational & Corporate Health\n- Vaccinations & Travel Health\n"
                "- Specialist Referrals",
            ),
            (
                "Clinics & Corporate Health",
                "Medilink Healthcare operates multiple clinics across the Klang Valley "
                "and provides panel and occupational health services for corporate clients.",
            ),
        ],
        "business_type": "MedicalClinic",
        "faqs": [
            ("What services does Medilink Healthcare offer?", "Medilink Healthcare offers GP consultations, health screening packages, occupational and corporate health services, vaccinations, and specialist referrals through its network of Klang Valley clinics."),
            ("Where are Medilink Healthcare clinics located?", "Medilink Healthcare operates a network of clinics across the Klang Valley. Exact clinic locations and opening hours are listed on its website."),
            ("Does Medilink Healthcare provide corporate health screening?", "Yes, Medilink Healthcare provides corporate and occupational health services, including staff health screening and panel clinic arrangements for companies."),
            ("How do I book a health screening with Medilink Healthcare?", "Health screening appointments can be booked by contacting a Medilink Healthcare clinic directly or through the booking form on its website."),
        ],
    },
    "content_analysis": {
        "topics_json": [
            {"topic": "Health screening package explainers (what's included, who needs it)", "status": "weak"},
            {"topic": "Clinic locations & opening hours", "status": "strong"},
            {"topic": "Occupational & corporate health services", "status": "weak"},
            {"topic": "Condition & symptom guides (e.g. diabetes, hypertension screening)", "status": "missing"},
            {"topic": "Patient guides (panel/insurance, walk-in vs appointment)", "status": "missing"},
            {"topic": "Comparisons with other Klang Valley clinic groups", "status": "missing"},
        ],
        "entities_json": [
            {"entity": "Health Screening Packages", "covered": True},
            {"entity": "GP / Primary Care Consultation", "covered": True},
            {"entity": "Occupational Health Services", "covered": False},
            {"entity": "Corporate Panel / Cashless Clinic", "covered": False},
            {"entity": "Clinic Locator", "covered": True},
            {"entity": "Vaccination & Travel Health", "covered": False},
        ],
        "suggested_content_json": [
            {
                "topic": "Health screening explainers",
                "title": "Medilink Healthcare Health Screening Packages: What's Included and Who Should Get Screened",
                "rationale": "Health-screening questions are a high-volume AI query type — a clear package explainer gives AI assistants a citable Medilink source where competitors currently appear.",
            },
            {
                "topic": "Corporate / occupational health",
                "title": "Corporate Health Screening & Occupational Health with Medilink Healthcare: A Guide for HR Teams",
                "rationale": "Corporate health screening is a key revenue line and a recommendation-category gap where Medipulse and Care Clinic Group currently surface instead of Medilink.",
            },
            {
                "topic": "Condition guides",
                "title": "Diabetes and Hypertension Screening: When to Get Checked at Medilink Healthcare",
                "rationale": "Condition/symptom explainers are how AI assistants surface clinics for health questions — Sentosa Healthcare dominates this space today.",
            },
        ],
        "content_metrics_json": {"word_count": 6800, "h1_count": 21, "faq_count": 4, "blog_count": 1, "schema_present": False},
        "content_quality_recommendation": (
            "Build out health-screening and condition explainer pages, and a dedicated "
            "corporate/occupational-health hub — these are the query types where Sentosa "
            "Healthcare and Medipulse Healthcare currently appear instead of Medilink in AI answers."
        ),
        "entity_coverage_score": 56.0,
        "pages_crawled": 27,
    },
    "roadmap_themes": [
        {
            "month": 1, "theme": "Health Screening Explainer Hub", "priority": "high",
            "content_type": "Service explainer pages",
            "suggested_title": "Medilink Healthcare Health Screening Guide: Packages, Pricing & Who Should Get Screened",
            "rationale": (
                "AI assistants currently surface Sentosa Healthcare and Care Clinic Group "
                "for health-screening questions — dedicated explainer pages per package "
                "give Medilink a citable answer for these high-intent queries."
            ),
        },
        {
            "month": 2, "theme": "Corporate & Occupational Health", "priority": "high",
            "content_type": "Service landing pages",
            "suggested_title": "Corporate Health Screening & Occupational Health Services from Medilink Healthcare",
            "rationale": (
                "Corporate and occupational-health queries currently favor Medipulse "
                "Healthcare — a clear corporate-services hub helps Medilink appear in "
                "these HR-driven recommendation shortlists."
            ),
        },
        {
            "month": 3, "theme": "Condition Guides & Local Trust Content", "priority": "medium",
            "content_type": "Condition explainer articles",
            "suggested_title": "Choosing a Clinic in the Klang Valley: A Patient's Guide to Medilink Healthcare",
            "rationale": (
                "Local 'best clinic near me' and condition-screening queries are where "
                "Medilink should have a natural advantage — condition guides and "
                "patient-guide content reinforce this local relevance for AI assistants."
            ),
        },
    ],
    "actions": [
        {"dimension": "ai_citability", "closable_fraction": 0.35, "action_text": "Publish health-screening explainer pages (what's included, recommended ages, how to prepare) so AI assistants have a Medilink source to cite for screening questions where competitors currently appear."},
        {"dimension": "content_quality", "closable_fraction": 0.30, "action_text": "Build a corporate/occupational-health hub and add condition-screening guides (diabetes, hypertension) — both are missing entity signals competitors already cover."},
        {"dimension": "brand_authority", "closable_fraction": 0.25, "action_text": "Pursue local press and health-directory coverage across Klang Valley publications to build third-party mentions and backlinks beyond Medilink's own site."},
        {"dimension": "ai_citability", "closable_fraction": 0.30, "action_text": "Publish a 'best clinic / health screening in the Klang Valley' style local guide to strengthen Medilink's presence in local recommendation queries where Sentosa Healthcare and Care Clinic Group currently appear."},
    ],
    "ai_traffic": {"current": 1680, "prev": 1320},
}


CLIENT_PROFILES = [GLAD2GLOW, AVISENA, NEWNORMZ, AYAM_GEPUK_TOKMAT, MEDILINK]


def seed_client(db, profile: dict) -> None:
    client_kwargs = profile["client"]
    print(f"Seeding {client_kwargs['name']}...")

    client = Client(
        **client_kwargs,
        technical_foundations_verified=True,
        structured_data_verified=True,
        created_at=CLIENT_CREATED,
        share_token=secrets.token_urlsafe(32),
        share_token_created_at=SHARE_LINK_CREATED,
    )
    db.add(client)
    db.flush()

    competitors = []
    for comp in profile["competitors"]:
        c = Competitor(client_id=client.id, name=comp["name"], website=comp["website"])
        db.add(c)
        competitors.append(c)
    db.flush()

    # --- old scan (month-ago baseline) ---
    scan_old = Scan(
        client_id=client.id, platform="multi", status="completed",
        triggered_at=OLD_SCAN_COMPLETED - timedelta(minutes=20),
        completed_at=OLD_SCAN_COMPLETED,
    )
    db.add(scan_old)
    db.flush()

    rng_old = random.Random(f"{client.name}-old")
    old_profile = derate_profile(profile["scan_profile"], delta=0.125)
    results_old, _ = build_client_scan_results(old_profile, rng_old, scan_old.id, client.name, competitors)
    db.add_all(results_old)
    db.flush()
    geo_score_old = save_geo_score(db, client, scan_old, results_old, computed_at=OLD_SCAN_COMPLETED)

    # --- new scan (current) ---
    scan_new = Scan(
        client_id=client.id, platform="multi", status="completed",
        triggered_at=NEW_SCAN_COMPLETED - timedelta(minutes=20),
        completed_at=NEW_SCAN_COMPLETED,
    )
    db.add(scan_new)
    db.flush()

    rng_new = random.Random(f"{client.name}-new")
    results_new, lost_new = build_client_scan_results(profile["scan_profile"], rng_new, scan_new.id, client.name, competitors)
    db.add_all(results_new)
    db.flush()
    geo_score_new = save_geo_score(db, client, scan_new, results_new, computed_at=NEW_SCAN_COMPLETED)
    db.flush()

    # --- AI Readiness Toolkit (verified) ---
    toolkit = profile["toolkit"]
    llms_txt = build_llms_txt(
        client.name, client.website, toolkit["tagline"], toolkit["about"], toolkit["sections"],
    )
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

    # --- content analysis (content gaps) ---
    ca = profile["content_analysis"]
    db.add(ContentAnalysis(
        client_id=client.id, status="completed",
        topics_json=ca["topics_json"], entities_json=ca["entities_json"],
        suggested_content_json=ca["suggested_content_json"],
        entity_coverage_score=ca["entity_coverage_score"],
        content_metrics_json=ca["content_metrics_json"],
        content_quality_recommendation=ca["content_quality_recommendation"],
        pages_crawled=ca["pages_crawled"],
        analyzed_at=NEW_SCAN_COMPLETED + timedelta(hours=2),
    ))

    # --- 90-day content roadmap, driven by real lost queries ---
    roadmap_json = build_roadmap_json(profile["roadmap_themes"], lost_new)
    db.add(ContentRoadmap(
        client_id=client.id, status="completed",
        roadmap_json=roadmap_json, source_query_count=len(lost_new),
        generated_at=NEW_SCAN_COMPLETED + timedelta(hours=3),
        created_at=NEW_SCAN_COMPLETED + timedelta(hours=3),
    ))

    # --- action recommendations, scored from the new GeoScore ---
    dimension_scores = {
        "ai_citability": geo_score_new.ai_citability,
        "brand_authority": geo_score_new.brand_authority,
        "content_quality": geo_score_new.content_quality,
        "technical_foundations": geo_score_new.technical_foundations,
        "structured_data": geo_score_new.structured_data,
    }
    for action in profile["actions"]:
        impact = compute_action_impact(action["dimension"], dimension_scores[action["dimension"]], action["closable_fraction"])
        db.add(ActionRecommendation(
            client_id=client.id, geo_score_id=geo_score_new.id,
            action_text=action["action_text"], dimension=action["dimension"],
            estimated_impact=impact, priority=compute_action_priority(impact),
            status="open", generated_at=NEW_SCAN_COMPLETED + timedelta(hours=1),
        ))

    # --- content briefs for up to 3 lost queries ---
    brief_notes = []
    for entry in lost_new[:3]:
        result = entry["result"]
        title, angle, outline = make_content_brief_fields(
            client.name, profile["scan_profile"]["industry_phrase"],
            profile["scan_profile"]["location"], profile["scan_profile"]["city"],
            result.query_text, entry["competitors_seen"], result.category,
        )
        db.add(ContentBrief(
            client_id=client.id, scan_query_result_id=result.id,
            platform=result.platform, query_text=result.query_text,
            competitors_seen=entry["competitors_seen"],
            title=title, angle=angle, outline=outline,
            generated_at=NEW_SCAN_COMPLETED + timedelta(hours=4),
        ))
        brief_notes.append(result.query_text)

    # --- AI traffic snapshots (current + previous month) ---
    current_period = NOW.date().replace(day=1)
    prev_period = (current_period - timedelta(days=1)).replace(day=1)
    db.add(AiTrafficSnapshot(client_id=client.id, period=current_period, ai_visitors=profile["ai_traffic"]["current"]))
    db.add(AiTrafficSnapshot(client_id=client.id, period=prev_period, ai_visitors=profile["ai_traffic"]["prev"]))

    # --- activity log timeline ---
    activity = [
        (CLIENT_CREATED, "client_created", f"Client {client.name} created."),
        (TOOLKIT_GENERATED, "toolkit_generated", "AI Readiness Toolkit files generated (llms.txt, schema.json, robots.txt)."),
        (TOOLKIT_VERIFIED, "toolkit_verified", "Toolkit verification run. Files verified: llms.txt, schema.json, robots.txt."),
        (OLD_SCAN_COMPLETED, "scan_completed", f"Scan completed across 4 platforms. Overall score: {geo_score_old.overall_score:.0f}."),
        (NEW_SCAN_COMPLETED, "scan_completed", f"Scan completed across 4 platforms. Overall score: {geo_score_new.overall_score:.0f}."),
        (NEW_SCAN_COMPLETED + timedelta(hours=2), "traffic_updated", "AI traffic snapshot recorded for this month."),
        (SHARE_LINK_CREATED, "share_link_generated", "Client view share link generated."),
        (NEW_SCAN_COMPLETED + timedelta(hours=3), "content_analyzed", "Content gap analysis completed."),
    ]
    for ts, event_type, note in activity:
        db.add(ActivityLog(client_id=client.id, event_type=event_type, note=note, created_at=ts))
    for q in brief_notes:
        db.add(ActivityLog(
            client_id=client.id, event_type="brief_generated",
            note=f"Content brief generated for query: {q[:100]}",
            created_at=NEW_SCAN_COMPLETED + timedelta(hours=4),
        ))

    db.commit()
    print(f"  -> client_id={client.id}  overall_score={geo_score_new.overall_score:.1f}")


def main():
    # Optional CLI args filter which demo clients to seed by name (case-insensitive,
    # substring match). No args = seed all profiles.
    import sys

    requested = [a.lower() for a in sys.argv[1:]]
    if requested:
        profiles = [
            p for p in CLIENT_PROFILES
            if any(r in p["client"]["name"].lower() for r in requested)
        ]
        if not profiles:
            print(f"No demo profiles matched: {sys.argv[1:]}")
            print(f"Available: {[p['client']['name'] for p in CLIENT_PROFILES]}")
            return
    else:
        profiles = CLIENT_PROFILES

    db = SessionLocal()
    try:
        for profile in profiles:
            seed_client(db, profile)

        print("\nGenerating PDF reports...")
        for profile in profiles:
            name = profile["client"]["name"]
            client = db.query(Client).filter(Client.name == name).order_by(Client.created_at.desc()).first()
            try:
                report = generate_report_pdf(client.id, db)
            except Exception as exc:  # report storage (R2) may be unconfigured locally
                print(f"  -> {name}: report generation failed ({exc}); client data still seeded")
                continue
            if report:
                print(f"  -> {name}: {report.r2_url}")
            else:
                print(f"  -> {name}: report generation skipped (no scan data in range)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
