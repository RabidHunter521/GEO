import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


def _make_app():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key
    app.dependency_overrides[require_api_key] = lambda: None
    return app, get_db


def _fake_client():
    m = MagicMock()
    m.id = uuid.uuid4()
    m.name = "Acme Corp"
    m.website = "https://acme.com"
    m.industry = "Technology"
    m.description = "An AI company"
    m.target_audience = "developers"
    m.city = "Kuala Lumpur"
    m.state = "Selangor"
    m.technical_foundations_verified = False
    m.structured_data_verified = False
    m.archived_at = None
    return m


def _fake_toolkit(client_id):
    m = MagicMock()
    m.id = uuid.uuid4()
    m.client_id = client_id
    m.llms_txt = "# Acme Corp\n> tagline"
    m.schema_json = '{"@context": "https://schema.org", "@graph": []}'
    m.robots_txt = "User-agent: GPTBot\nAllow: /"
    m.generated_at = datetime(2026, 1, 1)
    m.llms_verified = False
    m.schema_verified = False
    m.robots_verified = False
    m.verified_at = None
    m.llms_full_txt = None
    m.llms_full_verified = False
    return m


def test_get_files_returns_null_when_not_generated():
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    mock_db.query.return_value.filter.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{fake_client.id}/toolkit/files")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json() is None


def test_generate_creates_new_toolkit_files():
    app, get_db = _make_app()
    fake_client = _fake_client()
    fake_tf = _fake_toolkit(fake_client.id)

    def fake_refresh(obj):
        obj.id = fake_tf.id
        obj.client_id = fake_tf.client_id
        obj.llms_txt = fake_tf.llms_txt
        obj.schema_json = fake_tf.schema_json
        obj.robots_txt = fake_tf.robots_txt
        obj.generated_at = fake_tf.generated_at
        obj.llms_verified = fake_tf.llms_verified
        obj.schema_verified = fake_tf.schema_verified
        obj.robots_verified = fake_tf.robots_verified
        obj.verified_at = fake_tf.verified_at
        obj.llms_full_txt = fake_tf.llms_full_txt
        obj.llms_full_verified = fake_tf.llms_full_verified

    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    mock_db.query.return_value.filter.return_value.first.return_value = None
    mock_db.refresh = MagicMock(side_effect=fake_refresh)
    app.dependency_overrides[get_db] = lambda: mock_db

    with patch("app.api.v1.toolkit.generate_toolkit_files") as mock_gen:
        mock_gen.return_value = {
            "llms_txt": fake_tf.llms_txt,
            "schema_json": fake_tf.schema_json,
            "robots_txt": fake_tf.robots_txt,
        }
        http = TestClient(app)
        resp = http.post(f"/api/v1/clients/{fake_client.id}/toolkit/generate")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["llms_txt"] == fake_tf.llms_txt
    assert data["schema_json"] == fake_tf.schema_json
    assert data["robots_txt"] == fake_tf.robots_txt


def test_generate_updates_existing_toolkit_files():
    app, get_db = _make_app()
    fake_client = _fake_client()
    fake_tf = _fake_toolkit(fake_client.id)
    existing = MagicMock()
    existing.id = fake_tf.id
    existing.client_id = fake_tf.client_id
    existing.llms_txt = "old content"
    existing.schema_json = "{}"
    existing.robots_txt = "old"
    existing.generated_at = datetime(2025, 1, 1)
    existing.llms_verified = True
    existing.schema_verified = True
    existing.robots_verified = True
    existing.verified_at = datetime(2025, 1, 2)
    existing.llms_full_txt = None
    existing.llms_full_verified = False

    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    mock_db.query.return_value.filter.return_value.first.return_value = existing
    app.dependency_overrides[get_db] = lambda: mock_db

    with patch("app.api.v1.toolkit.generate_toolkit_files") as mock_gen:
        mock_gen.return_value = {
            "llms_txt": "# New",
            "schema_json": '{"@context": "new"}',
            "robots_txt": "User-agent: GPTBot\nAllow: /",
        }
        http = TestClient(app)
        resp = http.post(f"/api/v1/clients/{fake_client.id}/toolkit/generate")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert existing.llms_verified is False
    assert existing.schema_verified is False
    assert existing.robots_verified is False
    assert existing.verified_at is None


def test_verify_returns_verification_results():
    app, get_db = _make_app()
    fake_client = _fake_client()
    fake_tf = _fake_toolkit(fake_client.id)
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    mock_db.query.return_value.filter.return_value.first.return_value = fake_tf
    app.dependency_overrides[get_db] = lambda: mock_db

    with patch("app.api.v1.toolkit.verify_all") as mock_verify:
        mock_verify.return_value = {
            "llms_verified": True,
            "schema_verified": True,
            "robots_verified": True,
            "llms_full_verified": False,
        }
        http = TestClient(app)
        resp = http.post(f"/api/v1/clients/{fake_client.id}/toolkit/verify")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["llms_verified"] is True
    assert data["schema_verified"] is True
    assert data["robots_verified"] is True
    assert data["technical_foundations_updated"] is True
    assert data["structured_data_updated"] is True


def test_verify_returns_404_when_no_files():
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    mock_db.query.return_value.filter.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.post(f"/api/v1/clients/{fake_client.id}/toolkit/verify")
    app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_generate_requires_auth():
    from app.main import app
    http = TestClient(app)
    resp = http.post(f"/api/v1/clients/{uuid.uuid4()}/toolkit/generate")
    assert resp.status_code == 401


