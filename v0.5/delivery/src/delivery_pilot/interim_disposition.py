"""Durable, typed observation retries and human decision notices."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .canonical import digest

CADENCE = timedelta(minutes=15)
OBSERVATION_CATEGORIES = {"transient-outage", "ambiguous-missing-session", "unconfirmed-cancellation",
                          "uncertain-effect", "authority-denied", "credentials-revoked", "missing-session"}
STOP_CATEGORIES = {"hitl-slice", "outside-authority", "selected-limit", "repair-stuck", "whole-run-stop"}
CATEGORIES = OBSERVATION_CATEGORIES | STOP_CATEGORIES
SAFETY = {"unconfirmed-cancellation", "uncertain-effect"}
IMMEDIATE = {"authority-denied", "credentials-revoked", "missing-session"}
IMMEDIATE_REPORTS = {
    "authority-denied": (
        "The host denied authority for the approved exact operation.",
        "Resolve the denied authority through the approved owner before explicitly resuming.",
        "Restore the approved authority and explicitly resume"),
    "credentials-revoked": (
        "The host confirmed that credentials for the approved exact operation were revoked.",
        "Have the authorized account owner restore credentials before explicitly resuming.",
        "Restore credentials through the authorized owner and explicitly resume"),
    "missing-session": (
        "The approved exact worker session is definitively missing.",
        "Choose an authorized recovery plan for the missing exact session.",
        "Provide an authorized plan for the missing exact session"),
}


def decision_reason(category: str) -> str:
    if category in IMMEDIATE_REPORTS:
        return IMMEDIATE_REPORTS[category][0]
    if category in SAFETY:
        return "The exact cancellation or effect remained uncertain after three eligible backup cycles."
    return "The exact host observation remained unavailable after three eligible backup cycles."


class ObservationFailure(OSError):
    """A classification from a structured host status, never provider prose."""

    def __init__(self, category: str, retry_after: datetime | None = None):
        if category not in OBSERVATION_CATEGORIES:
            raise ValueError("unknown observation failure category")
        super().__init__(category)
        self.category, self.retry_after = category, retry_after


def _at(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def eligible(record: dict[str, Any], now: datetime) -> bool:
    active = record.get("recovery_disposition", {}).get("active")
    return not active or now >= datetime.fromisoformat(active["next_check_at"].replace("Z", "+00:00"))


def clear(record: dict[str, Any]) -> None:
    if "recovery_disposition" in record:
        record["recovery_disposition"]["active"] = None


def notice_stop(record: dict[str, Any], cause: str, happened: str) -> None:
    """Retain one complete decision report on the existing checkpoint surface."""
    if cause not in CATEGORIES:
        raise ValueError("unknown human stop cause")
    state = record.setdefault("recovery_disposition", {"active": None, "notices": []})
    operation_id = record["state"].get("operation_id") or record["approval"]["coordinator"]["session_id"]
    epoch = record.get("monitoring", {}).get("epoch", 0)
    identity = "notice-" + digest({"run": record["approval"]["run_id"], "epoch": epoch,
                                    "operation": operation_id, "cause": cause})[7:23]
    if any(item["id"] == identity for item in state["notices"]):
        return
    completed = [item["id"] for item in record["usage"]["operations"] if item["status"] in {"result", "reconciled", "accounted"}]
    remaining = [item["id"] for item in record["usage"]["operations"] if item["status"] not in {"result", "reconciled", "accounted", "unfinished-cancelled"}]
    if not remaining:
        remaining = [operation_id]
    options = (["Review the completed slice and authorize continuation", "Stop this run"] if cause == "hitl-slice"
               else ["Provide a scoped decision and explicitly resume", "Stop this run"])
    state["notices"].append({"id": identity, "epoch": epoch, "operation_id": operation_id,
                             "cause": cause, "happened": happened, "completed": completed,
                             "remains": remaining, "decision": "Choose the next authorized action for this run",
                             "options": options})


def unresolved(record: dict[str, Any], category: str, operation_id: str, now: datetime,
               retry_after: datetime | None = None) -> bool:
    """Spend at most one backup cycle; return true at a decision boundary."""
    if category not in OBSERVATION_CATEGORIES or not operation_id:
        raise ValueError("recovery observation category or operation is malformed")
    state = record.setdefault("recovery_disposition", {"active": None, "notices": []})
    active = state["active"]
    if active and active["operation_id"] == operation_id and not eligible(record, now):
        return False
    count = active["count"] + 1 if active and active["operation_id"] == operation_id else 1
    next_time = max(now + CADENCE, retry_after) if retry_after else now + CADENCE
    state["active"] = {"category": category, "operation_id": operation_id,
                       "count": count, "next_check_at": _at(next_time)}
    if count < 3 and category not in IMMEDIATE:
        return False
    cause = "safety-uncertainty" if category in SAFETY else "authority-decision" if category in IMMEDIATE else "recovery-stuck"
    epoch = record.get("monitoring", {}).get("epoch", 0)
    identity = "notice-" + digest({"run": record["approval"]["run_id"], "epoch": epoch,
                                    "operation": operation_id, "cause": cause})[7:23]
    if not any(item["id"] == identity for item in state["notices"]):
        completed = [item["id"] for item in record["usage"]["operations"] if item["status"] in {"result", "reconciled", "accounted"}]
        happened, decision, options = (IMMEDIATE_REPORTS[category][0], IMMEDIATE_REPORTS[category][1],
                                       [IMMEDIATE_REPORTS[category][2], "Stop this run"]) if category in IMMEDIATE else (
                                           category + " persisted for " + str(count) + " observation cycles",
                                           "Choose how to resolve the blocked operation before resuming",
                                           ["Resolve the host or effect and explicitly resume", "Stop this run"])
        state["notices"].append({"id": identity, "epoch": epoch, "operation_id": operation_id,
                                 "cause": category, "happened": happened,
                                 "completed": completed, "remains": [operation_id],
                                 "decision": decision, "options": options})
    return True


def validate_disposition(record: dict[str, Any]) -> None:
    value = record.get("recovery_disposition")
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {"active", "notices"} or not isinstance(value["notices"], list):
        raise ValueError("recovery disposition is malformed")
    operations = {item["id"] for item in record["usage"]["operations"]} | {record["approval"]["coordinator"]["session_id"]}
    active = value["active"]
    if active is not None:
        if (not isinstance(active, dict) or set(active) != {"category", "operation_id", "count", "next_check_at"}
                or active["category"] not in OBSERVATION_CATEGORIES or active["operation_id"] not in operations
                or type(active["count"]) is not int or active["count"] < 1):
            raise ValueError("active recovery disposition is malformed")
        _check_time(active["next_check_at"])
    seen = set()
    for notice in value["notices"]:
        required = {"id", "epoch", "operation_id", "cause", "happened", "completed", "remains", "decision", "options"}
        if (not isinstance(notice, dict) or set(notice) != required or notice["id"] in seen
                or notice["operation_id"] not in operations or notice["cause"] not in CATEGORIES
                or type(notice["epoch"]) is not int or notice["epoch"] < 0
                or not isinstance(notice["completed"], list) or not isinstance(notice["remains"], list)
                or not isinstance(notice["options"], list) or not notice["options"]
                or any(not isinstance(notice[key], str) or not notice[key] for key in ("id", "happened", "decision"))):
            raise ValueError("recovery decision notice is malformed")
        seen.add(notice["id"])


def _check_time(value: object) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("recovery next check time is malformed")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("recovery next check time is not UTC")
