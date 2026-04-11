"""Tests for the JWT authentication middleware."""

import time

import jwt
import pytest

from web.api.auth import (
    UserContext,
    _decode_jwt,
)

# Test JWT secret for testing only
TEST_SECRET = "test_secret_key_at_least_32_characters_long"


def _make_token(claims: dict, secret: str = TEST_SECRET, exp_delta: int = 3600) -> str:
    """Create a test JWT."""
    payload = {
        "sub": claims.get("sub", "test-user-id"),
        "email": claims.get("email", "test@example.com"),
        "aud": "authenticated",
        "exp": int(time.time()) + exp_delta,
        "iat": int(time.time()),
        "user_metadata": claims.get("user_metadata", {}),
        "app_metadata": claims.get("app_metadata", {}),
        **{k: v for k, v in claims.items() if k not in ("sub", "email", "user_metadata", "app_metadata")},
    }
    return jwt.encode(payload, secret, algorithm="HS256")


class TestUserContext:
    def test_tier_checks(self):
        admin = UserContext(user_id="1", tier="platform_admin")
        assert admin.is_admin
        assert admin.is_contributor
        assert admin.is_member

        member = UserContext(user_id="2", tier="member")
        assert not member.is_admin
        assert not member.is_contributor
        assert member.is_member

        pending = UserContext(user_id="3", tier="pending")
        assert not pending.is_admin
        assert not pending.is_contributor
        assert not pending.is_member

        contributor = UserContext(user_id="4", tier="contributor")
        assert not contributor.is_admin
        assert contributor.is_contributor
        assert contributor.is_member

    def test_default_values(self):
        user = UserContext(user_id="test")
        assert user.tier == "pending"
        assert user.email == ""
        assert user.org_ids == []
        assert user.raw_claims == {}


class TestDecodeJWT:
    def test_valid_token(self, monkeypatch):
        monkeypatch.setattr("web.api.auth.JWT_SECRET", TEST_SECRET)
        token = _make_token({"sub": "user-123", "email": "test@example.com"})
        claims = _decode_jwt(token)
        assert claims["sub"] == "user-123"
        assert claims["email"] == "test@example.com"

    def test_expired_token(self, monkeypatch):
        monkeypatch.setattr("web.api.auth.JWT_SECRET", TEST_SECRET)
        token = _make_token({"sub": "user-123"}, exp_delta=-3600)
        with pytest.raises(Exception, match="Token expired"):
            _decode_jwt(token)

    def test_wrong_secret(self, monkeypatch):
        monkeypatch.setattr("web.api.auth.JWT_SECRET", TEST_SECRET)
        token = _make_token({"sub": "user-123"}, secret="wrong_secret_that_is_long_enough_32")
        with pytest.raises(Exception, match="Invalid token"):
            _decode_jwt(token)

    def test_wrong_audience(self, monkeypatch):
        monkeypatch.setattr("web.api.auth.JWT_SECRET", TEST_SECRET)
        payload = {
            "sub": "user-123",
            "aud": "wrong_audience",
            "exp": int(time.time()) + 3600,
        }
        token = jwt.encode(payload, TEST_SECRET, algorithm="HS256")
        with pytest.raises(Exception, match="Invalid token"):
            _decode_jwt(token)

    def test_extracts_app_metadata(self, monkeypatch):
        monkeypatch.setattr("web.api.auth.JWT_SECRET", TEST_SECRET)
        token = _make_token(
            {
                "sub": "user-456",
                "app_metadata": {"tier": "contributor", "org_ids": ["org-1", "org-2"]},
            }
        )
        claims = _decode_jwt(token)
        assert claims["app_metadata"]["tier"] == "contributor"
        assert claims["app_metadata"]["org_ids"] == ["org-1", "org-2"]
