"""ADMIN_API_KEY is the only control on every endpoint that can spend money,
so production must refuse to boot on a guessable one."""
import secrets

import pytest

from app.core.config import Settings

_BASE = dict(
    DATABASE_URL="postgresql://x/y",
    ADMIN_API_KEY=secrets.token_hex(32),
    ANTHROPIC_API_KEY="k",
    RESEND_API_KEY="k",
)


def _settings(**over):
    return Settings(**{**_BASE, **over})


def test_strong_key_boots_in_production():
    assert _settings(ENVIRONMENT="production").ADMIN_API_KEY


@pytest.mark.parametrize("env", ["development", "staging", ""])
def test_short_key_allowed_outside_production(env):
    # The committed .env uses a short throwaway key and every API test
    # authenticates with it — enforcing length here would break local dev + CI.
    assert _settings(ENVIRONMENT=env, ADMIN_API_KEY="short-dev-key").ADMIN_API_KEY


@pytest.mark.parametrize("key", ["", "   "])
def test_empty_key_rejected_in_every_environment(key):
    # require_api_key uses hmac.compare_digest: an empty configured key would
    # make an empty bearer token a valid credential.
    with pytest.raises(ValueError, match="must not be empty"):
        _settings(ADMIN_API_KEY=key)


def test_short_key_rejected_in_production():
    with pytest.raises(ValueError, match="at least 32 characters"):
        _settings(ENVIRONMENT="production", ADMIN_API_KEY="tooshort")


def test_padded_placeholder_rejected_in_production():
    # Long enough to clear the length bar, still not a secret.
    with pytest.raises(ValueError, match="placeholder"):
        _settings(ENVIRONMENT="production",
                  ADMIN_API_KEY="changeme-prod-key-0000000000000000")


@pytest.mark.parametrize("key", ["a" * 64, "abcabc" * 11])
def test_low_entropy_key_rejected_in_production(key):
    with pytest.raises(ValueError, match="distinct characters"):
        _settings(ENVIRONMENT="production", ADMIN_API_KEY=key)


def test_production_match_is_case_and_whitespace_insensitive():
    with pytest.raises(ValueError, match="at least 32 characters"):
        _settings(ENVIRONMENT="  PRODUCTION  ", ADMIN_API_KEY="tooshort")
