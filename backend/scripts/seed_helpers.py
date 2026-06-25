# backend/scripts/seed_helpers.py
"""Shared helpers for seeding demo clients with fabricated-but-plausible scan
data. Used by seed_demo_clients.py — not imported by the running app.

Response text is generated from small template banks rather than hand-written
per row, so the ~80 ScanQueryResult rows per client read naturally without
requiring hundreds of bespoke strings.
"""
import json
import random
from datetime import datetime

from app.core.constants import (
    COMPETITOR_QUERY_TEMPLATES,
    QUERY_TEMPLATES,
    SCAN_PLATFORMS,
)
from app.models.scan_query_result import ScanQueryResult
from app.services.scoring_service import (
    compute_ai_citability,
    compute_geo_score,
    compute_platform_breakdown,
)
from app.models.geo_score import GeoScore
from app.core.constants import ACTION_IMPACT_MAX_PER_ACTION, ACTION_PRIORITY_BANDS, SCORE_WEIGHTS

PLATFORMS = list(SCAN_PLATFORMS)  # ["chatgpt", "perplexity", "gemini", "claude"]

# Per-platform "AI voice" opener, used so identical templates don't read
# verbatim-identically across platforms.
_PLATFORM_OPENERS = {
    "chatgpt": "Based on what I know,",
    "perplexity": "According to recent sources,",
    "gemini": "From available information,",
    "claude": "From what I can find,",
}

# ---------------------------------------------------------------------------
# Brand-category templates: "Tell me about {brand}" / "What is {brand} known for?"
# ---------------------------------------------------------------------------
_BRAND_DETECTED = [
    "{opener} {subject} is {article} {industry_phrase} based in {location}. "
    "{subject} is best known for {trait}. {extra}",
    "{subject} is {article} {industry_phrase} operating in {location}. "
    "It has built a reputation for {trait}, and {extra}",
]

_BRAND_NOT_DETECTED = [
    "{opener} I don't have specific information about {subject}. "
    "If you're looking for {industry_phrase} options in {location}, well-known names "
    "include {others_list}.",
    "{opener} I couldn't find detailed information on {subject}. "
    "Some established {industry_phrase} businesses in {location} include {others_list}.",
]

# ---------------------------------------------------------------------------
# Comparison-category templates: "{brand} vs {competitor}" / "Compare {brand} and {competitor}"
# ---------------------------------------------------------------------------
_COMPARISON_BOTH_KNOWN = [
    "{opener} {brand} and {competitor} are both {industry_phrase} options. "
    "{brand} {trait_brand}, while {competitor} {trait_competitor}. "
    "Both are worth considering depending on your priorities.",
]

_COMPARISON_ONLY_COMPETITOR = [
    "{opener} I'm not familiar with {brand}. {competitor}, however, {trait_competitor} "
    "and is a recognizable name in {location}.",
]

_COMPARISON_ONLY_BRAND = [
    "{opener} {brand} {trait_brand} and is active in {location}. "
    "I don't have information on {competitor} for comparison.",
]

# ---------------------------------------------------------------------------
# Recommendation / Local templates — ranked-list style answers.
# "Best {industry} in {location}" / "Best {industry} near me in {city}"
# ---------------------------------------------------------------------------
_LIST_INTROS = {
    "recommendation": "{opener} here are some well-regarded {industry_phrase} options in {location}:",
    "local": "{opener} here are some {industry_phrase} options near {city}:",
}

_LIST_NO_RESULTS = {
    "recommendation": "{opener} I don't have a confident list of specific {industry_phrase} "
    "businesses in {location}, but I'd recommend checking local directories and reviews.",
    "local": "{opener} I don't have specific recommendations for {industry_phrase} near {city} "
    "off the top of my head — local search or maps would give more current results.",
}


def _industry_article(industry_phrase: str) -> str:
    return "an" if industry_phrase[0].lower() in "aeiou" else "a"


