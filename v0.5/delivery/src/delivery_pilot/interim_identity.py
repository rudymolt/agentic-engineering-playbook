"""Host-compatible identities for the interim coordinator.

Logical operation identifiers are deliberately compact, but Conductor's session
and message creation flags accept UUIDs.  Derive UUIDv5 values from immutable
operation purpose *before* an effect is dispatched, then require the host to
echo those exact values.  This supplies stable reconciliation without passing
provider-invalid ``build-op-…`` placeholders to the host.
"""
from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5


def host_uuid(run_id: str, operation_id: str, kind: str) -> str:
    """Return a stable UUID accepted by Conductor for one durable identity."""
    return str(uuid5(NAMESPACE_URL, f"ai-engineering-playbook/interim/v1/{run_id}/{operation_id}/{kind}"))


def operation_identities(run_id: str, operation_id: str, phase: str, coordinator_session_id: str | None = None) -> dict[str, str]:
    """Return the host identities saved in an intent before its host call."""
    return {
        "session_id": coordinator_session_id if phase in {"coordinator", "wake"} and coordinator_session_id else host_uuid(run_id, operation_id, "session"),
        "message_id": host_uuid(run_id, operation_id, "message"),
        # Conductor echoes the supplied message UUID as ``content.turnId``.
        # It does not create a separately assignable turn identity.
        "terminal_turn_id": host_uuid(run_id, operation_id, "message"),
    }