def test_get_client_not_found_returns_404():
    app, get_db = _make_app()
    mock_db = MagicMock()
    mock_db.get.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{uuid.uuid4()}/toolkit/files")
    app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_generate_llms_full_updates_row():
    app, get_db = _make_app()
    fake_client = _fake_client()
    fake_tf = _fake_toolkit(fake_client.id)
    fake_tf.llms_full_txt = None
    fake_tf.llms_full_verified = False
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    mock_db.query.return_value.filter.return_value.first.return_value = fake_tf
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.toolkit.generate_llms_full_txt", return_value="# Acme — full"):
        resp = TestClient(app).post(f"/api/v1/clients/{fake_client.id}/toolkit/generate-llms-full")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert fake_tf.llms_full_txt == "# Acme — full"
    assert fake_tf.llms_full_verified is False


def test_generate_llms_full_404_without_base_files():
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    mock_db.query.return_value.filter.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    resp = TestClient(app).post(f"/api/v1/clients/{fake_client.id}/toolkit/generate-llms-full")
    app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_verify_persists_llms_full_flag_without_touching_scores():
    app, get_db = _make_app()
    fake_client = _fake_client()
    fake_tf = _fake_toolkit(fake_client.id)
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    mock_db.query.return_value.filter.return_value.first.return_value = fake_tf
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.toolkit.verify_all") as mock_verify:
        mock_verify.return_value = {
            "llms_verified": False,
            "schema_verified": False,
            "robots_verified": False,
            "llms_full_verified": True,
        }
        resp = TestClient(app).post(f"/api/v1/clients/{fake_client.id}/toolkit/verify")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["llms_full_verified"] is True
    assert fake_tf.llms_full_verified is True
    # llms-full alone must NOT flip either score dimension
    assert fake_client.technical_foundations_verified is False
    assert fake_client.structured_data_verified is False
    # llms-full alone must NOT stamp verified_at either
    assert fake_tf.verified_at is None


def test_verify_robots_without_llms_unlocks_technical_foundations():
    app, get_db = _make_app()
    fake_client = _fake_client()
    fake_tf = _fake_toolkit(fake_client.id)
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    mock_db.query.return_value.filter.return_value.first.return_value = fake_tf
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.toolkit.verify_all") as mock_verify:
        mock_verify.return_value = {
            "llms_verified": False,
            "schema_verified": False,
            "robots_verified": True,
            "llms_full_verified": False,
        }
        response = TestClient(app).post(
            f"/api/v1/clients/{fake_client.id}/toolkit/verify"
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_client.technical_foundations_verified is True
    assert fake_client.structured_data_verified is False


def test_verify_llms_without_robots_does_not_unlock_score():
    app, get_db = _make_app()
    fake_client = _fake_client()
    fake_tf = _fake_toolkit(fake_client.id)
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    mock_db.query.return_value.filter.return_value.first.return_value = fake_tf
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.toolkit.verify_all") as mock_verify:
        mock_verify.return_value = {
            "llms_verified": True,
            "schema_verified": False,
            "robots_verified": False,
            "llms_full_verified": False,
        }
        response = TestClient(app).post(
            f"/api/v1/clients/{fake_client.id}/toolkit/verify"
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_client.technical_foundations_verified is False


# ── M4: llms.txt must carry real page links ───────────────────────────────────
# The Answer.AI spec is built on link lists; the prompt emitted none, so an AI
# reading a client's llms.txt learnt what they do and had nowhere to go.

def test_llms_txt_prompt_lists_discovered_urls():
    from app.models.client import Client
    from app.prompts.toolkit import build_llms_txt
    c = Client(name="Acme Dental", website="https://acme.com", industry="Dental clinic")
    prompt = build_llms_txt(c, page_urls=["https://acme.com", "https://acme.com/services"])
    assert "## Key Pages" in prompt
    assert "https://acme.com/services" in prompt
    # The anti-hallucination instruction is the point — without it the model
    # cheerfully invents /about and /pricing.
    assert "never invent" in prompt.lower()


def test_llms_txt_prompt_omits_key_pages_when_discovery_found_nothing():
    from app.models.client import Client
    from app.prompts.toolkit import build_llms_txt
    c = Client(name="Acme Dental", website="https://acme.com", industry="Dental clinic")
    assert "## Key Pages" not in build_llms_txt(c, page_urls=[])
    assert "## Key Pages" not in build_llms_txt(c)


def test_llms_txt_generation_survives_discovery_failure():
    """A crawl failure must not block the file — it just loses the link list."""
    from unittest.mock import MagicMock, patch
    from app.models.client import Client
    from app.services import toolkit_service
    c = Client(name="Acme Dental", website="https://acme.com", industry="Dental clinic")

    resp = MagicMock()
    resp.content = [MagicMock(text="# Acme Dental")]
    resp.stop_reason = "end_turn"
    with patch("app.services.content_crawler.discover_pages", side_effect=OSError("dns")), \
         patch.object(toolkit_service, "_anthropic_client",
                      return_value=MagicMock(**{"messages.create.return_value": resp})), \
         patch.object(toolkit_service, "record_llm_call"):
        assert toolkit_service.generate_llms_txt(c) == "# Acme Dental"