def build_brand_response(
    rng: random.Random,
    opener: str,
    subject: str,
    detected: bool,
    industry_phrase: str,
    location: str,
    trait: str,
    extra: str,
    others: list[str],
) -> str:
    if detected:
        template = rng.choice(_BRAND_DETECTED)
        return template.format(
            opener=opener,
            subject=subject,
            article=_industry_article(industry_phrase),
            industry_phrase=industry_phrase,
            location=location,
            trait=trait,
            extra=extra,
        )
    template = rng.choice(_BRAND_NOT_DETECTED)
    return template.format(
        opener=opener,
        subject=subject,
        industry_phrase=industry_phrase,
        location=location,
        others_list=", ".join(others),
    )


def build_comparison_response(
    rng: random.Random,
    opener: str,
    brand: str,
    competitor: str,
    brand_known: bool,
    competitor_known: bool,
    industry_phrase: str,
    location: str,
    trait_brand: str,
    trait_competitor: str,
) -> str:
    if brand_known and competitor_known:
        template = rng.choice(_COMPARISON_BOTH_KNOWN)
    elif competitor_known:
        template = rng.choice(_COMPARISON_ONLY_COMPETITOR)
    else:
        template = rng.choice(_COMPARISON_ONLY_BRAND)
    return template.format(
        opener=opener,
        brand=brand,
        competitor=competitor,
        industry_phrase=industry_phrase,
        location=location,
        trait_brand=trait_brand,
        trait_competitor=trait_competitor,
    )


def build_ranked_list_response(
    rng: random.Random,
    opener: str,
    category: str,  # "recommendation" | "local"
    industry_phrase: str,
    location: str,
    city: str,
    names_in_order: list[str],
) -> str:
    """names_in_order: ordered list of business names to present as a ranked list.
    Empty list -> a "no confident answer" response."""
    if not names_in_order:
        return _LIST_NO_RESULTS[category].format(
            opener=opener, industry_phrase=industry_phrase, location=location, city=city
        )
    intro = _LIST_INTROS[category].format(
        opener=opener, industry_phrase=industry_phrase, location=location, city=city
    )
    items = "\n".join(f"{i + 1}. {name}" for i, name in enumerate(names_in_order))
    return f"{intro}\n{items}"


def visibility_to_flags(rng: random.Random, total: int, target_fraction: float) -> list[bool]:
    """Return a list of `total` booleans with round(total*target_fraction) True,
    shuffled deterministically via rng."""
    detected_count = round(total * target_fraction)
    flags = [True] * detected_count + [False] * (total - detected_count)
    rng.shuffle(flags)
    return flags


