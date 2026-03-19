"""Tests for GPU credit enforcement (CRKY-37)."""

from unittest.mock import MagicMock

import pytest

from web.api.auth import UserContext


@pytest.fixture
def credit_env(tmp_path, monkeypatch):
    """Set up credit enforcement environment."""
    from web.api import database as db_mod
    from web.api import persist

    persist.init(str(tmp_path))
    db_mod._backend = None

    # Reset org store singleton
    import web.api.orgs as orgs_mod

    orgs_mod._org_store = None

    yield

    db_mod._backend = None
    orgs_mod._org_store = None


def _make_request(user: UserContext | None = None) -> MagicMock:
    request = MagicMock()
    request.state.user = user
    return request


class TestCreditGuard:
    def test_no_op_when_disabled(self, credit_env, monkeypatch):
        import web.api.credit_guard as mod

        monkeypatch.setattr(mod, "CREDIT_RATIO", 0.0)
        monkeypatch.setattr(mod, "AUTH_ENABLED", True)
        request = _make_request(UserContext(user_id="u1", tier="member"))
        # Should not raise
        mod.check_credit_balance(request)

    def test_no_op_when_auth_disabled(self, credit_env, monkeypatch):
        import web.api.credit_guard as mod

        monkeypatch.setattr(mod, "AUTH_ENABLED", False)
        request = _make_request()
        mod.check_credit_balance(request)

    def test_admin_bypasses(self, credit_env, monkeypatch):
        import web.api.credit_guard as mod

        monkeypatch.setattr(mod, "AUTH_ENABLED", True)
        monkeypatch.setattr(mod, "CREDIT_RATIO", 1.0)
        request = _make_request(UserContext(user_id="admin", tier="platform_admin"))
        mod.check_credit_balance(request)

    def test_within_grace_period(self, credit_env, monkeypatch):
        import web.api.credit_guard as mod

        monkeypatch.setattr(mod, "AUTH_ENABLED", True)
        monkeypatch.setattr(mod, "CREDIT_RATIO", 1.0)
        monkeypatch.setattr(mod, "CREDIT_GRACE", 3600)

        from web.api.orgs import get_org_store

        store = get_org_store()
        org = store.create_org("Test", "u1")

        from web.api.gpu_credits import add_consumed

        add_consumed(org.org_id, 100)  # Well within grace

        request = _make_request(UserContext(user_id="u1", tier="member"))
        mod.check_credit_balance(request)

    def test_blocks_over_ratio(self, credit_env, monkeypatch):
        import web.api.credit_guard as mod

        monkeypatch.setattr(mod, "AUTH_ENABLED", True)
        monkeypatch.setattr(mod, "CREDIT_RATIO", 1.0)
        monkeypatch.setattr(mod, "CREDIT_GRACE", 0)

        from web.api.orgs import get_org_store

        store = get_org_store()
        org = store.create_org("Test", "u1")

        from web.api.gpu_credits import add_consumed, add_contributed

        add_contributed(org.org_id, 100)
        add_consumed(org.org_id, 200)  # 2x ratio, limit is 1x

        request = _make_request(UserContext(user_id="u1", tier="member"))
        with pytest.raises(Exception) as exc_info:
            mod.check_credit_balance(request)
        assert exc_info.value.status_code == 402

    def test_allows_within_ratio(self, credit_env, monkeypatch):
        import web.api.credit_guard as mod

        monkeypatch.setattr(mod, "AUTH_ENABLED", True)
        monkeypatch.setattr(mod, "CREDIT_RATIO", 2.0)
        monkeypatch.setattr(mod, "CREDIT_GRACE", 0)

        from web.api.orgs import get_org_store

        store = get_org_store()
        org = store.create_org("Test", "u1")

        from web.api.gpu_credits import add_consumed, add_contributed

        add_contributed(org.org_id, 100)
        add_consumed(org.org_id, 150)  # 1.5x ratio, limit is 2x

        request = _make_request(UserContext(user_id="u1", tier="member"))
        mod.check_credit_balance(request)  # Should not raise

    def test_blocks_zero_contribution(self, credit_env, monkeypatch):
        import web.api.credit_guard as mod

        monkeypatch.setattr(mod, "AUTH_ENABLED", True)
        monkeypatch.setattr(mod, "CREDIT_RATIO", 1.0)
        monkeypatch.setattr(mod, "CREDIT_GRACE", 0)

        from web.api.orgs import get_org_store

        store = get_org_store()
        org = store.create_org("Test", "u1")

        from web.api.gpu_credits import add_consumed

        add_consumed(org.org_id, 100)  # Consumed with zero contribution

        request = _make_request(UserContext(user_id="u1", tier="member"))
        with pytest.raises(Exception) as exc_info:
            mod.check_credit_balance(request)
        assert exc_info.value.status_code == 402
        assert "hasn't contributed" in str(exc_info.value.detail)
