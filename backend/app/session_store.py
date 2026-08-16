"""Per-session conversation state, kept in-process memory.

Prototype-scoped on purpose: state is lost on restart and doesn't scale past
one backend replica. Swap this for a shared store (e.g. Redis, keyed by
session_id) before running more than one backend instance in production —
see README "Configuration"/"Deployment" for the note on this.
"""
from typing import Any


class InMemorySessionStore:
    def __init__(self):
        self._sessions: dict[str, list[dict[str, Any]]] = {}

    def get_history(self, session_id: str) -> list[dict[str, Any]]:
        return self._sessions.setdefault(session_id, [])

    def save_history(self, session_id: str, history: list[dict[str, Any]]) -> None:
        self._sessions[session_id] = history

    def reset(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
