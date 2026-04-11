"""Singleton dependencies for the FastAPI application."""

from __future__ import annotations

from backend.service import CorridorKeyService

from .state import JobState, NodeState, StateBackend, create_backend

_service: CorridorKeyService | None = None
_state: StateBackend | None = None


def get_service() -> CorridorKeyService:
    global _service
    if _service is None:
        _service = CorridorKeyService()
    return _service


def get_state() -> StateBackend:
    """Get the shared state backend (creates on first call based on CK_REDIS_URL)."""
    global _state
    if _state is None:
        _state = create_backend()
    return _state


def get_node_state() -> NodeState:
    """Get the node state backend."""
    return get_state().nodes


def get_queue() -> JobState:
    """Get the job state backend.

    Named get_queue() for backward compatibility with existing
    Depends(get_queue) usage in route handlers.
    """
    return get_state().jobs
