"""Admin endpoints — user management, approval workflow (CRKY-2, CRKY-20).

All endpoints require platform_admin tier. Provides user listing,
tier management (approve/reject), and user deletion.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..auth import TIER_HIERARCHY, UserContext, get_current_user
from ..orgs import get_org_store
from ..tier_guard import require_admin
from ..users import get_user_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class SetTierRequest(BaseModel):
    tier: str


def _get_admin(request: Request) -> UserContext:
    """Extract admin user from request state."""
    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


# --- User management ---


@router.get("/users")
def list_users(tier: str | None = None):
    """List all users, optionally filtered by tier. Includes org memberships."""
    store = get_user_store()
    org_store = get_org_store()
    users = store.list_users(tier_filter=tier)
    enriched = []
    for u in users:
        data = u.to_dict()
        user_orgs = org_store.list_user_orgs(u.user_id)
        data["orgs"] = [{"org_id": o.org_id, "name": o.name} for o in user_orgs]
        enriched.append(data)
    return {"users": enriched}


@router.get("/users/pending")
def list_pending_users():
    """List users awaiting approval."""
    store = get_user_store()
    pending = store.list_users(tier_filter="pending")
    return {"users": [u.to_dict() for u in pending]}


@router.post("/users/{user_id}/approve")
def approve_user(user_id: str, request: Request):
    """Approve a pending user — sets tier to 'member' and creates personal org."""
    admin = _get_admin(request)
    user_store = get_user_store()
    user = user_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.tier != "pending":
        raise HTTPException(status_code=400, detail=f"User is already {user.tier}, not pending")

    # Set tier to member
    updated = user_store.set_tier(user_id, "member", approved_by=admin.user_id)

    # Create personal org for the newly approved user
    org_store = get_org_store()
    org_store.ensure_personal_org(user_id, user.email)

    return {"status": "approved", "user": updated.to_dict() if updated else None}


@router.post("/users/{user_id}/reject")
def reject_user(user_id: str, request: Request):
    """Reject a pending user — marks as rejected."""
    admin = _get_admin(request)
    user_store = get_user_store()
    user = user_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.tier != "pending":
        raise HTTPException(status_code=400, detail=f"User is already {user.tier}, not pending")

    updated = user_store.set_tier(user_id, "rejected", approved_by=admin.user_id)
    return {"status": "rejected", "user": updated.to_dict() if updated else None}


@router.post("/users/{user_id}/tier")
def set_user_tier(user_id: str, req: SetTierRequest, request: Request):
    """Set a user's trust tier directly. Platform admin only."""
    _get_admin(request)
    valid_tiers = set(TIER_HIERARCHY)
    if req.tier not in valid_tiers:
        raise HTTPException(status_code=400, detail=f"Invalid tier. Must be one of: {', '.join(TIER_HIERARCHY)}")

    user_store = get_user_store()
    user = user_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    updated = user_store.set_tier(user_id, req.tier)
    return {"status": "updated", "user": updated.to_dict() if updated else None}


@router.delete("/users/{user_id}")
def delete_user(user_id: str):
    """Delete a user record. Does not delete the Supabase auth account."""
    user_store = get_user_store()
    if not user_store.delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "deleted"}


# --- Org listing (admin view) ---


@router.get("/orgs")
def list_all_orgs():
    """List all organizations. Platform admin only."""
    org_store = get_org_store()
    orgs = org_store.list_orgs()
    result = []
    for org in orgs:
        members = org_store.list_members(org.org_id)
        result.append({**org.to_dict(), "member_count": len(members)})
    return {"orgs": result}
