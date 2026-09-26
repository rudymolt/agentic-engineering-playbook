"""Deterministic /whats-next mission discovery and mirror reconciliation."""

from __future__ import annotations

from typing import Any

from .contracts import ContractError


ORDER = (
    "local_locator",
    "protected_registry",
    "labelled_prs",
    "finalization_intents",
    "control_refs",
)


def _items(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _mission_id(source: str, item: Any) -> str | None:
    if isinstance(item, dict):
        return item.get("mission_id")
    if source == "control_refs" and isinstance(item, str) and "/delivery-control/" in item:
        return item.rsplit("/", 1)[-1]
    return None


def discover_mission(sources: dict[str, Any]) -> dict[str, Any]:
    seen: dict[str, list[tuple[str, Any]]] = {}
    for source in ORDER:
        for item in _items(sources.get(source)):
            mission_id = _mission_id(source, item)
            if mission_id:
                seen.setdefault(mission_id, []).append((source, item))
    if not seen:
        return {"outcome": "none", "source": None, "mission_id": None}
    if len(seen) != 1:
        raise ContractError(f"mission discovery mirrors disagree: {sorted(seen)}")
    mission_id, entries = next(iter(seen.items()))
    refs = {
        item.get("control_ref")
        for _, item in entries
        if isinstance(item, dict) and item.get("control_ref")
    }
    if len(refs) > 1:
        raise ContractError("mission discovery control refs disagree")
    for source in ORDER:
        matched = [item for entry_source, item in entries if entry_source == source]
        if matched:
            return {
                "outcome": "found",
                "source": source,
                "mission_id": mission_id,
                "control_ref": next(iter(refs), f"refs/heads/delivery-control/{mission_id}"),
                "record": matched[0],
            }
    raise AssertionError("unreachable")
