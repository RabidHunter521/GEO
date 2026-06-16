# backend/app/prompts/toolkit.py
"""Prompt templates for the AI Readiness Toolkit file generators."""
from app.models.client import Client

LLMS_TXT_VERSION = "v1"
SCHEMA_JSON_VERSION = "v1"


def build_llms_txt(client: Client) -> str:
    return f"""Generate an llms.txt file for this business.
llms.txt is a standard file (similar to robots.txt) that helps AI language models understand a website.
Follow the Answer.AI spec: start with # Brand Name on the first line, then > short one-sentence tagline, then markdown sections with relevant information.

Business details:
Name: {client.name}
Website: {client.website}
Industry: {client.industry}
Description: {client.description or 'Not provided'}
Target audience: {client.target_audience or 'Not provided'}
City: {client.city or 'Not provided'}
State: {client.state or 'Not provided'}

Output ONLY the raw llms.txt content. No explanations. No code block wrappers."""


def build_schema_json(client: Client) -> str:
    return f"""Generate a JSON-LD structured data file for this business.
Include these schema types in a @graph array:
1. LocalBusiness (or an appropriate subtype like ProfessionalService, Restaurant, etc.)
2. Organization
3. FAQPage with 3-5 realistic FAQ items about this specific business

Business details:
Name: {client.name}
Website: {client.website}
Industry: {client.industry}
Description: {client.description or 'Not provided'}
City: {client.city or 'Not provided'}
State: {client.state or 'Not provided'}

Output ONLY valid JSON. No explanations. No ```json code block wrapper. Start directly with the opening brace."""
