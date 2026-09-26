"""Executable, separately-authorized S7 fixture entry points.

They are ordinary functions, not a Routine or background service.  Calling one
is a live host effect only after an approved disposable fixture supplies a
checkpoint, current host observations, and a ``ConductorHostAdapter``.  Keeping
these drivers in maintained source prevents the S7 plan from silently reverting
to a trial-only adapter or deterministic-only limit/repair checks.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from .interim import InterimCheckpointSnapshot, InterimCheckpointStore
from .interim_conductor_host import ConductorHostAdapter, fixture_envelope
from .interim_repair_coordinator import InterimRepairCoordinator, RepairAdapter
from .interim_watchdog import resume_and_reconcile


def selected_limit_wake_fixture(store: InterimCheckpointStore, snapshot: InterimCheckpointSnapshot,
                                title: str, coordinator_session_id: str, host_event_id: str,
                                host_observation: dict[str, Any], adapter: ConductorHostAdapter,
                                now: datetime) -> tuple[InterimCheckpointSnapshot, dict[str, Any]]:
    """Exercise a selected cap or deadline at the real watchdog admission seam."""
    return resume_and_reconcile(store, snapshot, title, coordinator_session_id, host_event_id,
                                host_observation, adapter, now)


def diagnosis_stagnation_fixture(coordinator: InterimRepairCoordinator,
                                 snapshot: InterimCheckpointSnapshot, slice_id: str, task: dict[str, Any],
                                 diagnosis: RepairAdapter, repair: RepairAdapter, verify: RepairAdapter,
                                 cycles: int = 3) -> InterimCheckpointSnapshot:
    """Run exact live diagnosis then bounded repair/Verify cycles from one ledger.

    The passed adapters are responsible for actual host calls and must preserve
    each operation's persisted UUID identities.  This driver does not reset the
    repair batch, selected limits, forecast, or accumulated charges.
    """
    if type(cycles) is not int or not 1 <= cycles <= 3:
        raise ValueError("fixture invocation must bound one to three repair cycles")
    current = snapshot
    for _ in range(cycles + 1):
        status = current.value.get("repair", {}).get("status")
        if status in {"diagnosis-required", "waiting-diagnosis"}:
            current = coordinator.diagnose(current, slice_id, task, diagnosis)
        elif status in {"repair-ready", "repair-verify-ready", "waiting-repair", "waiting-repair-verify"}:
            current = coordinator.repair_once(current, slice_id, task, repair, verify)
        else:
            break
        if current.value["repair"]["status"].startswith("waiting-"):
            # Return the durable poll frontier; an outer host wake invokes this
            # same driver later. Never spin or manufacture a terminal result.
            break
    return current


def approved_fixture_envelope(main_workspaces: int, routine_deliveries: int, named_sessions: int,
                              session_limit: int, workspace_limit: int) -> dict[str, int]:
    """Reject an S7 plan that omits one Routine-created workspace per delivery."""
    return fixture_envelope(main_workspaces=main_workspaces, routine_deliveries=routine_deliveries,
                            named_sessions=named_sessions, session_limit=session_limit,
                            workspace_limit=workspace_limit)