def _client_brand_queries(profile: dict, rng: random.Random, platform: str, client_name: str, competitors: list) -> list[ScanQueryResult]:
    """Build the 8 client-perspective ScanQueryResult rows for one platform:
    2 brand, 2 comparison (vs top-2 competitors), 2 recommendation, 2 local."""
    opener = _PLATFORM_OPENERS[platform]
    location = profile["location"]
    city = profile["city"]
    industry_phrase = profile["industry_phrase"]
    # One flag per client-perspective query this platform will emit. Comparison
    # queries are capped by the number of tracked competitors (one per competitor),
    # mirroring the real scan engine; the others run every template in the category.
    n_comparison = min(len(QUERY_TEMPLATES["comparison"]), len(competitors))
    total_flags = (
        len(QUERY_TEMPLATES["brand"])
        + n_comparison
        + len(QUERY_TEMPLATES["recommendation"])
        + len(QUERY_TEMPLATES["local"])
    )
    flags = visibility_to_flags(rng, total_flags, profile["client_visibility"][platform])
    results: list[ScanQueryResult] = []
    lost_entries: list[dict] = []

    # --- brand category (2 queries) ---
    for template in QUERY_TEMPLATES["brand"]:
        detected = flags.pop()
        others = [c.name for c in competitors[:2]] or profile.get("filler_names", ["other local providers"])
        response = build_brand_response(
            rng, opener, client_name, detected, industry_phrase, location,
            profile["client_trait"], profile["client_extra"], others,
        )
        results.append(ScanQueryResult(
            platform=platform, competitor_id=None, category="brand",
            query_text=template.format(brand=client_name),
            response_text=response, brand_detected=detected,
        ))

    # --- comparison category (up to 2 queries, vs competitors[0] / competitors[1]) ---
    for i, template in enumerate(QUERY_TEMPLATES["comparison"]):
        if i >= len(competitors):
            break
        competitor = competitors[i]
        detected = flags.pop()
        comp_info = profile["competitor_traits"][competitor.name]
        response = build_comparison_response(
            rng, opener, client_name, competitor.name,
            brand_known=detected, competitor_known=True,
            industry_phrase=industry_phrase, location=location,
            trait_brand=profile["client_comparison_trait"],
            trait_competitor=comp_info["comparison_trait"],
        )
        results.append(ScanQueryResult(
            platform=platform, competitor_id=None, category="comparison",
            query_text=template.format(brand=client_name, competitor=competitor.name),
            response_text=response, brand_detected=detected,
        ))

    # --- recommendation (2) + local (2) — ranked-list style ---
    for category in ("recommendation", "local"):
        for template in QUERY_TEMPLATES[category]:
            client_in_list = flags.pop()
            names_in_order: list[str] = []
            position: int | None = None
            competitors_seen: list[str] = []

            if client_in_list:
                # Mostly "shared" (client + 1-2 competitors), sometimes a clean "won".
                if rng.random() < 0.35:
                    others_in_list = []
                else:
                    others_in_list = [c.name for c in rng.sample(competitors, k=min(2, len(competitors)))]
                names_in_order = others_in_list[:]
                position = rng.randint(1, len(names_in_order) + 1)
                names_in_order.insert(position - 1, client_name)
                competitors_seen = others_in_list
            else:
                # Mostly "lost" (1-2 competitors shown, client absent), sometimes "open".
                if rng.random() < 0.15:
                    names_in_order = []
                else:
                    names_in_order = [c.name for c in rng.sample(competitors, k=min(2, len(competitors)))]
                competitors_seen = names_in_order[:]

            if category == "recommendation":
                query_text = template.format(industry=industry_phrase, location=location)
            else:
                query_text = template.format(industry=industry_phrase, city=city)

            response = build_ranked_list_response(
                rng, opener, category, industry_phrase, location, city, names_in_order,
            )
            result = ScanQueryResult(
                platform=platform, competitor_id=None, category=category,
                query_text=query_text, response_text=response,
                brand_detected=client_in_list,
                recommendation_position=position if client_in_list else None,
            )
            results.append(result)
            if not client_in_list and competitors_seen:
                lost_entries.append({"result": result, "competitors_seen": competitors_seen})

    return results, lost_entries


def _competitor_queries(profile: dict, rng: random.Random, platform: str, client_name: str, competitor) -> list[ScanQueryResult]:
    """Build the 4 competitor-perspective ScanQueryResult rows for one platform
    (brand, comparison, recommendation, local) — brand_detected = competitor's
    own visibility in that response."""
    opener = _PLATFORM_OPENERS[platform]
    location = profile["location"]
    city = profile["city"]
    industry_phrase = profile["industry_phrase"]
    comp_info = profile["competitor_traits"][competitor.name]
    flags = visibility_to_flags(rng, 4, profile["competitor_visibility"][competitor.name][platform])
    results: list[ScanQueryResult] = []

    # brand
    detected = flags.pop()
    others = [client_name] + [c for c in profile.get("filler_names", [])][:1]
    response = build_brand_response(
        rng, opener, competitor.name, detected, industry_phrase, location,
        comp_info["trait"], comp_info["extra"], others,
    )
    results.append(ScanQueryResult(
        platform=platform, competitor_id=competitor.id, category="brand",
        query_text=COMPETITOR_QUERY_TEMPLATES["brand"].format(competitor=competitor.name),
        response_text=response, brand_detected=detected,
    ))

    # comparison: "{competitor} vs {brand}"
    detected = flags.pop()
    response = build_comparison_response(
        rng, opener, competitor.name, client_name,
        brand_known=detected, competitor_known=True,
        industry_phrase=industry_phrase, location=location,
        trait_brand=comp_info["comparison_trait"],
        trait_competitor=profile["client_comparison_trait"],
    )
    results.append(ScanQueryResult(
        platform=platform, competitor_id=competitor.id, category="comparison",
        query_text=COMPETITOR_QUERY_TEMPLATES["comparison"].format(competitor=competitor.name, brand=client_name),
        response_text=response, brand_detected=detected,
    ))

    # recommendation: "Best {industry} company in {location}"
    detected = flags.pop()
    names = [competitor.name, client_name] if detected else [client_name]
    if detected:
        rng.shuffle(names)
    response = build_ranked_list_response(
        rng, opener, "recommendation", industry_phrase, location, city, names,
    )
    results.append(ScanQueryResult(
        platform=platform, competitor_id=competitor.id, category="recommendation",
        query_text=COMPETITOR_QUERY_TEMPLATES["recommendation"].format(industry=industry_phrase, location=location),
        response_text=response, brand_detected=detected,
    ))

    # local: "Top {industry} in {city}"
    detected = flags.pop()
    names = [competitor.name, client_name] if detected else [client_name]
    if detected:
        rng.shuffle(names)
    response = build_ranked_list_response(
        rng, opener, "local", industry_phrase, location, city, names,
    )
    results.append(ScanQueryResult(
        platform=platform, competitor_id=competitor.id, category="local",
        query_text=COMPETITOR_QUERY_TEMPLATES["local"].format(industry=industry_phrase, city=city),
        response_text=response, brand_detected=detected,
    ))

    return results


