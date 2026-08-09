from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers

from app.core import rate_limit as rl


def _request(ip="1.2.3.4", xff=None):
    headers = {}
    if xff:
        headers["x-forwarded-for"] = xff
    return SimpleNamespace(headers=Headers(headers), client=SimpleNamespace(host=ip))


class _FakeRedis:
    def __init__(self):
        self.counts = {}
        self.expires = {}

    def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def expire(self, key, seconds):
        self.expires[key] = seconds


def test_allows_requests_under_limit(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(rl, "_get_redis", lambda: fake)
    dep = rl.rate_limit("view", max_requests=3, window_seconds=60)
    req = _request()
    dep(req)
    dep(req)
    dep(req)  # third is still within the limit


def test_blocks_requests_over_limit(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(rl, "_get_redis", lambda: fake)
    dep = rl.rate_limit("view", max_requests=2, window_seconds=60)
    req = _request()
    dep(req)
    dep(req)
    with pytest.raises(HTTPException) as exc:
        dep(req)
    assert exc.value.status_code == 429


def test_sets_expiry_only_on_first_request(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(rl, "_get_redis", lambda: fake)
    dep = rl.rate_limit("view", max_requests=10, window_seconds=45)
    req = _request()
    dep(req)
    dep(req)
    assert fake.expires == {"rl:view:1.2.3.4": 45}


def test_separate_budgets_per_ip(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(rl, "_get_redis", lambda: fake)
    dep = rl.rate_limit("view", max_requests=1, window_seconds=60)
    dep(_request(ip="10.0.0.1"))
    dep(_request(ip="10.0.0.2"))  # different IP, own budget — no raise


def test_trusted_proxy_keys_on_rightmost_forwarded_for(monkeypatch):
    # Behind a configured trusted proxy, the rightmost XFF entry is the one the
    # proxy appended from its own $remote_addr — the only entry a client cannot
    # forge — so that is what the limiter must key on.
    fake = _FakeRedis()
    monkeypatch.setattr(rl, "_get_redis", lambda: fake)
    monkeypatch.setattr(rl.settings, "RATE_LIMIT_TRUSTED_PROXY", "1")
    dep = rl.rate_limit("view", max_requests=5, window_seconds=60)
    dep(_request(ip="10.0.0.9", xff="203.0.113.7, 192.168.1.5"))
    assert "rl:view:192.168.1.5" in fake.counts
    assert "rl:view:203.0.113.7" not in fake.counts  # leftmost is client-forgeable


def test_untrusted_proxy_ignores_client_forwarded_for(monkeypatch):
    # With no trusted proxy configured, a client-supplied XFF must NOT influence
    # the key — otherwise an attacker rotates the header to dodge the limit.
    fake = _FakeRedis()
    monkeypatch.setattr(rl, "_get_redis", lambda: fake)
    monkeypatch.setattr(rl.settings, "RATE_LIMIT_TRUSTED_PROXY", "")
    dep = rl.rate_limit("view", max_requests=5, window_seconds=60)
    dep(_request(ip="10.0.0.9", xff="203.0.113.7, 192.168.1.5"))
    assert "rl:view:10.0.0.9" in fake.counts  # falls back to TCP connection IP
    assert "rl:view:203.0.113.7" not in fake.counts


def test_two_trusted_proxies_key_on_second_entry_from_the_right(monkeypatch):
    # Two proxies (e.g. Railway's edge + the platform router) each append the
    # address they received the connection from, so the real client is the 2nd
    # entry from the right. Keying on the rightmost would collapse every visitor
    # into one bucket — the platform's own IP.
    fake = _FakeRedis()
    monkeypatch.setattr(rl, "_get_redis", lambda: fake)
    monkeypatch.setattr(rl.settings, "RATE_LIMIT_TRUSTED_PROXY", "2")
    dep = rl.rate_limit("view", max_requests=5, window_seconds=60)
    dep(_request(ip="10.0.0.9", xff="203.0.113.7, 198.51.100.4, 192.168.1.5"))
    assert "rl:view:198.51.100.4" in fake.counts
    assert "rl:view:192.168.1.5" not in fake.counts  # that is proxy 1, not the client
    assert "rl:view:203.0.113.7" not in fake.counts  # client-forgeable


def test_shorter_chain_than_configured_hops_falls_back_to_peer(monkeypatch):
    # Fewer XFF entries than configured hops means the request did not traverse
    # the chain we were told about — every entry is then suspect, so trust the
    # TCP peer instead of picking a forgeable entry.
    fake = _FakeRedis()
    monkeypatch.setattr(rl, "_get_redis", lambda: fake)
    monkeypatch.setattr(rl.settings, "RATE_LIMIT_TRUSTED_PROXY", "2")
    dep = rl.rate_limit("view", max_requests=5, window_seconds=60)
    dep(_request(ip="10.0.0.9", xff="203.0.113.7"))
    assert "rl:view:10.0.0.9" in fake.counts
    assert "rl:view:203.0.113.7" not in fake.counts


def test_non_numeric_trusted_proxy_still_means_one_hop(monkeypatch):
    # Back-compat: the setting used to be a bare on/off flag ("any non-empty
    # value"), and existing deploys set things like "true". That must keep
    # meaning exactly one proxy hop.
    fake = _FakeRedis()
    monkeypatch.setattr(rl, "_get_redis", lambda: fake)
    monkeypatch.setattr(rl.settings, "RATE_LIMIT_TRUSTED_PROXY", "true")
    dep = rl.rate_limit("view", max_requests=5, window_seconds=60)
    dep(_request(ip="10.0.0.9", xff="203.0.113.7, 192.168.1.5"))
    assert "rl:view:192.168.1.5" in fake.counts


def test_leftmost_mode_keys_on_the_first_forwarded_for_entry(monkeypatch):
    # Railway's edge STRIPS any client-supplied X-Forwarded-For and rebuilds the
    # chain, so the leftmost entry is the real client and is not forgeable. It
    # also warns the internal hop count can vary, which is exactly why counting
    # from the right is unsafe there.
    fake = _FakeRedis()
    monkeypatch.setattr(rl, "_get_redis", lambda: fake)
    monkeypatch.setattr(rl.settings, "RATE_LIMIT_TRUSTED_PROXY", "leftmost")
    dep = rl.rate_limit("view", max_requests=5, window_seconds=60)
    dep(_request(ip="10.0.0.9", xff="203.0.113.7, 198.51.100.4, 192.168.1.5"))
    assert "rl:view:203.0.113.7" in fake.counts
    assert "rl:view:192.168.1.5" not in fake.counts


def test_leftmost_mode_survives_a_changing_internal_hop_count(monkeypatch):
    # The whole point of leftmost mode: two requests that traversed a different
    # number of internal hops must still key on the same client.
    fake = _FakeRedis()
    monkeypatch.setattr(rl, "_get_redis", lambda: fake)
    monkeypatch.setattr(rl.settings, "RATE_LIMIT_TRUSTED_PROXY", "leftmost")
    dep = rl.rate_limit("view", max_requests=5, window_seconds=60)
    dep(_request(ip="10.0.0.9", xff="203.0.113.7, 192.168.1.5"))
    dep(_request(ip="10.0.0.9", xff="203.0.113.7, 198.51.100.4, 192.168.1.5"))
    assert fake.counts["rl:view:203.0.113.7"] == 2


def test_leftmost_mode_falls_back_to_peer_without_forwarded_for(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(rl, "_get_redis", lambda: fake)
    monkeypatch.setattr(rl.settings, "RATE_LIMIT_TRUSTED_PROXY", "leftmost")
    dep = rl.rate_limit("view", max_requests=5, window_seconds=60)
    dep(_request(ip="10.0.0.9"))
    assert "rl:view:10.0.0.9" in fake.counts


def test_fails_open_when_redis_unavailable(monkeypatch):
    class _Broken:
        def incr(self, key):
            raise ConnectionError("redis down")

    monkeypatch.setattr(rl, "_get_redis", lambda: _Broken())
    dep = rl.rate_limit("view", max_requests=1, window_seconds=60)
    # Must not raise even though the store is unreachable.
    dep(_request())
    dep(_request())
