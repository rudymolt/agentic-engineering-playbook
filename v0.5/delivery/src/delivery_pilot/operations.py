"""Observe-before-dispatch external-operation protocol."""

from __future__ import annotations

import os
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .canonical import canonical_bytes, digest, load_strict


class Provider(Protocol):
    def query(self, key: str): ...
    def dispatch(self, key: str, payload: dict[str, Any]): ...


class ReceiptStore(Protocol):
    def get(self, operation_id: str) -> dict[str, Any] | None: ...
    def persist(self, receipt: dict[str, Any]) -> None: ...


class MemoryReceiptStore:
    def __init__(self) -> None:
        self.receipts: dict[str, dict[str, Any]] = {}

    def get(self, operation_id: str) -> dict[str, Any] | None:
        value = self.receipts.get(operation_id)
        return deepcopy(value) if value else None

    def persist(self, receipt: dict[str, Any]) -> None:
        self.receipts[receipt["operation_id"]] = deepcopy(receipt)


class FileReceiptStore:
    """Atomic local receipt store used before a control checkpoint is pushed."""

    def __init__(self, directory: Path):
        self.directory = directory

    def _path(self, operation_id: str) -> Path:
        if not operation_id.startswith("op-") or not operation_id[3:].isalnum():
            raise ValueError("invalid operation ID")
        return self.directory / f"{operation_id}.json"

    def get(self, operation_id: str) -> dict[str, Any] | None:
        path = self._path(operation_id)
        return load_strict(path.read_bytes()) if path.exists() else None

    def persist(self, receipt: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self._path(receipt["operation_id"])
        fd, raw_path = tempfile.mkstemp(prefix=target.name, dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(canonical_bytes(receipt) + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(raw_path, target)
        finally:
            if os.path.exists(raw_path):
                os.unlink(raw_path)


def operation_id(mission_id: str, kind: str, target: str, payload: dict[str, Any]) -> str:
    return "op-" + digest({"mission_id": mission_id, "kind": kind, "target": target, "payload": payload}).split(":", 1)[1][:24]


class OperationCoordinator:
    def __init__(self, provider: Provider, store: ReceiptStore | None = None):
        self.provider = provider
        self.store = store or MemoryReceiptStore()

    def run(self, mission_id: str, generation: int, kind: str, target: str, payload: dict[str, Any]) -> dict[str, Any]:
        op_id = operation_id(mission_id, kind, target, payload)
        key = op_id
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        base = {
            "schema_version": 1,
            "operation_id": op_id,
            "mission_id": mission_id,
            "controller_generation": generation,
            "kind": kind,
            "target": target,
            "intent_digest": digest(payload),
            "correlation_key": key,
            "expected_prior_state": None,
            "external_ref": None,
            "observations": [],
            "attempt_count": 0,
            "terminal_evidence_digest": None,
            "issuer": "delivery-pilot/process-attested",
        }
        prior = self.store.get(op_id)
        if prior and prior.get("status") in {"observed_succeeded", "observed_failed", "cancelled"}:
            return prior
        base["status"] = "intent_committed"
        if prior:
            base["observations"] = list(prior.get("observations", []))
            base["attempt_count"] = prior.get("attempt_count", 0)
        else:
            base["observations"].append({"at": now, "status": "intent_committed"})
        # This persistence is the authority boundary. A provider call is never
        # attempted when the intent cannot be made durable first.
        self.store.persist(base)
        observed = self.provider.query(key)
        if observed:
            receipt = self._observed(base, observed, now, base["attempt_count"])
            self.store.persist(receipt)
            return receipt
        base["observations"].append({"at": now, "status": "not_found"})
        base["status"] = "dispatched"
        base["attempt_count"] += 1
        self.store.persist(base)
        try:
            response = self.provider.dispatch(key, payload)
            receipt = self._observed(base, response, now, base["attempt_count"])
            self.store.persist(receipt)
            return receipt
        except TimeoutError:
            base["status"] = "ambiguous"
            base["observations"].append({"at": now, "status": "dispatch_result_unknown"})
            self.store.persist(base)
            return base
        except Exception as exc:
            base["status"] = "observed_failed"
            base["observations"].append({"at": now, "status": "failed", "class": type(exc).__name__})
            self.store.persist(base)
            return base

    @staticmethod
    def _observed(base: dict[str, Any], observed: dict[str, Any], now: str, attempts: int) -> dict[str, Any]:
        succeeded = observed.get("status") in {"succeeded", "observed_succeeded"}
        base.update({
            "status": "observed_succeeded" if succeeded else "observed_failed",
            "external_ref": observed.get("external_ref"),
            "attempt_count": attempts,
            "terminal_evidence_digest": observed.get("evidence_digest"),
        })
        base["observations"].append({"at": now, "status": base["status"]})
        return base