def build_client_scan_results(profile: dict, rng: random.Random, scan_id, client_name: str, competitors: list) -> tuple[list[ScanQueryResult], list[dict]]:
    """Build every ScanQueryResult row for one completed scan (all platforms,
    client + competitor queries). Returns (results, lost_entries) where
    lost_entries describe client recommendation/local queries the brand lost
    to a tracked competitor — used to seed ContentBrief rows."""
    all_results: list[ScanQueryResult] = []
    all_lost: list[dict] = []
    for platform in PLATFORMS:
        client_results, lost = _client_brand_queries(profile, rng, platform, client_name, competitors)
        all_results.extend(client_results)
        all_lost.extend(lost)
        for competitor in competitors:
            all_results.extend(_competitor_queries(profile, rng, platform, client_name, competitor))

    for r in all_results:
        r.scan_id = scan_id

    return all_results, all_lost


def compute_action_priority(estimated_impact: float) -> str:
    for priority, (lo, hi) in ACTION_PRIORITY_BANDS.items():
        if lo <= estimated_impact <= hi:
            return priority
    return "low"


def compute_action_impact(dimension: str, current_score: float, closable_fraction: float) -> float:
    """Mirror the real action-center math: impact = remaining gap to 100 on this
    dimension * its weight in the overall score * how much of that gap this
    action plausibly closes, capped at ACTION_IMPACT_MAX_PER_ACTION."""
    remaining_gap = max(0.0, 100.0 - current_score)
    weight = SCORE_WEIGHTS[dimension]
    impact = remaining_gap * weight * closable_fraction
    return round(min(impact, ACTION_IMPACT_MAX_PER_ACTION), 1)


_BRIEF_OUTLINES = {
    "recommendation": [
        "Why {industry_phrase} buyers in {location} are asking this question",
        "What {client_name} offers that fits this exact need",
        "Side-by-side comparison with {competitors_seen}",
        "Customer proof points and results",
        "How to get started with {client_name}",
    ],
    "local": [
        "What 'best {industry_phrase} near {city}' really means for local buyers",
        "{client_name}'s presence and service area in {city}",
        "How {client_name} compares to {competitors_seen} for local customers",
        "Local reviews, proof, and trust signals",
        "Next steps for {city}-based customers",
    ],
}


def make_content_brief_fields(client_name: str, industry_phrase: str, location: str, city: str, query_text: str, competitors_seen: list[str], category: str) -> tuple[str, str, list[str]]:
    """Generic but on-topic title/angle/outline for a lost recommendation/local
    query, used to seed ContentBrief rows without bespoke per-row writing."""
    comp_str = " and ".join(competitors_seen) if competitors_seen else "other providers"
    clean_query = query_text.rstrip("?")
    title = f"{clean_query}: Where {client_name} Fits In"
    angle = (
        f"AI assistants currently answer this with {comp_str} but not {client_name}. "
        f"A focused page that directly answers \"{query_text}\" with specifics about "
        f"{client_name}'s {industry_phrase} offering gives AI systems a clear, citable answer."
    )
    outline = [
        line.format(
            industry_phrase=industry_phrase, location=location, city=city,
            client_name=client_name, competitors_seen=comp_str,
        )
        for line in _BRIEF_OUTLINES[category]
    ]
    return title, angle, outline


