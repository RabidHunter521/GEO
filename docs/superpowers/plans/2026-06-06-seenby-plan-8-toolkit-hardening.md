# Toolkit Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the AI Readiness Toolkit (llms.txt / schema.json / robots.txt generator) production-safe for real clients.

**Architecture:** Four surgical fixes — (1) strip Claude's code fences from schema.json output and validate the JSON before storing, (2) run the two Claude API calls in parallel to halve generation time, (3) pass the client's website into the frontend so verification instructions show the actual live URL, (4) add unit tests for the generation service to prevent regressions.

**Tech Stack:** Python 3.12, FastAPI, Anthropic SDK (claude-haiku-4-5), concurrent.futures.ThreadPoolExecutor, pytest, Next.js 15, TypeScript

---

## Files Changed

| File | Change |
|---|---|
| `backend/app/services/toolkit_service.py` | Add `_strip_code_fences`, validate JSON, parallelize calls |
| `backend/tests/test_toolkit_service.py` | New — unit tests for generation service |
| `frontend/src/app/clients/[id]/toolkit/page.tsx` | Also fetch client and pass `clientWebsite` |
| `frontend/src/app/clients/[id]/toolkit/ToolkitClient.tsx` | Accept `clientWebsite` prop, compute full URL |

---

## Task 1: Strip code fences and validate JSON in `generate_schema_json`

**Problem:** Claude Haiku sometimes wraps its JSON output in ` ```json ... ``` ` code fences despite the prompt instruction. If stored as-is, the client downloads an invalid JSON file and gets confused when trying to implement it. The verification crawler's `r.json()` call would also fail.

**Files:**
- Modify: `backend/app/services/toolkit_service.py`

- [ ] **Step 1: Write the failing test first (in a new test file)**

Create `backend/tests/test_toolkit_service.py`:

```python
# backend/tests/test_toolkit_service.py
import json
from unittest.mock import MagicMock, patch
from app.services.toolkit_service import _strip_code_fences, generate_schema_json


def test_strip_code_fences_removes_json_fence():
    raw = '```json\n{"@context": "https://schema.org"}\n```'
    assert _strip_code_fences(raw) == '{"@context": "https://schema.org"}'


def test_strip_code_fences_removes_plain_fence():
    raw = '```\n{"key": "val"}\n```'
    assert _strip_code_fences(raw) == '{"key": "val"}'


def test_strip_code_fences_is_noop_on_clean_json():
    raw = '{"@context": "https://schema.org"}'
    assert _strip_code_fences(raw) == raw


def _mock_client(json_text: str):
    """Return a mock Anthropic client whose messages.create returns json_text."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json_text)]
    mock_ac = MagicMock()
    mock_ac.messages.create.return_value = mock_msg
    return mock_ac


def _fake_client():
    """Minimal Client model substitute."""
    c = MagicMock()
    c.name = "Acme Corp"
    c.website = "https://acme.com"
    c.industry = "Technology"
    c.description = "An AI company"
    c.city = "Kuala Lumpur"
    c.state = "Selangor"
    return c


def test_generate_schema_json_strips_code_fences_and_validates():
    valid_json = '{"@context": "https://schema.org", "@graph": []}'
    fenced = f'```json\n{valid_json}\n```'

    with patch("app.services.toolkit_service._anthropic_client", return_value=_mock_client(fenced)):
        result = generate_schema_json(_fake_client())

    parsed = json.loads(result)
    assert parsed["@context"] == "https://schema.org"


def test_generate_schema_json_retries_on_invalid_json():
    invalid = "```json\nthis is not json\n```"
    valid_json = '{"@context": "https://schema.org"}'

    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        msg = MagicMock()
        msg.content = [MagicMock(text=invalid if call_count == 1 else valid_json)]
        return msg

    mock_ac = MagicMock()
    mock_ac.messages.create.side_effect = side_effect

    with patch("app.services.toolkit_service._anthropic_client", return_value=mock_ac):
        result = generate_schema_json(_fake_client())

    assert call_count == 2
    assert json.loads(result)["@context"] == "https://schema.org"


def test_generate_schema_json_raises_after_two_invalid_attempts():
    import pytest
    invalid = "not json at all"

    with patch("app.services.toolkit_service._anthropic_client", return_value=_mock_client(invalid)):
        with pytest.raises(ValueError, match="invalid JSON"):
            generate_schema_json(_fake_client())
```

