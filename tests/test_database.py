"""Tests for the database abstraction layer (CRKY-9)."""

import pytest

from web.api.database import JSONBackend, StorageBackend


class TestStorageBackendInterface:
    """Verify the abstract interface raises NotImplementedError."""

    def test_get_setting_raises(self):
        with pytest.raises(NotImplementedError):
            StorageBackend().get_setting("key")

    def test_set_setting_raises(self):
        with pytest.raises(NotImplementedError):
            StorageBackend().set_setting("key", "value")

    def test_get_all_settings_raises(self):
        with pytest.raises(NotImplementedError):
            StorageBackend().get_all_settings()

    def test_get_invite_tokens_raises(self):
        with pytest.raises(NotImplementedError):
            StorageBackend().get_invite_tokens()

    def test_save_invite_token_raises(self):
        with pytest.raises(NotImplementedError):
            StorageBackend().save_invite_token("tok", {})

    def test_save_job_history_raises(self):
        with pytest.raises(NotImplementedError):
            StorageBackend().save_job_history([])

    def test_load_job_history_raises(self):
        with pytest.raises(NotImplementedError):
            StorageBackend().load_job_history()


class TestJSONBackend:
    """Test JSONBackend delegates correctly to persist module."""

    @pytest.fixture(autouse=True)
    def setup_persist(self, tmp_path):
        """Initialize persist with a temp directory."""
        from web.api import persist

        persist.init(str(tmp_path))
        yield
        # Reset state path after test
        persist._state_path = ""

    def test_get_set_setting(self):
        backend = JSONBackend()
        assert backend.get_setting("foo") is None
        assert backend.get_setting("foo", 42) == 42

        backend.set_setting("foo", "bar")
        assert backend.get_setting("foo") == "bar"

    def test_get_all_settings(self):
        backend = JSONBackend()
        backend.set_setting("a", 1)
        backend.set_setting("b", 2)
        all_settings = backend.get_all_settings()
        assert all_settings["a"] == 1
        assert all_settings["b"] == 2

    def test_invite_tokens(self):
        backend = JSONBackend()
        assert backend.get_invite_tokens() == {}

        backend.save_invite_token("tok1", {"created_at": 123, "used": False})
        tokens = backend.get_invite_tokens()
        assert "tok1" in tokens
        assert tokens["tok1"]["created_at"] == 123
        assert tokens["tok1"]["used"] is False

    def test_invite_token_update(self):
        backend = JSONBackend()
        backend.save_invite_token("tok1", {"used": False})
        backend.save_invite_token("tok1", {"used": True, "used_by": "user@test.com"})
        tokens = backend.get_invite_tokens()
        assert tokens["tok1"]["used"] is True
        assert tokens["tok1"]["used_by"] == "user@test.com"

    def test_job_history(self):
        backend = JSONBackend()
        assert backend.load_job_history() == []

        history = [{"id": "j1", "status": "completed"}, {"id": "j2", "status": "failed"}]
        backend.save_job_history(history)
        loaded = backend.load_job_history()
        assert len(loaded) == 2
        assert loaded[0]["id"] == "j1"

    def test_overwrite_setting(self):
        backend = JSONBackend()
        backend.set_setting("key", "old")
        backend.set_setting("key", "new")
        assert backend.get_setting("key") == "new"


class TestGetStorage:
    """Test the singleton factory."""

    def test_returns_json_backend_when_postgres_disabled(self, monkeypatch):
        """When CK_AUTH_ENABLED=false, should use JSONBackend."""
        import web.api.database as db_mod

        # Reset singleton
        db_mod._backend = None
        monkeypatch.setattr(db_mod, "_USE_POSTGRES", False)
        monkeypatch.setattr(db_mod, "_PG_URL", "")

        # Need persist initialized for JSONBackend
        from web.api import persist

        persist.init("/tmp")

        backend = db_mod.get_storage()
        assert isinstance(backend, JSONBackend)

        # Clean up singleton
        db_mod._backend = None

    def test_returns_json_backend_when_no_pg_url(self, monkeypatch):
        """When auth enabled but no PG URL, should fall back to JSON."""
        import web.api.database as db_mod

        db_mod._backend = None
        monkeypatch.setattr(db_mod, "_USE_POSTGRES", True)
        monkeypatch.setattr(db_mod, "_PG_URL", "")

        from web.api import persist

        persist.init("/tmp")

        backend = db_mod.get_storage()
        assert isinstance(backend, JSONBackend)

        db_mod._backend = None

    def test_singleton_returns_same_instance(self, monkeypatch):
        """get_storage() should return the same instance on repeated calls."""
        import web.api.database as db_mod

        db_mod._backend = None
        monkeypatch.setattr(db_mod, "_USE_POSTGRES", False)
        monkeypatch.setattr(db_mod, "_PG_URL", "")

        from web.api import persist

        persist.init("/tmp")

        a = db_mod.get_storage()
        b = db_mod.get_storage()
        assert a is b

        db_mod._backend = None