def build_llms_txt(name: str, url: str, tagline: str, about: str, sections: list[tuple[str, str]]) -> str:
    """Answer.AI llms.txt spec: H1 name, blockquote tagline, then H2 sections."""
    lines = [f"# {name}", "", f"> {tagline}", "", "## About", about, ""]
    for heading, body in sections:
        lines.append(f"## {heading}")
        lines.append(body)
        lines.append("")
    lines.append("## Contact")
    lines.append(f"Website: {url}")
    return "\n".join(lines)


def build_schema_json(
    name: str,
    url: str,
    description: str,
    business_type: str,
    city: str,
    state: str,
    country: str,
    faqs: list[tuple[str, str]],
) -> str:
    """JSON-LD @graph: Organization + a LocalBusiness subtype + FAQPage."""
    graph = [
        {
            "@type": "Organization",
            "@id": f"{url}#organization",
            "name": name,
            "url": url,
            "description": description,
        },
        {
            "@type": business_type,
            "@id": f"{url}#localbusiness",
            "name": name,
            "url": url,
            "description": description,
            "address": {
                "@type": "PostalAddress",
                "addressLocality": city,
                "addressRegion": state,
                "addressCountry": country,
            },
        },
        {
            "@type": "FAQPage",
            "@id": f"{url}#faq",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": q,
                    "acceptedAnswer": {"@type": "Answer", "text": a},
                }
                for q, a in faqs
            ],
        },
    ]
    return json.dumps({"@context": "https://schema.org", "@graph": graph}, indent=2)


def derate_profile(profile: dict, delta: float) -> dict:
    """Return a copy of `profile` with each client_visibility fraction reduced
    by `delta` (clipped to >= 0) — used to build an "earlier scan" with a
    slightly worse score, so the dashboard shows a month-over-month trend."""
    new_profile = dict(profile)
    new_profile["client_visibility"] = {
        platform: max(0.0, fraction - delta)
        for platform, fraction in profile["client_visibility"].items()
    }
    return new_profile


def build_roadmap_json(themes: list[dict], lost_entries: list[dict]) -> list[dict]:
    """Merge hand-written roadmap themes with real lost-query data: each theme
    gets target_queries / competitors_winning drawn from the scan's lost_entries
    (recommendation/local queries the client didn't appear in)."""
    roadmap = []
    for i, theme in enumerate(themes):
        entry = dict(theme)
        # The roadmap is weekly now; map any legacy "month" key to a week.
        entry["week"] = entry.pop("month", i + 1)
        entry.setdefault("article_content", None)
        if lost_entries:
            picked = lost_entries[i % len(lost_entries)]
            entry["target_queries"] = [picked["result"].query_text]
            entry["competitors_winning"] = picked["competitors_seen"]
        else:
            entry["target_queries"] = []
            entry["competitors_winning"] = []
        roadmap.append(entry)
    return roadmap


def save_geo_score(db, client, scan, all_results: list[ScanQueryResult], computed_at: datetime) -> GeoScore:
    """Compute and persist a GeoScore using the app's real scoring functions,
    so the overall score / band stays internally consistent."""
    platform_breakdown = compute_platform_breakdown(all_results, failed_platforms=[])
    ai_citability = compute_ai_citability(all_results, platform_breakdown)
    overall = compute_geo_score(client, ai_citability)

    geo_score = GeoScore(
        client_id=client.id,
        scan_id=scan.id,
        ai_citability=ai_citability,
        brand_authority=float(client.brand_authority_score),
        content_quality=float(client.content_quality_score),
        technical_foundations=100.0 if client.technical_foundations_verified else 0.0,
        structured_data=100.0 if client.structured_data_verified else 0.0,
        overall_score=overall,
        platform_breakdown=platform_breakdown,
        computed_at=computed_at,
    )
    db.add(geo_score)
    return geo_score
