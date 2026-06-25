# backend/app/prompts/toolkit.py
"""Prompt templates for the AI Readiness Toolkit file generators."""
from app.models.client import Client

LLMS_TXT_VERSION = "v3"
SCHEMA_JSON_VERSION = "v3"

# Maps common industry keywords → the most specific schema.org type.
# Checked in order; first match wins. Falls back to LocalBusiness.
_INDUSTRY_SCHEMA_TYPES: list[tuple[str, str]] = [
    ("dental", "Dentist"),
    ("dentist", "Dentist"),
    ("clinic", "MedicalClinic"),
    ("healthcare", "MedicalBusiness"),
    ("medical", "MedicalBusiness"),
    ("hospital", "Hospital"),
    ("pharmacy", "Pharmacy"),
    ("attorney", "LegalService"),
    ("lawyer", "LegalService"),
    ("legal", "LegalService"),
    ("law firm", "LegalService"),
    ("restaurant", "Restaurant"),
    ("cafe", "CafeOrCoffeeShop"),
    ("coffee", "CafeOrCoffeeShop"),
    ("food", "FoodEstablishment"),
    ("bakery", "Bakery"),
    ("hotel", "LodgingBusiness"),
    ("resort", "LodgingBusiness"),
    ("accommodation", "LodgingBusiness"),
    ("university", "CollegeOrUniversity"),
    ("college", "CollegeOrUniversity"),
    ("school", "School"),
    ("education", "EducationalOrganization"),
    ("e-commerce", "OnlineStore"),
    ("ecommerce", "OnlineStore"),
    ("retail", "Store"),
    ("property", "RealEstateAgent"),
    ("real estate", "RealEstateAgent"),
    ("accounting", "AccountingService"),
    ("insurance", "InsuranceAgency"),
    ("finance", "FinancialService"),
    ("bank", "BankOrCreditUnion"),
    ("hair salon", "HairSalon"),
    ("salon", "HairSalon"),
    ("spa", "HealthAndBeautyBusiness"),
    ("beauty", "HealthAndBeautyBusiness"),
    ("gym", "SportsActivityLocation"),
    ("fitness", "SportsActivityLocation"),
    ("veterinary", "VeterinaryCare"),
    ("vet", "VeterinaryCare"),
]


def _schema_type_for(industry: str) -> str:
    lower = industry.lower()
    for keyword, schema_type in _INDUSTRY_SCHEMA_TYPES:
        if keyword in lower:
            return schema_type
    return "LocalBusiness"


def build_llms_txt(client: Client) -> str:
    location_parts = [p for p in [client.city, client.state, client.country] if p]
    location = ", ".join(location_parts)

    return f"""Generate an llms.txt file for this business following the Answer.AI spec.

Required format — use exactly these section headings in this order:

# {client.name}
> [One-sentence tagline: what the business does and who it serves, under 20 words]

## About
[2-3 sentences: mission, core offering, what makes this business distinctive from competitors]

## Services
[Bullet list of main services or products, inferred from the industry and description]

## Target Audience
[Specific description of who the business serves — be concrete, not generic]

## Location
[City, state/region, country — for local AI discovery. Omit this entire section if no location was provided.]

## Contact
[Website URL. Include contact email on a second line only if one was provided.]

## Key Facts
[3-5 bullet points an AI should know when deciding whether to recommend this business to a customer]

## Questions & Answers
[4-6 Q&A pairs. Write the questions exactly as a potential customer would ask an AI assistant — \
natural, conversational language, not keyword-stuffed. Each answer must be 1-2 sentences, \
specific to this business, and naturally include the business name. \
Cover: what the business does, who it's for, what makes it different, how to get started.]

---

Business details:
Name: {client.name}
Website: {client.website}
Industry: {client.industry}
Description: {client.description or "Not provided"}
Target audience: {client.target_audience or "Not provided"}
Location: {location or "Not provided"}
Contact email: {client.contact_email or "Not provided"}

Rules:
- Start with # {client.name} on the very first line — no blank line before it
- Keep the > tagline under 20 words
- Be specific to THIS business — no generic filler
- Omit the Location section entirely if no location was provided
- The Questions & Answers section is required — do not omit it
- Output ONLY the raw llms.txt content. No explanations. No code block wrappers."""


def build_schema_json(client: Client) -> str:
    schema_type = _schema_type_for(client.industry)
    location = ", ".join(p for p in [client.city, client.state, client.country] if p)

    return f"""Generate a JSON-LD structured data file for this business.

Output a single JSON object with "@context": "https://schema.org" and "@graph": [ ... ] \
containing exactly these 4 schemas:

Schema 1 — Primary business type:
  @type: "{schema_type}"  (chosen for industry: {client.industry})
  @id: "{client.website}/#business"
  name, url, description
  address as PostalAddress:
    addressLocality: "{client.city or ""}"
    addressRegion: "{client.state or ""}"
    addressCountry: "{client.country or ""}"
    (omit addressLocality/addressRegion/addressCountry if their value is empty)
  email: "{client.contact_email or ""}"  (omit the email field entirely if empty)
  speakable: {{"@type": "SpeakableSpecification", "cssSelector": ["h1", "h2", "[itemprop=description]"]}}
  sameAs: [see sameAs rules below]

Schema 2 — Organization:
  @type: "Organization"
  @id: "{client.website}/#organization"
  name, url, description
  email (omit if empty, same rule as above)
  sameAs: [same array as Schema 1]

sameAs rules — apply the SAME array to both Schema 1 and Schema 2:
  Generate 3-5 likely social and directory profile URLs for "{client.name}" ({client.industry}).
  Slug: lowercase the business name, replace spaces with hyphens, remove special characters.
  Always include:
    "https://www.linkedin.com/company/[slug]"
    "https://www.facebook.com/[slug-no-hyphens]"
  Add 1-2 industry-relevant directories chosen from:
    Healthcare/clinic/dental → Healthgrades, RateMDs
    Legal/law → Avvo, FindLaw
    Restaurant/food/cafe → Yelp, TripAdvisor
    Hotel/resort → TripAdvisor, Booking.com
    Fitness/beauty/spa → Yelp, Treatwell
    All others → "https://maps.google.com/?q=[business+name+url-encoded]", Yelp
  These are best-guess URLs for the admin to verify before publishing.

Schema 3 — WebSite:
  @type: "WebSite"
  @id: "{client.website}/#website"
  url: "{client.website}"
  name: "{client.name}"
  potentialAction: SearchAction with target "{client.website}/?s={{search_term_string}}" and query-input "required name=search_term_string"

Schema 4 — FAQPage:
  @type: "FAQPage"
  mainEntity: 3-5 Question + acceptedAnswer pairs that a real potential customer of this business would ask
  Make the questions specific to this industry and business, not generic

---

Business details:
Name: {client.name}
Website: {client.website}
Industry: {client.industry}
Schema type: {schema_type}
Description: {client.description or "Not provided"}
Location: {location or "Not provided"}
Contact email: {client.contact_email or "Not provided"}

Output ONLY valid JSON. No explanations. No code block wrapper. Start directly with {{"""
