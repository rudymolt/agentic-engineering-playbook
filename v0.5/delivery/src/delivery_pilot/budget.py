"""Executable active-time and TTL accounting."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


class CeilingError(RuntimeError):
    pass


@dataclass
class ActiveTimeLedger:
    total_limit: int
    phase_limits: dict[str, int] = field(default_factory=dict)
    total_seconds: int = 0
    by_phase: dict[str, int] = field(default_factory=dict)
    charged_ids: set[str] = field(default_factory=set)
    open_intervals: dict[str, tuple[str, int]] = field(default_factory=dict)

    def start(self, interval_id: str, phase: str, monotonic_second: int) -> None:
        if interval_id in self.charged_ids or interval_id in self.open_intervals:
            return
        self.open_intervals[interval_id] = (phase, monotonic_second)

    def stop(self, interval_id: str, monotonic_second: int) -> int:
        if interval_id in self.charged_ids:
            return 0
        if interval_id not in self.open_intervals:
            return 0
        phase, started = self.open_intervals[interval_id]
        if monotonic_second < started:
            raise CeilingError("interval ended before it started")
        del self.open_intervals[interval_id]
        seconds = int(monotonic_second - started)
        self.total_seconds += seconds
        self.by_phase[phase] = self.by_phase.get(phase, 0) + seconds
        self.charged_ids.add(interval_id)
        self._check_limits(phase)
        return seconds

    def split(self, interval_id: str, new_phase: str, monotonic_second: int) -> str:
        self.stop(interval_id, monotonic_second)
        next_id = f"{interval_id}:{new_phase}:{monotonic_second}"
        self.start(next_id, new_phase, monotonic_second)
        return next_id

    def reconcile_unknown(self, interval_id: str) -> None:
        if interval_id in self.open_intervals:
            raise CeilingError(f"interval {interval_id} has no trustworthy end")

    def check_ttl(self, now: datetime, expires_at: datetime) -> None:
        if now >= expires_at:
            raise CeilingError("mission TTL expired")

    def extend(self, limit_name: str, new_seconds: int, authorized: bool) -> None:
        if not authorized:
            raise CeilingError("ceiling extension is not authorized")
        if limit_name == "active_seconds_total":
            if new_seconds <= self.total_limit:
                raise CeilingError("extension must raise the exact named limit")
            self.total_limit = new_seconds
            return
        prefix = "active_seconds_by_phase."
        if not limit_name.startswith(prefix):
            raise CeilingError("unknown ceiling extension target")
        phase = limit_name.removeprefix(prefix)
        current = self.phase_limits.get(phase, 0)
        if new_seconds <= current:
            raise CeilingError("extension must raise the exact named limit")
        self.phase_limits[phase] = new_seconds

    def to_record(self) -> dict[str, object]:
        """Return the complete durable ledger record without relaxing its limits."""
        return {
            "total_limit": self.total_limit,
            "phase_limits": dict(sorted(self.phase_limits.items())),
            "total_seconds": self.total_seconds,
            "by_phase": dict(sorted(self.by_phase.items())),
            "charged_ids": sorted(self.charged_ids),
            "open_intervals": {
                interval_id: {"phase": phase, "started": started}
                for interval_id, (phase, started) in sorted(self.open_intervals.items())
            },
        }

    @classmethod
    def from_record(cls, value: object) -> "ActiveTimeLedger":
        """Restore a ledger exactly, refusing malformed or incomplete accounting facts."""
        if not isinstance(value, dict):
            raise CeilingError("ledger record must be an object")
        required = {"total_limit", "phase_limits", "total_seconds", "by_phase", "charged_ids", "open_intervals"}
        if set(value) != required:
            raise CeilingError("ledger record has unknown or missing fields")
        if not all(isinstance(value[name], int) and not isinstance(value[name], bool) and value[name] >= 0 for name in ("total_limit", "total_seconds")):
            raise CeilingError("ledger totals must be non-negative integers")
        phase_limits = value["phase_limits"]
        by_phase = value["by_phase"]
        charged_ids = value["charged_ids"]
        open_intervals = value["open_intervals"]
        if not isinstance(phase_limits, dict) or not isinstance(by_phase, dict) or not isinstance(charged_ids, list) or not isinstance(open_intervals, dict):
            raise CeilingError("ledger collections are malformed")
        if any(not isinstance(key, str) or not isinstance(item, int) or isinstance(item, bool) or item < 0 for collection in (phase_limits, by_phase) for key, item in collection.items()):
            raise CeilingError("ledger phase accounting is malformed")
        if any(not isinstance(item, str) for item in charged_ids) or len(set(charged_ids)) != len(charged_ids):
            raise CeilingError("ledger charged interval IDs are malformed")
        restored_open: dict[str, tuple[str, int]] = {}
        for interval_id, interval in open_intervals.items():
            if not isinstance(interval_id, str) or not isinstance(interval, dict) or set(interval) != {"phase", "started"}:
                raise CeilingError("ledger open interval is malformed")
            phase, started = interval["phase"], interval["started"]
            if not isinstance(phase, str) or not isinstance(started, int) or isinstance(started, bool) or started < 0:
                raise CeilingError("ledger open interval is malformed")
            restored_open[interval_id] = (phase, started)
        if set(charged_ids) & set(restored_open):
            raise CeilingError("ledger interval cannot be open and charged")
        if sum(by_phase.values()) != value["total_seconds"]:
            raise CeilingError("ledger phase totals do not equal total seconds")
        return cls(
            total_limit=value["total_limit"], phase_limits=dict(phase_limits),
            total_seconds=value["total_seconds"], by_phase=dict(by_phase),
            charged_ids=set(charged_ids), open_intervals=restored_open,
        )

    def _check_limits(self, phase: str) -> None:
        if self.total_seconds >= self.total_limit:
            raise CeilingError("mission active-time ceiling reached")
        phase_limit = self.phase_limits.get(phase)
        if phase_limit is not None and self.by_phase[phase] >= phase_limit:
            raise CeilingError(f"{phase} active-time ceiling reached")