- [ ] **Step 2: Run the test to verify it fails (functions don't exist yet)**

```bash
cd backend && python -m pytest tests/test_toolkit_service.py -v
```

Expected: `ImportError` or `AttributeError` — `_strip_code_fences` not found.

- [ ] **Step 3: Add `_strip_code_fences` and update `generate_schema_json` in `toolkit_service.py`**

Replace the entire `backend/app/services/toolkit_service.py` with:

```python
# backend/app/services/toolkit_service.py
import json
import re
from concurrent.futures import ThreadPoolExecutor

import anthropic
from app.core.config import settings
from app.models.client import Client

_MODEL = "claude-haiku-4-5-20251001"


def _anthropic_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def _strip_code_fences(text: str) -> str:
    """Remove ```json or ``` code fences Claude sometimes adds despite instructions."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def generate_llms_txt(client: Client) -> str:
    response = _anthropic_client().messages.create(
        model=_MODEL,
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": f"""Generate an llms.txt file for this business.
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

Output ONLY the raw llms.txt content. No explanations. No code block wrappers.""",
            }
        ],
    )
    return response.content[0].text.strip()


def generate_schema_json(client: Client) -> str:
    prompt = f"""Generate a JSON-LD structured data file for this business.
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

    for attempt in range(2):
        response = _anthropic_client().messages.create(
            model=_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = _strip_code_fences(response.content[0].text)
        try:
            json.loads(raw)
            return raw
        except json.JSONDecodeError:
            if attempt == 1:
                raise ValueError(
                    f"Claude returned invalid JSON after 2 attempts for client {client.id}"
                )

    raise ValueError("Should not reach here")  # pragma: no cover


def generate_robots_txt(client: Client) -> str:
    return f"""# AI Search Bot Access — generated by SeenBy
# Add these lines to your existing robots.txt file at {client.website}/robots.txt
# If you don't have a robots.txt yet, this file is ready to use as-is.

User-agent: *
Allow: /

User-agent: GPTBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: Google-Extended
Allow: /"""


def generate_toolkit_files(client: Client) -> dict[str, str]:
    with ThreadPoolExecutor(max_workers=2) as executor:
        llms_future = executor.submit(generate_llms_txt, client)
        schema_future = executor.submit(generate_schema_json, client)
        robots = generate_robots_txt(client)
        return {
            "llms_txt": llms_future.result(),
            "schema_json": schema_future.result(),
            "robots_txt": robots,
        }
```

- [ ] **Step 4: Run the tests**

```bash
cd backend && python -m pytest tests/test_toolkit_service.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Run the existing verification crawler tests to make sure nothing broke**

```bash
cd backend && python -m pytest tests/test_verification_crawler.py -v
```

Expected: All 11 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/toolkit_service.py backend/tests/test_toolkit_service.py
git commit -m "fix: strip code fences and validate JSON in generate_schema_json, parallelize toolkit generation"
```

---

## Task 2: Show full domain URL in ToolkitClient verification instructions

**Problem:** The "Expected URL" shown in each file's instructions reads `/llms.txt` instead of `https://yourdomain.com/llms.txt`. Clients have to mentally combine their domain with the path — a small but unnecessary friction point when onboarding.

**Files:**
- Modify: `frontend/src/app/clients/[id]/toolkit/page.tsx`
- Modify: `frontend/src/app/clients/[id]/toolkit/ToolkitClient.tsx`

- [ ] **Step 1: Update `page.tsx` to also fetch the client**

Replace the contents of `frontend/src/app/clients/[id]/toolkit/page.tsx`:

```tsx
import { getToolkitFiles, getClient } from "@/lib/api"
import { ToolkitClient } from "./ToolkitClient"

interface Props {
  params: Promise<{ id: string }>
}

export default async function ToolkitPage({ params }: Props) {
  const { id } = await params
  let files = null
  let clientWebsite = ""
  try {
    const [fetchedFiles, client] = await Promise.all([
      getToolkitFiles(id),
      getClient(id),
    ])
    files = fetchedFiles
    clientWebsite = client.website
  } catch {
    // Backend down or client not found — show empty state
  }
  return <ToolkitClient clientId={id} initialFiles={files} clientWebsite={clientWebsite} />
}
```

- [ ] **Step 2: Update `ToolkitClient.tsx` to accept `clientWebsite` and show full URLs**

In `frontend/src/app/clients/[id]/toolkit/ToolkitClient.tsx`:

a) Add `clientWebsite: string` to the `Props` interface (line 8):

```tsx
interface Props {
  clientId: string
  initialFiles: ToolkitFiles | null
  clientWebsite: string
}
```

b) Add a `fullUrl` helper just below the `FILE_KEYS` declaration and update the component signature:

```tsx
export function ToolkitClient({ clientId, initialFiles, clientWebsite }: Props) {
```

c) Add a helper to compute the full URL from the client's website:

```tsx
  function fullUrl(path: string): string {
    if (!clientWebsite) return path
    const base = clientWebsite.startsWith("http") ? clientWebsite : `https://${clientWebsite}`
    return base.replace(/\/$/, "") + path
  }
```

d) Replace the "Expected URL" display (the `<code>` block in the instructions panel) — change:

```tsx
                    {FILE_META[key].expectedUrl}
```

to:

```tsx
                    {fullUrl(FILE_META[key].expectedUrl)}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/clients/[id]/toolkit/page.tsx frontend/src/app/clients/[id]/toolkit/ToolkitClient.tsx
git commit -m "feat: show full domain URL in toolkit verification instructions"
```

---

## Self-Review

**Spec coverage:**
- Strip code fences from schema_json output → Task 1 ✓
- Validate JSON before storing → Task 1 ✓
- Retry once on invalid JSON → Task 1 ✓
- Parallelize Claude calls (speed) → Task 1 (generate_toolkit_files) ✓
- Show full verification URL → Task 2 ✓
- Tests for toolkit_service → Task 1 (test file) ✓
- Existing crawler tests still pass → Task 1 step 5 ✓

**Placeholder scan:** None.

**Type consistency:**
- `_strip_code_fences(text: str) -> str` defined in Task 1 step 3, used in same file ✓
- `clientWebsite: string` prop defined and consumed in same task ✓
- `fullUrl(path: string): string` defined and used within ToolkitClient ✓
