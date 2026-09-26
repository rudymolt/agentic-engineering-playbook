"""One canonical G1-G9 definition for the Tier A dry-run oracle."""

from __future__ import annotations

from typing import Any


GATES = {
    "G1": "approved scope is complete and uncontradicted",
    "G2": "required deterministic checks are green",
    "G3": "final pass binds the exact frozen tuple",
    "G4": "checker freshness identity and provenance meet the tier",
    "G5": "no open taste or safety interrupt",
    "G6": "findings QA readiness and review threads have no unresolved defect",
    "G7": "remote head PR metadata target and required actions are reconciled",
    "G8": "target merge method protected paths and authority match the envelope",
}
G9_GUARDS = ("delivery_enabled", "generation_current", "expected_head", "operations_reconciled")


def evaluate_gates(facts: dict[str, bool]) -> dict[str, Any]:
    failures = [
        {"id": gate, "reason": text, "fact": bool(facts.get(gate, False))}
        for gate, text in GATES.items()
        if facts.get(gate) is not True
    ]
    return {"pass": not failures, "failures": failures, "evaluated": list(GATES)}


def simulate_g9(facts: dict[str, bool]) -> dict[str, Any]:
    failures = [guard for guard in G9_GUARDS if facts.get(guard) is not True]
    return {
        "gate": "G9",
        "would_authorize": not failures,
        "failures": failures,
        "dispatched": False,
        "mode": "non-dispatching-simulator",
    }
