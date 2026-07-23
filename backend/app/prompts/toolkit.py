# backend/app/prompts/toolkit.py
"""Prompt templates for the AI Readiness Toolkit file generators."""
from app.models.client import Client

LLMS_TXT_VERSION = "v3"
LLMS_FULL_TXT_VERSION = "v1"
# v4: feed logo_url as logo/image; drop the WordPress-only SearchAction; stop
# emitting hallucinated sameAs URLs into the published file.
# v5: add Service (one per main service) + BreadcrumbList to the @graph.
SCHEMA_JSON_VERSION = "v5"

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


def build_llms_full_txt(client: Client) -> str:
    location_parts = [p for p in [client.city, client.state, client.country] if p]
    location = ", ".join(location_parts)

    return f"""Generate an llms-full.txt file for this business — the extended companion \
to llms.txt, giving AI assistants the full picture in one file.

Required format — use exactly these section headings in this order:

# {client.name}
> [One-sentence tagline: what the business does and who it serves, under 20 words]

## About
[3-5 sentences: mission, core offering, history if inferable, what makes this business \
distinctive from competitors]

## Services
[For EACH main service or product: a "### Service name" subheading followed by 2-3 \
sentences describing what it is, who it's for, and what to expect. Infer services from \
the industry and description. 3-8 services.]

## Target Audience
[Specific description of who the business serves — be concrete, not generic]

## Location
[City, state/region, country — for local AI discovery. Omit this entire section if no \
location was provided.]

## Key Pages
[Bullet list of the site's likely key URLs using the website domain: homepage, and one \
per main service using clean, plausible paths like {client.website}/services. Only use \
the domain provided — never invent other domains.]

## Policies
[2-4 short bullets covering how the business typically works with customers: how to get \
started, consultations or quotes, what a first visit or engagement looks like. Infer \
conservatively from the industry — write nothing that promises specific prices or terms.]

## Contact
[Website URL. Include contact email on a second line only if one was provided.]

## Key Facts
[5-8 bullet points an AI should know when deciding whether to recommend this business]

## Questions & Answers
[8-12 Q&A pairs. Write the questions exactly as a potential customer would ask an AI \
assistant — natural, conversational language. Each answer must be 1-3 sentences, \
specific to this business, and naturally include the business name. Cover: what the \
business does, who it's for, each main service, what makes it different, how to get \
started, and location/area served if provided.]

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
- Be specific to THIS business — no generic filler
- Never invent prices, phone numbers, addresses, or URLs on other domains
- Omit the Location section entirely if no location was provided
- Output ONLY the raw llms-full.txt content. No explanations. No code block wrappers."""


def build_schema_json(client: Client) -> str:
    schema_type = _schema_type_for(client.industry)
    location = ", ".join(p for p in [client.city, client.state, client.country] if p)
    has_logo = bool(client.logo_url)

    return f"""Generate a JSON-LD structured data file for this business.

Output a single JSON object with "@context": "https://schema.org" and "@graph": [ ... ] \
containing exactly these 6 schemas:

Schema 1 — Primary business type:
  @type: "{schema_type}"  (chosen for industry: {client.industry})
  @id: "{client.website}/#business"
  name, url, description
  address as PostalAddress:
    addressLocality: "{client.city or ""}"
    addressRegion: "{client.state or ""}"
    addressCountry: use the 2-letter ISO 3166 country code for "{client.country or ""}" (e.g. Malaysia → "MY")
    (omit addressLocality/addressRegion/addressCountry if their value is empty)
  email: "{client.contact_email or ""}"  (omit the email field entirely if empty)
  {'image: "' + client.logo_url + '"' if has_logo else 'image: (omit — no logo provided)'}
  parentOrganization: {{"@id": "{client.website}/#organization"}}
  speakable: {{"@type": "SpeakableSpecification", "cssSelector": ["h1", "h2"]}}

Schema 2 — Organization:
  @type: "Organization"
  @id: "{client.website}/#organization"
  name, url, description
  email (omit if empty, same rule as above)
  {'logo: "' + client.logo_url + '"' if has_logo else 'logo: (omit — no logo provided)'}

Do NOT add a "sameAs" field to either schema. Social/directory profile URLs are
added by the admin after verification — never invent them.

Schema 3 — WebSite:
  @type: "WebSite"
  @id: "{client.website}/#website"
  url: "{client.website}"
  name: "{client.name}"
  publisher: {{"@id": "{client.website}/#organization"}}
  Do NOT add a "potentialAction"/SearchAction — the site's search URL is unknown.

Schema 4 — FAQPage:
  @type: "FAQPage"
  @id: "{client.website}/#faq"
  about: {{"@id": "{client.website}/#business"}}
  mainEntity: 3-5 Question + acceptedAnswer pairs that a real potential customer of this business would ask
  Make the questions specific to this industry and business, not generic

Schema 5 — Services:
  One "Service" entry per main service of the business (2-5 services, inferred from the
  industry and description). For each:
  @type: "Service"
  @id: "{client.website}/#service-N"  (N = 1, 2, 3…)
  name: the service name
  description: one sentence
  provider: {{"@id": "{client.website}/#business"}}
  areaServed: "{location or 'omit if unknown'}"  (omit the field if no location was provided)

Schema 6 — BreadcrumbList:
  @type: "BreadcrumbList"
  @id: "{client.website}/#breadcrumbs"
  itemListElement: exactly 2 ListItem entries:
    position 1: name "Home", item "{client.website}"
    position 2: name "Services", item "{client.website}/services"

---

Business details:
Name: {client.name}
Website: {client.website}
Industry: {client.industry}
Schema type: {schema_type}
Description: {client.description or "Not provided"}
Location: {location or "Not provided"}
Contact email: {client.contact_email or "Not provided"}
Logo URL: {client.logo_url or "Not provided"}

Output ONLY valid JSON. No explanations. No code block wrapper. Start directly with {{"""
