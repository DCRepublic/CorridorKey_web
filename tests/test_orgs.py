"""Tests for the organization model (CRKY-4)."""

import pytest

from web.api.orgs import Org, OrgMember, OrgStore


@pytest.fixture
def org_store(tmp_path):
    """Create an OrgStore backed by a temp JSON file."""
    from web.api import database as db_mod
    from web.api import persist

    persist.init(str(tmp_path))
    # Reset singleton to ensure fresh JSONBackend
    db_mod._backend = None
    store = OrgStore()
    yield store
    db_mod._backend = None


class TestOrgCRUD:
    def test_create_org(self, org_store):
        org = org_store.create_org("Test Studio", "user-1")
        assert org.name == "Test Studio"
        assert org.owner_id == "user-1"
        assert not org.personal
        assert len(org.org_id) == 12

    def test_get_org(self, org_store):
        org = org_store.create_org("Studio A", "user-1")
        fetched = org_store.get_org(org.org_id)
        assert fetched is not None
        assert fetched.name == "Studio A"

    def test_get_nonexistent_org(self, org_store):
        assert org_store.get_org("nonexistent") is None

    def test_list_orgs(self, org_store):
        org_store.create_org("A", "user-1")
        org_store.create_org("B", "user-2")
        orgs = org_store.list_orgs()
        assert len(orgs) == 2
        names = {o.name for o in orgs}
        assert names == {"A", "B"}

    def test_delete_org(self, org_store):
        org = org_store.create_org("Doomed", "user-1")
        assert org_store.delete_org(org.org_id)
        assert org_store.get_org(org.org_id) is None

    def test_delete_nonexistent(self, org_store):
        assert not org_store.delete_org("nope")

    def test_delete_removes_memberships(self, org_store):
        org = org_store.create_org("Studio", "user-1")
        org_store.add_member(org.org_id, "user-2")
        org_store.delete_org(org.org_id)
        assert org_store.list_members(org.org_id) == []


class TestMembership:
    def test_owner_auto_added(self, org_store):
        org = org_store.create_org("Studio", "user-1")
        members = org_store.list_members(org.org_id)
        assert len(members) == 1
        assert members[0].user_id == "user-1"
        assert members[0].role == "owner"

    def test_add_member(self, org_store):
        org = org_store.create_org("Studio", "user-1")
        member = org_store.add_member(org.org_id, "user-2", role="member")
        assert member.user_id == "user-2"
        assert member.role == "member"
        assert len(org_store.list_members(org.org_id)) == 2

    def test_add_duplicate_is_noop(self, org_store):
        org = org_store.create_org("Studio", "user-1")
        org_store.add_member(org.org_id, "user-2")
        org_store.add_member(org.org_id, "user-2")  # duplicate
        members = org_store.list_members(org.org_id)
        user2_members = [m for m in members if m.user_id == "user-2"]
        assert len(user2_members) == 1

    def test_remove_member(self, org_store):
        org = org_store.create_org("Studio", "user-1")
        org_store.add_member(org.org_id, "user-2")
        assert org_store.remove_member(org.org_id, "user-2")
        assert len(org_store.list_members(org.org_id)) == 1

    def test_remove_nonexistent(self, org_store):
        org = org_store.create_org("Studio", "user-1")
        assert not org_store.remove_member(org.org_id, "ghost")

    def test_is_member(self, org_store):
        org = org_store.create_org("Studio", "user-1")
        assert org_store.is_member(org.org_id, "user-1")
        assert not org_store.is_member(org.org_id, "outsider")

    def test_is_org_admin(self, org_store):
        org = org_store.create_org("Studio", "user-1")
        org_store.add_member(org.org_id, "user-2", role="admin")
        org_store.add_member(org.org_id, "user-3", role="member")
        assert org_store.is_org_admin(org.org_id, "user-1")  # owner
        assert org_store.is_org_admin(org.org_id, "user-2")  # admin
        assert not org_store.is_org_admin(org.org_id, "user-3")  # member

    def test_update_member_role(self, org_store):
        org = org_store.create_org("Studio", "user-1")
        org_store.add_member(org.org_id, "user-2", role="member")
        updated = org_store.update_member_role(org.org_id, "user-2", "admin")
        assert updated is not None
        assert updated.role == "admin"

    def test_update_role_nonexistent(self, org_store):
        org = org_store.create_org("Studio", "user-1")
        assert org_store.update_member_role(org.org_id, "ghost", "admin") is None


class TestUserOrgs:
    def test_list_user_orgs(self, org_store):
        org_store.create_org("Studio A", "user-1")
        org2 = org_store.create_org("Studio B", "user-2")
        org_store.add_member(org2.org_id, "user-1")
        orgs = org_store.list_user_orgs("user-1")
        assert len(orgs) == 2

    def test_list_user_orgs_empty(self, org_store):
        org_store.create_org("Studio", "user-1")
        assert org_store.list_user_orgs("outsider") == []


class TestPersonalOrg:
    def test_ensure_personal_org_creates(self, org_store):
        org = org_store.ensure_personal_org("user-1", "alice@studio.com")
        assert org.personal
        assert org.owner_id == "user-1"
        assert "alice" in org.name

    def test_ensure_personal_org_idempotent(self, org_store):
        org1 = org_store.ensure_personal_org("user-1", "alice@studio.com")
        org2 = org_store.ensure_personal_org("user-1", "alice@studio.com")
        assert org1.org_id == org2.org_id

    def test_get_personal_org(self, org_store):
        org_store.ensure_personal_org("user-1", "bob@test.com")
        personal = org_store.get_personal_org("user-1")
        assert personal is not None
        assert personal.personal

    def test_personal_org_not_confused_with_regular(self, org_store):
        org_store.create_org("Regular Org", "user-1")
        assert org_store.get_personal_org("user-1") is None


class TestDataclasses:
    def test_org_to_dict(self):
        org = Org(org_id="abc", name="Test", owner_id="u1", personal=True, created_at=123.0)
        d = org.to_dict()
        assert d["org_id"] == "abc"
        assert d["personal"] is True

    def test_org_member_to_dict(self):
        m = OrgMember(user_id="u1", org_id="o1", role="admin", joined_at=456.0)
        d = m.to_dict()
        assert d["role"] == "admin"
        assert d["joined_at"] == 456.0
