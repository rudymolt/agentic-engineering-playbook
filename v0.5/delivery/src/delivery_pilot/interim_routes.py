"""One route resolver for durable worker intent, host dispatch, and acceptance."""
from __future__ import annotations

from typing import Any


def route_name(operation: dict[str, Any]) -> str:
    if "escalated_verify" in operation:
        return "escalated_verify"
    if "escalated_slot" in operation:
        return "escalation"
    phase = operation["phase"]
    if phase == "diagnosis":
        return "diagnosis"
    if phase in {"repair", "build"}:
        return "build"
    if phase in {"repair-verify", "verify", "stack-verify", "stack-final-qa", "stack-final-ci", "stack-final-review"}:
        return "verify"
    return phase


def route_for_operation(approval: dict[str, Any], operation: dict[str, Any]) -> dict[str, str]:
    name = route_name(operation)
    source = ({"model": "gpt-6-sol", "effort": "high"} if name == "escalated_verify" else
              approval["escalation_policy"]["route"] if name == "escalation" else approval["routes"][name])
    return {key: source[key] for key in ("model", "effort")}


def configured_route(routes: dict[str, Any], operation: dict[str, Any]) -> dict[str, str]:
    name = route_name(operation)
    source = {"model": "gpt-6-sol", "effort": "high"} if name == "escalated_verify" else routes[name]
    return {key: source[key] for key in ("model", "effort")}
