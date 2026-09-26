from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACK / "src"))

from delivery_pilot.continuation import (  # noqa: E402
    ContinuationError,
    initial_state,
    load_state,
    next_action,
    reduce,
    serialize_state,
    validate_state,
)
from delivery_pilot.budget import ActiveTimeLedger, CeilingError  # noqa: E402


def envelope() -> dict:
    return {
        "schema_version": 1,
        "human_authorization": {
            "source_event_id": "human-event-1", "validated": True,
            "original_intent_id": "intent-1",
        },
        "run_id": "run-1",
        "feature": "bounded-unattended-continuation",
        "maximum_action": "review-ready",
        "spec_digest": "sha256:" + "a" * 64,
        "slices_digest": "sha256:" + "b" * 64,
        "targets": ["workspace-1"],
        "sender_ids": ["builder-1", "verify-1"],
        "approved_afk_slices": ["TASK-394"],
        "build_route": "gpt-5.6-terra/high",
        "verify_route": "gpt-5.6-sol/medium",
        "allowed_paths_digest": "sha256:" + "c" * 64,
        "deadline": 1000,
        "limits": {
            "dispatch_max": 3, "retry_max": 3, "failure_max": 3,
            "no_progress_max": 3, "active_seconds_max": 100,
            "verification_reserve_seconds": 20,
        },
        "initial_epoch": 7,
        "protected_boundary": "boundary-1",
        "stop_channel": "operator-stop-1",
    }


def admit(now: int = 10, **changes: object) -> dict:
    value = {
        "type": "admit", "now": now, "sender_id": "builder-1",
        "target": "workspace-1", "payload_digest": "sha256:" + "d" * 64,
        "task": "TASK-394", "slice": "TASK-394", "candidate": "base-1",
        "action": "review-ready", "attempt": 1, "original_generation": 1,
    }
    value.update(changes)
    return value


class ContinuationReducerTests(unittest.TestCase):
    def observed(self, state: dict) -> dict:
        return reduce(state, {"type": "observe", "now": 1, "facts_complete": True})

    def test_admission_is_bound_and_requires_observer_first(self) -> None:
        state = initial_state(envelope())
        with self.assertRaisesRegex(ContinuationError, "observer"):
            reduce(state, admit())
        state = self.observed(state)
        state = reduce(state, admit())
        operation = next(iter(state["operations"].values()))
        self.assertEqual(operation["epoch"], 7)
        self.assertEqual(operation["target"], "workspace-1")
        self.assertEqual(operation["status"], "admitted")
        self.assertTrue(operation["receipt_id"].startswith("receipt-"))
        state = self.observed(state)
        with self.assertRaisesRegex(ContinuationError, "mutable builder"):
            reduce(state, admit(sender_id="verify-1", task="verify"))

    def test_stop_serializes_with_admission_and_freezes_unsent(self) -> None:
        state = reduce(self.observed(initial_state(envelope())), admit())
        state = reduce(state, {"type": "stop_run", "now": 11, "persistence_confirmed": True, "evidence_digest": "sha256:" + "0" * 64, "authentication": {
            "validated": True, "source_event_id": "human-stop-1", "channel": "operator-stop-1",
        }})
        operation = next(iter(state["operations"].values()))
        self.assertEqual(state["status"], "stopping")
        self.assertEqual(state["epoch"], 8)
        self.assertEqual(operation["status"], "discarded")
        self.assertEqual(state["senders"]["builder-1"]["status"], "frozen")
        with self.assertRaises(ContinuationError):
            reduce(state, admit())

    def test_inflight_survives_stop_but_ambiguous_never_resumes(self) -> None:
        state = reduce(self.observed(initial_state(envelope())), admit())
        operation_id = next(iter(state["operations"]))
        state = reduce(state, {"type": "dispatch_started", "now": 11, "operation_id": operation_id})
        state = reduce(state, {"type": "stop_run", "now": 12, "persistence_confirmed": True, "evidence_digest": "sha256:" + "0" * 64, "authentication": {
            "validated": True, "source_event_id": "human-stop-1", "channel": "operator-stop-1",
        }})
        self.assertEqual(state["operations"][operation_id]["status"], "in_flight")
        state = reduce(state, {"type": "observe", "now": 13, "facts_complete": False,
                               "operation_id": operation_id, "transport": "unknown", "evidence_digest": "sha256:" + "0" * 64})
        self.assertEqual(state["status"], "intervention_required")
        with self.assertRaises(ContinuationError):
            reduce(state, admit())

    def test_stop_not_confirmed_and_current_turn_stop_are_distinct(self) -> None:
        state = self.observed(initial_state(envelope()))
        current_turn = reduce(state, {"type": "stop_current_turn", "now": 2})
        self.assertEqual(current_turn["status"], "active")
        self.assertEqual(current_turn["epoch"], 7)
        unknown = reduce(state, {"type": "stop_run", "now": 2, "persistence_confirmed": False, "evidence_digest": "sha256:" + "0" * 64,
                                 "authentication": {"validated": True, "source_event_id": "s", "channel": "operator-stop-1"}})
        self.assertEqual(unknown["status"], "stop_not_confirmed")
        self.assertEqual(unknown["epoch"], 7)

    def test_durable_budget_replay_cannot_reset_or_extend(self) -> None:
        state = self.observed(initial_state(envelope()))
        state = reduce(state, {"type": "interval_start", "now": 10, "interval_id": "i1", "phase": "build"})
        state = reduce(state, {"type": "interval_stop", "now": 70, "interval_id": "i1"})
        replay = load_state(serialize_state(state))
        self.assertEqual(replay["ledger"]["total_seconds"], 60)
        self.assertEqual(replay["ledger"]["charged_ids"], ["i1"])
        with self.assertRaisesRegex(ContinuationError, "deadline"):
            reduce(replay, admit(now=1000))
        with self.assertRaises(ContinuationError):
            load_state(json.dumps({"schema_version": 1, "ledger": {}}))

    def test_terminal_stop_requires_all_senders_operations_and_effects_fenced(self) -> None:
        state = reduce(self.observed(initial_state(envelope())), admit())
        state = reduce(state, {"type": "dispatch_started", "now": 11, "operation_id": next(iter(state["operations"]))})
        state = reduce(state, {"type": "stop_run", "now": 12, "persistence_confirmed": True, "evidence_digest": "sha256:" + "0" * 64, "authentication": {
            "validated": True, "source_event_id": "human-stop-1", "channel": "operator-stop-1",
        }})
        with self.assertRaisesRegex(ContinuationError, "sender.*evidence"):
            reduce(state, {"type": "confirm_stopped", "now": 13, "evidence_digest": "sha256:" + "0" * 64})
        operation_id = next(iter(state["operations"]))
        state = reduce(state, {"type": "observe", "now": 13, "facts_complete": True,
                               "operation_id": operation_id, "transport": "accepted",
                               "completion": "failed", "known_effects": "fenced", "evidence_digest": "sha256:" + "0" * 64})
        for sender in ("builder-1", "verify-1"):
            state = reduce(state, {"type": "fence_sender", "now": 13, "sender_id": sender,
                                   "status": "fenced", "evidence_digest": "sha256:" + "f" * 64})
        state = reduce(state, {"type": "native_cancellation", "now": 14, "status": "fenced", "evidence_digest": "sha256:" + "0" * 64})
        state = reduce(state, {"type": "confirm_stopped", "now": 14, "evidence_digest": "sha256:" + "0" * 64})
        self.assertEqual(state["status"], "stopped")

    def test_malformed_unbound_and_revoked_public_inputs_fail_closed(self) -> None:
        with self.assertRaises(ContinuationError):
            initial_state({})
        state = self.observed(initial_state(envelope()))
        for event in (admit(target="other"), admit(payload_digest="not-a-digest"), {"type": "admit"}):
            with self.subTest(event=event), self.assertRaises(ContinuationError):
                reduce(state, event)
        stopped = reduce(state, {"type": "stop_run", "now": 2, "persistence_confirmed": True, "evidence_digest": "sha256:" + "0" * 64, "authentication": {
            "validated": True, "source_event_id": "human-stop-1", "channel": "operator-stop-1",
        }})
        with self.assertRaises(ContinuationError):
            reduce(stopped, {"type": "resume", "now": 3})

    def test_maximum_action_and_explicit_afk_slice_membership_are_bound(self) -> None:
        state = self.observed(initial_state(envelope()))
        with self.assertRaisesRegex(ContinuationError, "approved AFK"):
            reduce(state, admit(slice="unapproved-slice"))
        with self.assertRaisesRegex(ContinuationError, "maximum action"):
            reduce(state, admit(action="open-pr"))

    def test_counter_replay_and_four_part_result_evidence_are_non_resettable(self) -> None:
        state = self.observed(initial_state(envelope()))
        state = reduce(state, {"type": "account", "now": 2, "retries": 1, "failures": 1, "no_progress": 1, "evidence_digest": "sha256:" + "0" * 64})
        replay = load_state(serialize_state(state))
        self.assertEqual(replay["counters"], {"dispatches": 0, "retries": 1, "failures": 1, "no_progress": 1})
        state = reduce(replay, admit())
        operation_id = next(iter(state["operations"]))
        state = reduce(state, {"type": "result", "now": 11, "operation_id": operation_id,
                               "transport": "accepted", "completion": "succeeded", "verification": "failed",
                               "known_effects": "fenced", "evidence_digest": "sha256:" + "e" * 64})
        result = state["results"][-1]
        self.assertEqual(set(result), {"operation_id", "transport", "completion", "verification", "known_effects", "evidence_digest"})
        with self.assertRaises(ContinuationError):
            reduce(state, {"type": "result", "now": 12, "operation_id": operation_id,
                           "transport": "accepted", "completion": "succeeded", "verification": "failed",
                           "known_effects": "fenced"})

    def test_receipt_cannot_dispatch_or_start_use_at_deadline(self) -> None:
        state = reduce(self.observed(initial_state(envelope())), admit())
        operation_id = next(iter(state["operations"]))
        with self.assertRaisesRegex(ContinuationError, "deadline"):
            reduce(state, {"type": "dispatch_started", "now": 1000, "operation_id": operation_id})
        with self.assertRaisesRegex(ContinuationError, "deadline"):
            reduce(state, {"type": "interval_start", "now": 1001, "interval_id": "late", "phase": "build"})

    def test_receipt_cannot_extend_a_later_retry_or_unknown_interval_limit(self) -> None:
        state = reduce(self.observed(initial_state(envelope())), admit())
        operation_id = next(iter(state["operations"]))
        exhausted = reduce(state, {"type": "account", "now": 11, "retries": 3, "failures": 0, "no_progress": 0, "evidence_digest": "sha256:" + "0" * 64})
        with self.assertRaisesRegex(ContinuationError, "dispatch lacks|not active"):
            reduce(exhausted, {"type": "dispatch_started", "now": 12, "operation_id": operation_id})
        state = reduce(state, {"type": "interval_start", "now": 11, "interval_id": "open", "phase": "build"})
        with self.assertRaisesRegex(ContinuationError, "charged interval"):
            reduce(state, {"type": "dispatch_started", "now": 12, "operation_id": operation_id})

    def test_ceiling_charge_persists_and_stopping_can_close_existing_interval(self) -> None:
        short = envelope()
        short["limits"] = {**short["limits"], "active_seconds_max": 21, "verification_reserve_seconds": 1}
        state = self.observed(initial_state(short))
        state = reduce(state, {"type": "interval_start", "now": 1, "interval_id": "charged", "phase": "build"})
        state = reduce(state, {"type": "interval_stop", "now": 22, "interval_id": "charged", "evidence_digest": "sha256:" + "0" * 64})
        self.assertEqual(state["ledger"]["total_seconds"], 21)
        self.assertEqual(state["status"], "blocked")
        self.assertEqual(set(state["ceiling_report"]), {"activity", "progress", "ceiling", "next_action"})

        state = self.observed(initial_state(envelope()))
        state = reduce(state, {"type": "interval_start", "now": 1, "interval_id": "inflight", "phase": "build"})
        state = reduce(state, {"type": "stop_run", "now": 2, "persistence_confirmed": True, "evidence_digest": "sha256:" + "0" * 64, "authentication": {
            "validated": True, "source_event_id": "human-stop-1", "channel": "operator-stop-1",
        }})
        state = reduce(state, {"type": "interval_stop", "now": 3, "interval_id": "inflight"})
        self.assertEqual(state["ledger"]["total_seconds"], 2)

    def test_stop_requires_persistence_and_explicit_sender_fencing_evidence(self) -> None:
        state = self.observed(initial_state(envelope()))
        unknown = reduce(state, {"type": "stop_run", "now": 2, "evidence_digest": "sha256:" + "0" * 64, "authentication": {
            "validated": True, "source_event_id": "human-stop-1", "channel": "operator-stop-1",
        }})
        self.assertEqual(unknown["status"], "stop_not_confirmed")

        state = reduce(unknown, {"type": "stop_run", "now": 2, "persistence_confirmed": True, "evidence_digest": "sha256:" + "0" * 64,
                               "authentication": {"validated": True, "source_event_id": "human-stop-1", "channel": "operator-stop-1"}})
        with self.assertRaisesRegex(ContinuationError, "sender.*evidence"):
            reduce(state, {"type": "confirm_stopped", "now": 3, "evidence_digest": "sha256:" + "0" * 64})
        for sender in ("builder-1", "verify-1"):
            state = reduce(state, {"type": "fence_sender", "now": 3, "sender_id": sender,
                                   "status": "fenced", "evidence_digest": "sha256:" + "f" * 64})
        state = reduce(state, {"type": "native_cancellation", "now": 4, "status": "fenced", "evidence_digest": "sha256:" + "0" * 64})
        state = reduce(state, {"type": "confirm_stopped", "now": 4, "evidence_digest": "sha256:" + "0" * 64})
        self.assertEqual(state["status"], "stopped")

    def test_checkpoint_is_durable_and_next_action_stays_conservative(self) -> None:
        state = self.observed(initial_state(envelope()))
        state = reduce(state, {"type": "interval_start", "now": 2, "interval_id": "quantum", "phase": "build"})
        state = reduce(state, {"type": "interval_stop", "now": 3, "interval_id": "quantum"})
        state = reduce(state, {"type": "checkpoint", "now": 3, "checkpoint_id": "checkpoint-1",
                               "outcome": "incomplete", "operation_id": None, "evidence_digest": "sha256:" + "1" * 64})
        replay = load_state(serialize_state(state))
        self.assertEqual(replay["checkpoint"]["checkpoint_id"], "checkpoint-1")
        self.assertEqual(next_action(replay, 4), {"action": "admit", "reason": "approved run remains active"})
        replay = reduce(replay, admit(now=4))
        operation_id = next(iter(replay["operations"]))
        replay = reduce(replay, {"type": "result", "now": 5, "operation_id": operation_id, "transport": "accepted", "completion": "succeeded", "verification": "succeeded", "known_effects": "succeeded", "evidence_digest": "sha256:" + "7" * 64})
        complete = reduce(replay, {"type": "checkpoint", "now": 6, "checkpoint_id": "checkpoint-2",
                                   "outcome": "verified", "operation_id": operation_id, "evidence_digest": "sha256:" + "7" * 64})
        self.assertEqual(next_action(complete, 5), {"action": "handback", "reason": "checkpoint is verified"})

    def test_optional_tool_and_token_counters_need_null_reasons_or_monotonic_evidence(self) -> None:
        state = initial_state(envelope())
        self.assertEqual(state["optional_counters"]["tool_calls"], {"value": None, "reason": "unavailable authoritative tool count"})
        state = reduce(state, {"type": "optional_counter", "now": 1, "name": "tokens", "value": None,
                               "reason": "host does not expose token use", "evidence_digest": "sha256:" + "2" * 64})
        state = reduce(state, {"type": "optional_counter", "now": 2, "name": "tool_calls", "value": 4,
                               "reason": None, "evidence_digest": "sha256:" + "3" * 64})
        self.assertEqual(load_state(serialize_state(state))["optional_counters"]["tool_calls"]["value"], 4)
        with self.assertRaisesRegex(ContinuationError, "decrease"):
            reduce(state, {"type": "optional_counter", "now": 3, "name": "tool_calls", "value": 3,
                           "reason": None, "evidence_digest": "sha256:" + "4" * 64})

    def test_generation_recovery_reuses_immutable_intent_and_receipt(self) -> None:
        state = reduce(self.observed(initial_state(envelope())), admit())
        operation_id = next(iter(state["operations"]))
        receipt_id = state["operations"][operation_id]["receipt_id"]
        state = self.observed(load_state(serialize_state(state)))
        state = reduce(state, {"type": "recover", "now": 11, "operation_id": operation_id,
                               "controller_generation": 9, "evidence_digest": "sha256:" + "5" * 64})
        self.assertEqual(state["recovery"], {"controller_generation": 9, "operation_id": operation_id})
        self.assertEqual(state["operations"][operation_id]["receipt_id"], receipt_id)
        self.assertEqual(len(state["operations"]), 1)

    def test_reloaded_state_refuses_epoch_status_closure_and_receipt_contradictions(self) -> None:
        invalid = initial_state(envelope())
        invalid["admission_closed"] = True
        with self.assertRaisesRegex(ContinuationError, "active state"):
            validate_state(invalid)
        invalid = initial_state(envelope())
        invalid["status"] = "stopped"
        invalid["admission_closed"] = True
        invalid["epoch"] = 8
        with self.assertRaisesRegex(ContinuationError, "closed admission|stopped state"):
            validate_state(invalid)
        invalid = initial_state(envelope())
        invalid["outcomes"] = [{"outcome": "complete", "status": "blocked", "evidence_digest": "sha256:" + "8" * 64}]
        with self.assertRaisesRegex(ContinuationError, "outcome status"):
            validate_state(invalid)
        state = reduce(self.observed(initial_state(envelope())), admit())
        operation_id = next(iter(state["operations"]))
        state["operations"][operation_id]["receipt_id"] = "receipt-mismatch"
        with self.assertRaisesRegex(ContinuationError, "immutable receipt"):
            validate_state(state)

    def test_explicit_outcome_evidence_records_truthful_refusal(self) -> None:
        state = self.observed(initial_state(envelope()))
        state = reduce(state, {"type": "outcome", "now": 2, "outcome": "intervention_required",
                               "evidence_digest": "sha256:" + "6" * 64})
        self.assertEqual(state["outcomes"][-1], {"outcome": "intervention_required", "status": "intervention_required", "evidence_digest": "sha256:" + "6" * 64})
        self.assertEqual(next_action(load_state(serialize_state(state)), 3), {"action": "refuse", "reason": "run is intervention_required"})

    def test_recovery_refuses_deadline_exhaustion_and_revoked_state(self) -> None:
        state = reduce(self.observed(initial_state(envelope())), admit())
        operation_id = next(iter(state["operations"]))
        state = self.observed(state)
        with self.assertRaisesRegex(ContinuationError, "deadline"):
            reduce(state, {"type": "recover", "now": 1000, "operation_id": operation_id,
                           "controller_generation": 2, "evidence_digest": "sha256:" + "9" * 64})
        exhausted = reduce(state, {"type": "account", "now": 2, "retries": 3, "failures": 0, "no_progress": 0, "evidence_digest": "sha256:" + "0" * 64})
        with self.assertRaisesRegex(ContinuationError, "recovery requires|not active"):
            reduce(exhausted, {"type": "recover", "now": 3, "operation_id": operation_id,
                               "controller_generation": 2, "evidence_digest": "sha256:" + "9" * 64})
        revoked = reduce(state, {"type": "stop_run", "now": 2, "persistence_confirmed": True, "evidence_digest": "sha256:" + "0" * 64,
                                 "authentication": {"validated": True, "source_event_id": "stop", "channel": "operator-stop-1"}})
        with self.assertRaisesRegex(ContinuationError, "active"):
            reduce(revoked, {"type": "recover", "now": 3, "operation_id": operation_id,
                             "controller_generation": 2, "evidence_digest": "sha256:" + "9" * 64})

    def test_blocked_complete_or_verified_checkpoint_refuses_admission_and_dispatch(self) -> None:
        for outcome in ("blocked", "complete", "verified"):
            with self.subTest(outcome=outcome):
                state = self.observed(initial_state(envelope()))
                operation_id = None
                if outcome in {"complete", "verified"}:
                    state = reduce(state, admit())
                    operation_id = next(iter(state["operations"]))
                    state = reduce(state, {"type": "result", "now": 2, "operation_id": operation_id,
                                           "transport": "accepted", "completion": "succeeded",
                                           "verification": "succeeded" if outcome == "verified" else "not_run",
                                           "known_effects": "succeeded", "evidence_digest": "sha256:" + "a" * 64})
                state = reduce(state, {"type": "checkpoint", "now": 2, "checkpoint_id": f"checkpoint-{outcome}",
                                       "outcome": outcome, "operation_id": operation_id, "evidence_digest": "sha256:" + "a" * 64})
                with self.assertRaisesRegex(ContinuationError, "checkpoint"):
                    reduce(state, admit())
                admitted_before_checkpoint = reduce(self.observed(initial_state(envelope())), admit())
                operation_id = next(iter(admitted_before_checkpoint["operations"]))
                if outcome in {"complete", "verified"}:
                    admitted_before_checkpoint = reduce(admitted_before_checkpoint, {"type": "result", "now": 2, "operation_id": operation_id,
                                                                                       "transport": "accepted", "completion": "succeeded",
                                                                                       "verification": "succeeded" if outcome == "verified" else "not_run",
                                                                                       "known_effects": "succeeded", "evidence_digest": "sha256:" + "b" * 64})
                checkpointed = reduce(admitted_before_checkpoint, {"type": "checkpoint", "now": 2,
                                                                      "checkpoint_id": f"prior-{outcome}", "outcome": outcome,
                                                                      "operation_id": operation_id if outcome in {"complete", "verified"} else None,
                                                                      "evidence_digest": "sha256:" + "b" * 64})
                with self.assertRaises(ContinuationError):
                    reduce(checkpointed, {"type": "dispatch_started", "now": 3, "operation_id": operation_id})

    def test_reloaded_cross_record_builder_contradictions_fail_closed(self) -> None:
        state = reduce(self.observed(initial_state(envelope())), admit())
        operation_id = next(iter(state["operations"]))
        state = reduce(state, {"type": "dispatch_started", "now": 11, "operation_id": operation_id})
        state["senders"]["builder-1"]["status"] = "terminal"
        with self.assertRaisesRegex(ContinuationError, "sender.*unresolved"):
            load_state(json.dumps(state))

    def test_terminal_operation_statuses_require_coherent_terminal_evidence(self) -> None:
        state = reduce(self.observed(initial_state(envelope())), admit())
        operation_id = next(iter(state["operations"]))
        state = reduce(state, {
            "type": "observe", "now": 5, "facts_complete": True,
            "operation_id": operation_id, "transport": "accepted",
            "completion": "pending", "verification": "not_run",
            "known_effects": "pending", "evidence_digest": "sha256:" + "a" * 64,
        })
        for status in ("completed", "failed", "discarded", "cancelled", "fenced"):
            with self.subTest(status=status):
                contradictory = json.loads(serialize_state(state))
                contradictory["operations"][operation_id]["status"] = status
                contradictory["senders"]["builder-1"]["status"] = "terminal"
                for public_check in (validate_state, serialize_state, load_state):
                    with self.subTest(check=public_check.__name__), self.assertRaisesRegex(
                        ContinuationError, "operation.*terminal|terminal operation"
                    ):
                        if public_check is load_state:
                            public_check(json.dumps(contradictory))
                        else:
                            public_check(contradictory)
                with self.assertRaisesRegex(ContinuationError, "operation.*terminal|terminal operation"):
                    next_action(contradictory, 6)

        succeeded = reduce(self.observed(initial_state(envelope())), admit())
        succeeded_id = next(iter(succeeded["operations"]))
        succeeded = reduce(succeeded, {
            "type": "result", "now": 6, "operation_id": succeeded_id,
            "transport": "accepted", "completion": "succeeded",
            "verification": "not_run", "known_effects": "succeeded",
            "evidence_digest": "sha256:" + "b" * 64,
        })
        self.assertEqual(load_state(serialize_state(succeeded))["operations"][succeeded_id]["status"], "completed")

        stopping = reduce(self.observed(initial_state(envelope())), admit())
        stopping_id = next(iter(stopping["operations"]))
        stopping = reduce(stopping, {
            "type": "stop_run", "now": 6, "persistence_confirmed": True,
            "evidence_digest": "sha256:" + "c" * 64,
            "authentication": {"validated": True, "source_event_id": "stop-terminal",
                               "channel": "operator-stop-1"},
        })
        self.assertEqual(load_state(serialize_state(stopping))["operations"][stopping_id]["status"], "discarded")

        ambiguous = reduce(self.observed(initial_state(envelope())), admit())
        ambiguous_id = next(iter(ambiguous["operations"]))
        ambiguous = reduce(ambiguous, {
            "type": "result", "now": 6, "operation_id": ambiguous_id,
            "transport": "accepted", "completion": "pending",
            "verification": "not_run", "known_effects": "unknown",
            "evidence_digest": "sha256:" + "e" * 64,
        })
        self.assertEqual(load_state(serialize_state(ambiguous))["operations"][ambiguous_id]["status"], "ambiguous")

    def test_discard_and_fence_require_stop_bound_operation_evidence(self) -> None:
        active = reduce(self.observed(initial_state(envelope())), admit())
        active_id = next(iter(active["operations"]))
        for status, effects in (("discarded", "not_run"), ("cancelled", "fenced"), ("fenced", "fenced")):
            with self.subTest(active_status=status):
                edited = json.loads(serialize_state(active))
                edited["operations"][active_id].update({"status": status, "known_effects": effects})
                edited["senders"]["builder-1"]["status"] = "terminal"
                for public_check in (validate_state, serialize_state, load_state, next_action):
                    with self.subTest(check=public_check.__name__), self.assertRaisesRegex(ContinuationError, "Stop|operation.*evidence"):
                        if public_check is load_state:
                            public_check(json.dumps(edited))
                        elif public_check is next_action:
                            public_check(edited, 6)
                        else:
                            public_check(edited)

        for native_status, expected_operation_status in (("fenced", "fenced"), ("cancelled", "cancelled")):
            with self.subTest(native_status=native_status):
                state = reduce(self.observed(initial_state(envelope())), admit())
                operation_id = next(iter(state["operations"]))
                state = reduce(state, {"type": "dispatch_started", "now": 6, "operation_id": operation_id})
                state = reduce(state, {
                    "type": "stop_run", "now": 7, "persistence_confirmed": True,
                    "evidence_digest": "sha256:" + "b" * 64,
                    "authentication": {"validated": True, "source_event_id": "stop-bound",
                                       "channel": "operator-stop-1"},
                })
                edited = json.loads(serialize_state(state))
                edited["operations"][operation_id].update({"status": "fenced", "known_effects": "fenced"})
                with self.assertRaisesRegex(ContinuationError, "operation.*evidence"):
                    load_state(json.dumps(edited))
                state = reduce(state, {
                    "type": "result", "now": 8, "operation_id": operation_id,
                    "transport": "accepted", "completion": "pending", "verification": "not_run",
                    "known_effects": "fenced", "evidence_digest": "sha256:" + "c" * 64,
                })
                self.assertEqual(state["operations"][operation_id]["status"], "fenced")
                for sender_id in ("builder-1", "verify-1"):
                    state = reduce(state, {"type": "fence_sender", "now": 9, "sender_id": sender_id,
                                           "status": "fenced", "evidence_digest": "sha256:" + "d" * 64})
                state = reduce(state, {"type": "native_cancellation", "now": 10,
                                       "status": native_status, "evidence_digest": "sha256:" + "e" * 64})
                self.assertEqual(state["operations"][operation_id]["status"], expected_operation_status)
                stopped = reduce(state, {"type": "confirm_stopped", "now": 11,
                                         "evidence_digest": "sha256:" + "f" * 64})
                self.assertEqual(load_state(serialize_state(stopped))["status"], "stopped")

    def test_result_history_rejects_duplicates_and_observation_preserves_new_evidence(self) -> None:
        state = reduce(self.observed(initial_state(envelope())), admit())
        operation_id = next(iter(state["operations"]))
        completed_observation = {
            "type": "observe", "now": 2, "facts_complete": True,
            "operation_id": operation_id, "transport": "accepted",
            "completion": "succeeded", "verification": "not_run",
            "known_effects": "succeeded", "evidence_digest": "sha256:" + "a" * 64,
        }
        state = reduce(state, completed_observation)
        duplicate = json.loads(serialize_state(state))
        duplicate["results"].append(duplicate["results"][0].copy())
        for public_check in (validate_state, serialize_state, load_state, next_action):
            with self.subTest(duplicate_completion_check=public_check.__name__), self.assertRaisesRegex(
                ContinuationError, "result history repeats identical evidence"
            ):
                if public_check is load_state:
                    public_check(json.dumps(duplicate))
                elif public_check is next_action:
                    public_check(duplicate, 3)
                else:
                    public_check(duplicate)

        repeated = reduce(state, completed_observation)
        self.assertEqual(repeated["results"], state["results"])
        distinct = reduce(repeated, {**completed_observation, "now": 3,
                                    "evidence_digest": "sha256:" + "b" * 64})
        self.assertEqual(len(distinct["results"]), 2)
        self.assertEqual(distinct["results"][-1]["evidence_digest"], "sha256:" + "b" * 64)

        progressing = reduce(self.observed(initial_state(envelope())), admit())
        progressing_id = next(iter(progressing["operations"]))
        progressing = reduce(progressing, {
            "type": "observe", "now": 2, "facts_complete": True,
            "operation_id": progressing_id, "transport": "accepted",
            "completion": "succeeded", "verification": "pending",
            "known_effects": "succeeded", "evidence_digest": "sha256:" + "c" * 64,
        })
        progressing = reduce(progressing, {
            "type": "observe", "now": 3, "facts_complete": True,
            "operation_id": progressing_id, "transport": "accepted",
            "completion": "succeeded", "verification": "succeeded",
            "known_effects": "succeeded", "evidence_digest": "sha256:" + "d" * 64,
        })
        self.assertEqual(len(progressing["results"]), 2)
        self.assertEqual(progressing["results"][-1]["verification"], "succeeded")

    def test_stop_bound_fenced_result_history_rejects_duplicate_evidence(self) -> None:
        state = reduce(self.observed(initial_state(envelope())), admit())
        operation_id = next(iter(state["operations"]))
        state = reduce(state, {"type": "dispatch_started", "now": 2, "operation_id": operation_id})
        state = reduce(state, {
            "type": "stop_run", "now": 3, "persistence_confirmed": True,
            "evidence_digest": "sha256:" + "a" * 64,
            "authentication": {"validated": True, "source_event_id": "duplicate-fence-stop",
                               "channel": "operator-stop-1"},
        })
        fenced_observation = {
            "type": "observe", "now": 4, "facts_complete": True,
            "operation_id": operation_id, "transport": "accepted",
            "completion": "pending", "verification": "not_run",
            "known_effects": "fenced", "evidence_digest": "sha256:" + "b" * 64,
        }
        state = reduce(state, fenced_observation)
        for sender_id in ("builder-1", "verify-1"):
            state = reduce(state, {"type": "fence_sender", "now": 5, "sender_id": sender_id,
                                   "status": "fenced", "evidence_digest": "sha256:" + "c" * 64})
        state = reduce(state, {"type": "native_cancellation", "now": 6, "status": "fenced",
                               "evidence_digest": "sha256:" + "d" * 64})
        stopped = reduce(state, {"type": "confirm_stopped", "now": 7,
                                 "evidence_digest": "sha256:" + "e" * 64})
        duplicate = json.loads(serialize_state(stopped))
        duplicate["results"].append(duplicate["results"][0].copy())
        for public_check in (validate_state, serialize_state, load_state, next_action):
            with self.subTest(duplicate_fence_check=public_check.__name__), self.assertRaisesRegex(
                ContinuationError, "result history repeats identical evidence"
            ):
                if public_check is load_state:
                    public_check(json.dumps(duplicate))
                elif public_check is next_action:
                    public_check(duplicate, 8)
                else:
                    public_check(duplicate)

    def test_backward_interval_stop_refuses_without_losing_the_open_interval(self) -> None:
        state = self.observed(initial_state(envelope()))
        state = reduce(state, {"type": "interval_start", "now": 10,
                               "interval_id": "backward-clock", "phase": "build"})
        before = load_state(serialize_state(state))
        with self.assertRaisesRegex(ContinuationError, "ended before"):
            reduce(state, {"type": "interval_stop", "now": 9,
                           "interval_id": "backward-clock", "evidence_digest": "sha256:" + "a" * 64})
        self.assertEqual(load_state(serialize_state(state)), before)
        closed = reduce(state, {"type": "interval_stop", "now": 11,
                                "interval_id": "backward-clock", "evidence_digest": "sha256:" + "b" * 64})
        replay = load_state(serialize_state(closed))
        self.assertEqual((replay["ledger"]["open_intervals"], replay["ledger"]["charged_ids"], replay["ledger"]["total_seconds"]),
                         ({}, ["backward-clock"], 1))

    def test_terminal_outcomes_require_matching_concrete_result_and_checkpoint(self) -> None:
        state = reduce(self.observed(initial_state(envelope())), admit())
        operation_id = next(iter(state["operations"]))
        with self.assertRaisesRegex(ContinuationError, "terminal outcome"):
            reduce(state, {"type": "outcome", "now": 2, "outcome": "complete",
                           "evidence_digest": "sha256:" + "c" * 64})
        state = reduce(state, {"type": "result", "now": 11, "operation_id": operation_id,
                               "transport": "accepted", "completion": "succeeded", "verification": "failed",
                               "known_effects": "succeeded", "evidence_digest": "sha256:" + "d" * 64})
        state = reduce(state, {"type": "checkpoint", "now": 12, "checkpoint_id": "complete-1",
                               "outcome": "complete", "operation_id": operation_id,
                               "evidence_digest": "sha256:" + "e" * 64})
        complete = reduce(state, {"type": "outcome", "now": 13, "outcome": "complete",
                                  "evidence_digest": "sha256:" + "f" * 64})
        self.assertEqual(load_state(serialize_state(complete))["status"], "terminal")

        state = reduce(self.observed(initial_state(envelope())), admit())
        operation_id = next(iter(state["operations"]))
        state = reduce(state, {"type": "result", "now": 11, "operation_id": operation_id,
                               "transport": "accepted", "completion": "succeeded", "verification": "succeeded",
                               "known_effects": "succeeded", "evidence_digest": "sha256:" + "1" * 64})
        state = reduce(state, {"type": "checkpoint", "now": 12, "checkpoint_id": "verified-1",
                               "outcome": "verified", "operation_id": operation_id,
                               "evidence_digest": "sha256:" + "2" * 64})
        verified = reduce(state, {"type": "outcome", "now": 13, "outcome": "verified",
                                  "evidence_digest": "sha256:" + "3" * 64})
        self.assertEqual(load_state(serialize_state(verified))["status"], "terminal")

    def test_explicit_ceiling_record_persists_without_mutating_next_action_input(self) -> None:
        state = self.observed(initial_state(envelope()))
        decision = next_action(state, 1000)
        self.assertEqual(state["status"], "active")
        self.assertEqual(decision["action"], "refuse")
        blocked = reduce(state, {"type": "ceiling", "now": 1000, "ceiling": "deadline",
                                 "evidence_digest": "sha256:" + "4" * 64})
        replay = load_state(serialize_state(blocked))
        self.assertEqual(replay["status"], "expired")
        self.assertEqual(set(replay["ceiling_report"]), {"activity", "progress", "ceiling", "next_action"})

    def test_stop_receipt_native_fact_and_terminal_observation_are_truthful(self) -> None:
        state = reduce(self.observed(initial_state(envelope())), admit())
        operation_id = next(iter(state["operations"]))
        state = reduce(state, {"type": "dispatch_started", "now": 11, "operation_id": operation_id})
        state = reduce(state, {"type": "stop_run", "now": 12, "persistence_confirmed": True,
                               "evidence_digest": "sha256:" + "5" * 64, "authentication": {
                                   "validated": True, "source_event_id": "human-stop-1", "channel": "operator-stop-1"}})
        self.assertEqual(load_state(serialize_state(state))["stop_receipt"]["source_event_id"], "human-stop-1")
        state = reduce(state, {"type": "observe", "now": 13, "facts_complete": False,
                               "operation_id": operation_id, "transport": "unknown",
                               "evidence_digest": "sha256:" + "6" * 64})
        self.assertEqual(state["status"], "intervention_required")
        self.assertTrue(state["admission_closed"])

    def test_every_ceiling_has_a_durable_four_part_handback(self) -> None:
        cases: list[tuple[str, dict]] = [("deadline", self.observed(initial_state(envelope())))]
        dispatch = self.observed(initial_state(envelope()))
        for attempt in range(1, 4):
            dispatch = reduce(dispatch, admit(attempt=attempt))
            operation_id = list(dispatch["operations"])[-1]
            dispatch = reduce(dispatch, {"type": "dispatch_started", "now": 10 + attempt, "operation_id": operation_id})
            dispatch = reduce(dispatch, {"type": "result", "now": 20 + attempt, "operation_id": operation_id,
                                         "transport": "accepted", "completion": "failed", "verification": "not_run",
                                         "known_effects": "failed", "evidence_digest": "sha256:" + "8" * 64})
            dispatch = self.observed(dispatch)
        cases.append(("dispatch", dispatch))
        for ceiling, counts in (("retry", (3, 0, 0)), ("failure", (0, 3, 0)), ("no_progress", (0, 0, 3))):
            state = self.observed(initial_state(envelope()))
            state = reduce(state, {"type": "account", "now": 2, "retries": counts[0], "failures": counts[1],
                                   "no_progress": counts[2], "evidence_digest": "sha256:" + "8" * 64})
            self.assertEqual(load_state(serialize_state(state))["status"], "blocked")
        reserve = self.observed(initial_state(envelope()))
        reserve = reduce(reserve, {"type": "interval_start", "now": 1, "interval_id": "reserve", "phase": "build"})
        reserve = reduce(reserve, {"type": "interval_stop", "now": 81, "interval_id": "reserve",
                                   "evidence_digest": "sha256:" + "8" * 64})
        cases.append(("reserve", reserve))
        for ceiling, state in cases:
            now = 1000 if ceiling == "deadline" else 82
            state = reduce(state, {"type": "ceiling", "now": now, "ceiling": ceiling,
                                   "evidence_digest": "sha256:" + "8" * 64})
            replay = load_state(serialize_state(state))
            self.assertEqual(set(replay["ceiling_report"]), {"activity", "progress", "ceiling", "next_action"})

    def test_stopped_round_trip_requires_explicit_native_fact_and_never_downgrades(self) -> None:
        state = self.observed(initial_state(envelope()))
        state = reduce(state, {"type": "stop_run", "now": 2, "persistence_confirmed": True,
                               "evidence_digest": "sha256:" + "9" * 64, "authentication": {
                                   "validated": True, "source_event_id": "stop-source", "channel": "operator-stop-1"}})
        for sender in ("builder-1", "verify-1"):
            state = reduce(state, {"type": "fence_sender", "now": 3, "sender_id": sender,
                                   "status": "fenced", "evidence_digest": "sha256:" + "9" * 64})
        with self.assertRaisesRegex(ContinuationError, "native cancellation"):
            reduce(state, {"type": "confirm_stopped", "now": 4, "evidence_digest": "sha256:" + "9" * 64})
        state = reduce(state, {"type": "native_cancellation", "now": 4, "status": "not_required",
                               "evidence_digest": "sha256:" + "9" * 64})
        stopped = reduce(state, {"type": "confirm_stopped", "now": 5, "evidence_digest": "sha256:" + "9" * 64})
        stopped = load_state(serialize_state(stopped))
        self.assertEqual(stopped["status"], "stopped")
        with self.assertRaisesRegex(ContinuationError, "cannot be downgraded"):
            reduce(stopped, {"type": "observe", "now": 6, "facts_complete": False})

    def test_deadline_handback_records_exhaustion_without_discarding_closure_evidence(self) -> None:
        state = reduce(self.observed(initial_state(envelope())), admit())
        operation_id = next(iter(state["operations"]))
        state = reduce(state, {"type": "result", "now": 2, "operation_id": operation_id,
                               "transport": "accepted", "completion": "succeeded", "verification": "succeeded",
                               "known_effects": "succeeded", "evidence_digest": "sha256:" + "a" * 64})
        state = reduce(state, {"type": "checkpoint", "now": 1000, "checkpoint_id": "late-verified",
                               "outcome": "verified", "operation_id": operation_id,
                               "evidence_digest": "sha256:" + "b" * 64})
        self.assertEqual(state["status"], "expired")
        self.assertIsNotNone(state["ceiling_report"])
        self.assertEqual(state["checkpoint"]["outcome"], "verified")
        state = reduce(state, {"type": "outcome", "now": 1000, "outcome": "verified",
                               "evidence_digest": "sha256:" + "c" * 64})
        replay = load_state(serialize_state(state))
        self.assertEqual(replay["status"], "expired")
        self.assertEqual(replay["outcomes"][-1], {
            "outcome": "verified", "status": "expired", "evidence_digest": "sha256:" + "c" * 64,
        })

    def test_terminal_success_requires_quiescent_current_operations_and_senders(self) -> None:
        state = reduce(self.observed(initial_state(envelope())), admit())
        operation_id = next(iter(state["operations"]))
        state = reduce(state, {"type": "result", "now": 2, "operation_id": operation_id,
                               "transport": "accepted", "completion": "succeeded", "verification": "not_run",
                               "known_effects": "succeeded", "evidence_digest": "sha256:" + "a" * 64})
        state = reduce(self.observed(state), admit(sender_id="verify-1", attempt=2))
        with self.assertRaisesRegex(ContinuationError, "quiescent"):
            reduce(state, {"type": "checkpoint", "now": 3, "checkpoint_id": "old-complete",
                           "outcome": "complete", "operation_id": operation_id,
                           "evidence_digest": "sha256:" + "b" * 64})

        state["checkpoint"] = {"checkpoint_id": "old-complete", "outcome": "complete",
                               "operation_id": operation_id, "evidence_digest": "sha256:" + "b" * 64}
        state["status"] = "terminal"
        state["outcomes"] = [{"outcome": "complete", "status": "terminal",
                              "evidence_digest": "sha256:" + "c" * 64}]
        state["transitions"] = [{"transition": "outcome:complete", "from_status": "active",
                                 "to_status": "terminal", "evidence_digest": "sha256:" + "c" * 64}]
        with self.assertRaisesRegex(ContinuationError, "quiescent"):
            load_state(json.dumps(state))

    def test_stopped_is_monotone_across_ceiling_accounting_and_result_events(self) -> None:
        state = self.observed(initial_state(envelope()))
        state = reduce(state, {"type": "stop_run", "now": 2, "persistence_confirmed": True,
                               "evidence_digest": "sha256:" + "a" * 64, "authentication": {
                                   "validated": True, "source_event_id": "stop-source", "channel": "operator-stop-1"}})
        for sender in ("builder-1", "verify-1"):
            state = reduce(state, {"type": "fence_sender", "now": 3, "sender_id": sender,
                                   "status": "fenced", "evidence_digest": "sha256:" + "a" * 64})
        state = reduce(state, {"type": "native_cancellation", "now": 4, "status": "not_required",
                               "evidence_digest": "sha256:" + "a" * 64})
        stopped = reduce(state, {"type": "confirm_stopped", "now": 5, "evidence_digest": "sha256:" + "a" * 64})
        for event in (
            {"type": "ceiling", "now": 1000, "ceiling": "deadline", "evidence_digest": "sha256:" + "b" * 64},
            {"type": "account", "now": 6, "retries": 1, "failures": 0, "no_progress": 0,
             "evidence_digest": "sha256:" + "b" * 64},
            {"type": "result", "now": 6, "operation_id": "missing", "transport": "accepted",
             "completion": "succeeded", "verification": "not_run", "known_effects": "succeeded",
             "evidence_digest": "sha256:" + "b" * 64},
        ):
            with self.subTest(event=event["type"]):
                with self.assertRaisesRegex(ContinuationError, "terminal stopped"):
                    reduce(stopped, event)
        self.assertEqual(load_state(serialize_state(stopped))["status"], "stopped")

    def test_stop_lifecycle_reload_binds_receipt_and_contiguous_transition_chain(self) -> None:
        state = self.observed(initial_state(envelope()))
        state = reduce(state, {"type": "stop_run", "now": 2, "persistence_confirmed": True,
                               "evidence_digest": "sha256:" + "a" * 64, "authentication": {
                                   "validated": True, "source_event_id": "stop-source", "channel": "operator-stop-1"}})
        for sender in ("builder-1", "verify-1"):
            state = reduce(state, {"type": "fence_sender", "now": 3, "sender_id": sender,
                                   "status": "fenced", "evidence_digest": "sha256:" + "a" * 64})
        state = reduce(state, {"type": "native_cancellation", "now": 4, "status": "not_required",
                               "evidence_digest": "sha256:" + "a" * 64})
        stopped = reduce(state, {"type": "confirm_stopped", "now": 5, "evidence_digest": "sha256:" + "a" * 64})
        altered = json.loads(serialize_state(stopped))
        altered["transitions"] = []
        altered["stop_receipt"]["persistence_confirmed"] = False
        with self.assertRaisesRegex(ContinuationError, "Stop receipt|transition"):
            load_state(json.dumps(altered))

        unconfirmed = reduce(self.observed(initial_state(envelope())), {
            "type": "stop_run", "now": 2, "evidence_digest": "sha256:" + "b" * 64,
            "authentication": {"validated": True, "source_event_id": "stop-source", "channel": "operator-stop-1"},
        })
        self.assertEqual(load_state(serialize_state(unconfirmed))["status"], "stop_not_confirmed")

    def test_ledger_limit_exactly_matches_immutable_envelope_on_reload(self) -> None:
        state = initial_state(envelope())
        state["ledger"]["total_limit"] = 1000
        with self.assertRaisesRegex(ContinuationError, "ledger limit"):
            load_state(json.dumps(state))

    def test_deadline_result_persists_expiry_while_retaining_post_stop_closure(self) -> None:
        state = reduce(self.observed(initial_state(envelope())), admit())
        operation_id = next(iter(state["operations"]))
        state = reduce(state, {"type": "result", "now": 1000, "operation_id": operation_id,
                               "transport": "accepted", "completion": "succeeded", "verification": "not_run",
                               "known_effects": "succeeded", "evidence_digest": "sha256:" + "a" * 64})
        self.assertEqual(load_state(serialize_state(state))["status"], "expired")

        state = reduce(self.observed(initial_state(envelope())), admit())
        operation_id = next(iter(state["operations"]))
        state = reduce(state, {"type": "dispatch_started", "now": 2, "operation_id": operation_id})
        state = reduce(state, {"type": "stop_run", "now": 3, "persistence_confirmed": True,
                               "evidence_digest": "sha256:" + "b" * 64, "authentication": {
                                   "validated": True, "source_event_id": "stop-source", "channel": "operator-stop-1"}})
        state = reduce(state, {"type": "result", "now": 1000, "operation_id": operation_id,
                               "transport": "accepted", "completion": "succeeded", "verification": "not_run",
                               "known_effects": "succeeded", "evidence_digest": "sha256:" + "c" * 64})
        replay = load_state(serialize_state(state))
        self.assertEqual(replay["status"], "stopping")
        self.assertIsNotNone(replay["ceiling_report"])

    def test_observed_active_time_overrun_round_trips_without_widening_its_limit(self) -> None:
        state = self.observed(initial_state(envelope()))
        state = reduce(state, {"type": "interval_start", "now": 1, "interval_id": "overrun", "phase": "build"})
        state = reduce(state, {"type": "interval_stop", "now": 151, "interval_id": "overrun",
                               "evidence_digest": "sha256:" + "a" * 64})
        replay = load_state(serialize_state(state))
        self.assertEqual(replay["ledger"]["total_limit"], 100)
        self.assertEqual(replay["ledger"]["total_seconds"], 150)
        self.assertEqual(replay["status"], "blocked")
        self.assertIsNotNone(replay["ceiling_report"])
        self.assertEqual(next_action(replay, 152)["action"], "refuse")

        stopping = self.observed(initial_state(envelope()))
        stopping = reduce(stopping, {"type": "interval_start", "now": 1, "interval_id": "overrun", "phase": "build"})
        stopping = reduce(stopping, {"type": "stop_run", "now": 2, "persistence_confirmed": True,
                                     "evidence_digest": "sha256:" + "b" * 64, "authentication": {
                                         "validated": True, "source_event_id": "stop-source", "channel": "operator-stop-1"}})
        stopping = reduce(stopping, {"type": "interval_stop", "now": 151, "interval_id": "overrun",
                                     "evidence_digest": "sha256:" + "c" * 64})
        replay = load_state(serialize_state(stopping))
        self.assertEqual(replay["ledger"]["total_seconds"], 150)
        self.assertEqual(replay["status"], "stopping")
        self.assertIsNotNone(replay["ceiling_report"])

    def test_deadline_interval_closure_records_exhaustion_in_active_and_stopping_states(self) -> None:
        long = envelope()
        long["limits"] = {**long["limits"], "active_seconds_max": 2000, "verification_reserve_seconds": 20}
        state = self.observed(initial_state(long))
        state = reduce(state, {"type": "interval_start", "now": 1, "interval_id": "deadline", "phase": "build"})
        state = reduce(state, {"type": "interval_stop", "now": 1000, "interval_id": "deadline",
                               "evidence_digest": "sha256:" + "a" * 64})
        replay = load_state(serialize_state(state))
        self.assertEqual(replay["status"], "expired")
        self.assertIsNotNone(replay["ceiling_report"])

        stopping = self.observed(initial_state(long))
        stopping = reduce(stopping, {"type": "interval_start", "now": 1, "interval_id": "deadline", "phase": "build"})
        stopping = reduce(stopping, {"type": "stop_run", "now": 2, "persistence_confirmed": True,
                                     "evidence_digest": "sha256:" + "b" * 64, "authentication": {
                                         "validated": True, "source_event_id": "stop-source", "channel": "operator-stop-1"}})
        stopping = reduce(stopping, {"type": "interval_stop", "now": 1000, "interval_id": "deadline",
                                     "evidence_digest": "sha256:" + "c" * 64})
        replay = load_state(serialize_state(stopping))
        self.assertEqual(replay["status"], "stopping")
        self.assertIsNotNone(replay["ceiling_report"])

    def test_observation_result_fields_and_history_progress_coherently(self) -> None:
        state = reduce(self.observed(initial_state(envelope())), admit())
        operation_id = next(iter(state["operations"]))
        invalid_fields = (
            {"completion": "fenced", "verification": "not_run", "known_effects": "fenced"},
            {"completion": "pending", "verification": "fenced", "known_effects": "pending"},
            {"completion": "pending", "verification": "not_run", "known_effects": "accepted"},
        )
        for fields in invalid_fields:
            with self.subTest(fields=fields):
                with self.assertRaisesRegex(ContinuationError, "observation"):
                    reduce(state, {"type": "observe", "now": 3, "facts_complete": True,
                                   "operation_id": operation_id, "transport": "accepted",
                                   **fields, "evidence_digest": "sha256:" + "a" * 64})

        state = reduce(state, {"type": "dispatch_started", "now": 3, "operation_id": operation_id})
        state = reduce(state, {"type": "result", "now": 4, "operation_id": operation_id,
                               "transport": "accepted", "completion": "pending", "verification": "not_run",
                               "known_effects": "pending", "evidence_digest": "sha256:" + "b" * 64})
        state = reduce(state, {"type": "observe", "now": 5, "facts_complete": True,
                               "operation_id": operation_id, "transport": "accepted",
                               "completion": "succeeded", "verification": "not_run",
                               "known_effects": "succeeded", "evidence_digest": "sha256:" + "c" * 64})
        replay = load_state(serialize_state(state))
        self.assertEqual(replay["operations"][operation_id]["completion"], "succeeded")
        self.assertEqual([item["completion"] for item in replay["results"]], ["pending", "succeeded"])
        with self.assertRaisesRegex(ContinuationError, "terminal observation"):
            reduce(replay, {"type": "observe", "now": 6, "facts_complete": True,
                            "operation_id": operation_id, "transport": "accepted",
                            "completion": "failed", "verification": "not_run",
                            "known_effects": "failed", "evidence_digest": "sha256:" + "d" * 64})

    def test_deadline_non_success_outcome_matrix_round_trips_with_exhaustion(self) -> None:
        for outcome in ("incomplete", "blocked", "current_turn_cancelled", "intervention_required", "ambiguous", "expired"):
            with self.subTest(outcome=outcome):
                state = reduce(self.observed(initial_state(envelope())), {
                    "type": "outcome", "now": 1000, "outcome": outcome,
                    "evidence_digest": "sha256:" + "a" * 64,
                })
                replay = load_state(serialize_state(state))
                self.assertEqual(replay["status"], "expired")
                self.assertEqual(replay["outcomes"][-1]["outcome"], outcome)
                self.assertIsNotNone(replay["ceiling_report"])
                self.assertEqual(next_action(replay, 1001)["action"], "refuse")

    def test_exhausted_success_claims_reload_only_with_current_matching_evidence(self) -> None:
        state = reduce(self.observed(initial_state(envelope())), admit())
        operation_id = next(iter(state["operations"]))
        state = reduce(state, {"type": "result", "now": 2, "operation_id": operation_id,
                               "transport": "accepted", "completion": "succeeded", "verification": "succeeded",
                               "known_effects": "succeeded", "evidence_digest": "sha256:" + "a" * 64})
        state = reduce(state, {"type": "checkpoint", "now": 1000, "checkpoint_id": "late-verified",
                               "outcome": "verified", "operation_id": operation_id,
                               "evidence_digest": "sha256:" + "b" * 64})
        valid = reduce(state, {"type": "outcome", "now": 1000, "outcome": "verified",
                               "evidence_digest": "sha256:" + "c" * 64})
        self.assertEqual(load_state(serialize_state(valid))["status"], "expired")
        for mutate in (
            lambda record: record.update(results=[]),
            lambda record: record.update(checkpoint=None),
            lambda record: record["senders"]["builder-1"].update(status="mutable"),
        ):
            edited = json.loads(serialize_state(valid))
            mutate(edited)
            with self.subTest(mutate=mutate), self.assertRaisesRegex(ContinuationError, "success|quiescent"):
                load_state(json.dumps(edited))

    def test_stop_receipt_implies_matching_closed_state_and_transition_evidence(self) -> None:
        active = initial_state(envelope())
        active["stop_receipt"] = {"source_event_id": "stop-source", "channel": "operator-stop-1",
                                  "persistence_confirmed": True, "evidence_digest": "sha256:" + "a" * 64}
        with self.assertRaisesRegex(ContinuationError, "Stop receipt"):
            load_state(json.dumps(active))

        state = reduce(self.observed(initial_state(envelope())), {
            "type": "stop_run", "now": 2, "persistence_confirmed": True,
            "evidence_digest": "sha256:" + "b" * 64, "authentication": {
                "validated": True, "source_event_id": "stop-source", "channel": "operator-stop-1"}})
        self.assertEqual(load_state(serialize_state(state))["status"], "stopping")
        for sender in ("builder-1", "verify-1"):
            state = reduce(state, {"type": "fence_sender", "now": 3, "sender_id": sender,
                                   "status": "fenced", "evidence_digest": "sha256:" + "b" * 64})
        state = reduce(state, {"type": "native_cancellation", "now": 4, "status": "not_required",
                               "evidence_digest": "sha256:" + "b" * 64})
        stopped = reduce(state, {"type": "confirm_stopped", "now": 5, "evidence_digest": "sha256:" + "b" * 64})
        edited = json.loads(serialize_state(stopped))
        edited["stop_receipt"]["evidence_digest"] = "sha256:" + "c" * 64
        with self.assertRaisesRegex(ContinuationError, "Stop receipt"):
            load_state(json.dumps(edited))

    def test_interval_close_refuses_unknown_id_but_replays_charged_idempotently(self) -> None:
        state = self.observed(initial_state(envelope()))
        with self.assertRaisesRegex(ContinuationError, "charged interval"):
            reduce(state, {"type": "interval_stop", "now": 2, "interval_id": "never-started"})
        state = reduce(state, {"type": "interval_start", "now": 1, "interval_id": "known", "phase": "build"})
        state = reduce(state, {"type": "interval_stop", "now": 2, "interval_id": "known"})
        self.assertEqual(reduce(state, {"type": "interval_stop", "now": 3, "interval_id": "known"}), state)

    def test_durable_integer_fields_reject_bool_without_rejecting_zero_or_positive_ints(self) -> None:
        record = initial_state(envelope())["ledger"]
        valid = json.loads(json.dumps(record))
        valid["phase_limits"] = {"build": 0}
        self.assertEqual(ActiveTimeLedger.from_record(valid).phase_limits, {"build": 0})
        malformed_records = (
            {**record, "total_limit": True},
            {**record, "total_seconds": True, "by_phase": {"build": True}},
            {**record, "phase_limits": {"build": True}},
            {**record, "by_phase": {"build": True}, "total_seconds": 1},
            {**record, "open_intervals": {"open": {"phase": "build", "started": True}}},
        )
        for malformed in malformed_records:
            with self.subTest(malformed=malformed), self.assertRaises(CeilingError):
                ActiveTimeLedger.from_record(malformed)

        epoch_envelope = envelope()
        epoch_envelope["initial_epoch"] = 1
        state = initial_state(epoch_envelope)
        state["epoch"] = True
        with self.assertRaisesRegex(ContinuationError, "epoch"):
            serialize_state(state)

    def test_operation_map_key_must_match_immutable_operation_identity(self) -> None:
        state = reduce(self.observed(initial_state(envelope())), admit())
        operation_id = next(iter(state["operations"]))
        state["operations"]["wrong-key"] = state["operations"].pop(operation_id)
        with self.assertRaisesRegex(ContinuationError, "operation key"):
            serialize_state(state)

        valid = reduce(self.observed(initial_state(envelope())), admit())
        self.assertEqual(load_state(serialize_state(valid))["operations"], valid["operations"])

    def test_state_and_envelope_schema_versions_require_integer_one(self) -> None:
        for version in (True, 1.0):
            with self.subTest(container="envelope", version=version):
                invalid_envelope = envelope()
                invalid_envelope["schema_version"] = version
                with self.assertRaisesRegex(ContinuationError, "envelope"):
                    initial_state(invalid_envelope)
            with self.subTest(container="state", version=version):
                invalid_state = initial_state(envelope())
                invalid_state["schema_version"] = version
                with self.assertRaisesRegex(ContinuationError, "state"):
                    serialize_state(invalid_state)
        self.assertEqual(load_state(serialize_state(initial_state(envelope())))["schema_version"], 1)

    def test_stop_discards_unsent_operation_with_terminal_no_effects(self) -> None:
        state = reduce(self.observed(initial_state(envelope())), admit())
        operation_id = next(iter(state["operations"]))
        state = reduce(state, {"type": "stop_run", "now": 3, "persistence_confirmed": True,
                               "evidence_digest": "sha256:" + "a" * 64, "authentication": {
                                   "validated": True, "source_event_id": "stop-unsent", "channel": "operator-stop-1"}})
        self.assertEqual(state["operations"][operation_id]["status"], "discarded")
        self.assertEqual(state["operations"][operation_id]["known_effects"], "not_run")
        for sender in ("builder-1", "verify-1"):
            state = reduce(state, {"type": "fence_sender", "now": 4, "sender_id": sender,
                                   "status": "fenced", "evidence_digest": "sha256:" + "a" * 64})
        state = reduce(state, {"type": "native_cancellation", "now": 5, "status": "not_required",
                               "evidence_digest": "sha256:" + "a" * 64})
        stopped = reduce(state, {"type": "confirm_stopped", "now": 6, "evidence_digest": "sha256:" + "a" * 64})
        self.assertEqual(load_state(serialize_state(stopped))["status"], "stopped")

    def test_stop_discard_remains_bound_through_post_stop_refusal_and_overrun_closure(self) -> None:
        short_envelope = envelope()
        short_envelope["limits"]["active_seconds_max"] = 10
        short_envelope["limits"]["verification_reserve_seconds"] = 2
        state = self.observed(initial_state(short_envelope))
        state = reduce(state, admit(now=2))
        operation_id = next(iter(state["operations"]))
        state = reduce(state, {"type": "interval_start", "now": 3,
                               "interval_id": "discard-overrun", "phase": "build"})
        state = reduce(state, {"type": "stop_run", "now": 4, "persistence_confirmed": True,
                               "evidence_digest": "sha256:" + "a" * 64, "authentication": {
                                   "validated": True, "source_event_id": "stop-discard-refusal",
                                   "channel": "operator-stop-1"}})
        self.assertEqual(state["operations"][operation_id]["status"], "discarded")
        malformed_receipt = json.loads(serialize_state(state))
        malformed_receipt["stop_receipt"] = {}
        with self.assertRaises(ContinuationError):
            validate_state(malformed_receipt)
        state = reduce(state, {"type": "native_cancellation", "now": 5, "status": "unknown",
                               "evidence_digest": "sha256:" + "b" * 64})
        self.assertEqual(load_state(serialize_state(state))["status"], "intervention_required")
        closed = reduce(state, {"type": "interval_stop", "now": 20,
                                "interval_id": "discard-overrun", "evidence_digest": "sha256:" + "c" * 64})
        replay = load_state(serialize_state(closed))
        self.assertEqual((replay["status"], replay["operations"][operation_id]["status"],
                          replay["ledger"]["total_seconds"], replay["ledger"]["charged_ids"]),
                         ("intervention_required", "discarded", 17, ["discard-overrun"]))
        self.assertIsNotNone(replay["ceiling_report"])

        for transport in ("accepted", "queued"):
            with self.subTest(transport=transport):
                state = reduce(self.observed(initial_state(envelope())), admit())
                operation_id = next(iter(state["operations"]))
                state = reduce(state, {"type": "result", "now": 2, "operation_id": operation_id,
                                       "transport": transport, "completion": "pending", "verification": "not_run",
                                       "known_effects": "pending", "evidence_digest": "sha256:" + "d" * 64})
                state = reduce(state, {"type": "stop_run", "now": 3, "persistence_confirmed": True,
                                       "evidence_digest": "sha256:" + "e" * 64, "authentication": {
                                           "validated": True, "source_event_id": "stop-" + transport,
                                           "channel": "operator-stop-1"}})
                state = reduce(state, {"type": "observe", "now": 4, "facts_complete": True,
                                       "operation_id": operation_id, "transport": transport, "completion": "pending",
                                       "verification": "not_run", "known_effects": "fenced",
                                       "evidence_digest": "sha256:" + "f" * 64})
                self.assertEqual(state["operations"][operation_id]["status"], "fenced")
                self.assertEqual(load_state(serialize_state(state))["results"][-1]["known_effects"], "fenced")

                direct = reduce(self.observed(initial_state(envelope())), admit())
                direct_id = next(iter(direct["operations"]))
                direct = reduce(direct, {"type": "dispatch_started", "now": 2, "operation_id": direct_id})
                direct = reduce(direct, {"type": "stop_run", "now": 3, "persistence_confirmed": True,
                                         "evidence_digest": "sha256:" + "0" * 64, "authentication": {
                                             "validated": True, "source_event_id": "stop-direct-" + transport,
                                             "channel": "operator-stop-1"}})
                direct = reduce(direct, {"type": "result", "now": 4, "operation_id": direct_id,
                                         "transport": transport, "completion": "pending", "verification": "not_run",
                                         "known_effects": "fenced", "evidence_digest": "sha256:" + "1" * 64})
                self.assertEqual(load_state(serialize_state(direct))["operations"][direct_id]["status"], "fenced")

    def test_stop_preserves_admitted_operations_with_observed_transport_progress(self) -> None:
        def stopped_after_progress(progress: dict) -> dict:
            state = reduce(self.observed(initial_state(envelope())), admit())
            operation_id = next(iter(state["operations"]))
            state = reduce(state, {**progress, "operation_id": operation_id})
            return reduce(state, {"type": "stop_run", "now": 3, "persistence_confirmed": True,
                                  "evidence_digest": "sha256:" + "a" * 64, "authentication": {
                                      "validated": True, "source_event_id": "stop-observed-transport",
                                      "channel": "operator-stop-1"}})

        result_state = stopped_after_progress({
            "type": "result", "now": 2, "transport": "accepted", "completion": "pending",
            "verification": "not_run", "known_effects": "pending", "evidence_digest": "sha256:" + "5" * 64,
        })
        operation = next(iter(result_state["operations"].values()))
        self.assertEqual((operation["status"], operation["transport"], operation["known_effects"]),
                         ("in_flight", "accepted", "pending"))
        self.assertEqual(load_state(serialize_state(result_state)), result_state)

        for transport in ("accepted", "queued"):
            with self.subTest(source="observe", transport=transport):
                observed_state = stopped_after_progress({
                    "type": "observe", "now": 2, "facts_complete": True, "transport": transport,
                    "completion": "pending", "verification": "not_run", "known_effects": "pending",
                    "evidence_digest": "sha256:" + "6" * 64,
                })
                operation = next(iter(observed_state["operations"].values()))
                self.assertEqual((operation["status"], operation["transport"], operation["known_effects"]),
                                 ("in_flight", transport, "pending"))
                self.assertEqual(load_state(serialize_state(observed_state)), observed_state)

    def test_repeated_stop_receipts_preserve_replay_and_confirmed_monotonicity(self) -> None:
        authentication = lambda source: {"validated": True, "source_event_id": source, "channel": "operator-stop-1"}
        first = reduce(self.observed(initial_state(envelope())), {
            "type": "stop_run", "now": 2, "persistence_confirmed": False,
            "evidence_digest": "sha256:" + "a" * 64, "authentication": authentication("stop-1")})
        first = load_state(serialize_state(first))
        replay = reduce(first, {
            "type": "stop_run", "now": 3, "persistence_confirmed": False,
            "evidence_digest": "sha256:" + "a" * 64, "authentication": authentication("stop-1")})
        self.assertEqual(replay, first)
        repeated = reduce(first, {
            "type": "stop_run", "now": 3, "persistence_confirmed": False,
            "evidence_digest": "sha256:" + "b" * 64, "authentication": authentication("stop-2")})
        self.assertEqual(load_state(serialize_state(repeated))["stop_receipt"]["source_event_id"], "stop-2")
        confirmed = reduce(repeated, {
            "type": "stop_run", "now": 4, "persistence_confirmed": True,
            "evidence_digest": "sha256:" + "c" * 64, "authentication": authentication("stop-3")})
        self.assertEqual(load_state(serialize_state(confirmed))["status"], "stopping")
        self.assertEqual(confirmed["epoch"], envelope()["initial_epoch"] + 1)
        with self.assertRaisesRegex(ContinuationError, "already closed"):
            reduce(confirmed, {
                "type": "stop_run", "now": 5, "persistence_confirmed": False,
                "evidence_digest": "sha256:" + "d" * 64, "authentication": authentication("stop-4")})

    def test_native_cancellation_keeps_terminal_evidence_monotone(self) -> None:
        def stopping() -> dict:
            return reduce(self.observed(initial_state(envelope())), {
                "type": "stop_run", "now": 2, "persistence_confirmed": True,
                "evidence_digest": "sha256:" + "a" * 64, "authentication": {
                    "validated": True, "source_event_id": "stop-native", "channel": "operator-stop-1"}})

        state = reduce(stopping(), {"type": "native_cancellation", "now": 3, "status": "requested",
                                   "evidence_digest": "sha256:" + "b" * 64})
        state = reduce(state, {"type": "native_cancellation", "now": 4, "status": "cancelled",
                               "evidence_digest": "sha256:" + "c" * 64})
        self.assertEqual(load_state(serialize_state(state))["native_cancellation"]["status"], "cancelled")
        with self.assertRaisesRegex(ContinuationError, "native cancellation.*regress"):
            reduce(state, {"type": "native_cancellation", "now": 5, "status": "requested",
                           "evidence_digest": "sha256:" + "d" * 64})
        unknown = reduce(stopping(), {"type": "native_cancellation", "now": 3, "status": "unknown",
                                      "evidence_digest": "sha256:" + "e" * 64})
        self.assertEqual(load_state(serialize_state(unknown))["status"], "intervention_required")

    def test_frozen_sender_and_operation_sets_require_unique_exact_identifiers(self) -> None:
        state = reduce(self.observed(initial_state(envelope())), admit())
        operation_id = next(iter(state["operations"]))
        state = reduce(state, {"type": "stop_run", "now": 3, "persistence_confirmed": True,
                               "evidence_digest": "sha256:" + "a" * 64, "authentication": {
                                   "validated": True, "source_event_id": "stop-frozen", "channel": "operator-stop-1"}})
        self.assertEqual(load_state(serialize_state(state))["frozen_operations"], [operation_id])
        duplicate_sender = json.loads(serialize_state(state))
        duplicate_sender["frozen_senders"].append(duplicate_sender["frozen_senders"][0])
        with self.assertRaisesRegex(ContinuationError, "frozen identifiers"):
            load_state(json.dumps(duplicate_sender))
        duplicate_operation = json.loads(serialize_state(state))
        duplicate_operation["frozen_operations"].append(operation_id)
        with self.assertRaisesRegex(ContinuationError, "frozen identifiers"):
            load_state(json.dumps(duplicate_operation))

    def test_public_state_event_matrix_returns_only_replayable_states_or_refusals(self) -> None:
        authentication = {"validated": True, "source_event_id": "stop-matrix", "channel": "operator-stop-1"}
        active = self.observed(initial_state(envelope()))
        exhausted = reduce(active, {"type": "outcome", "now": 1000, "outcome": "incomplete",
                                   "evidence_digest": "sha256:" + "a" * 64})
        unconfirmed = reduce(self.observed(initial_state(envelope())), {
            "type": "stop_run", "now": 2, "persistence_confirmed": False,
            "evidence_digest": "sha256:" + "b" * 64, "authentication": authentication})
        stopping = reduce(self.observed(initial_state(envelope())), {
            "type": "stop_run", "now": 2, "persistence_confirmed": True,
            "evidence_digest": "sha256:" + "c" * 64, "authentication": authentication})
        intervention = reduce(stopping, {"type": "native_cancellation", "now": 3, "status": "unknown",
                                         "evidence_digest": "sha256:" + "d" * 64})
        stopped = self.observed(initial_state(envelope()))
        stopped = reduce(stopped, {"type": "stop_run", "now": 2, "persistence_confirmed": True,
                                   "evidence_digest": "sha256:" + "e" * 64, "authentication": authentication})
        for sender in ("builder-1", "verify-1"):
            stopped = reduce(stopped, {"type": "fence_sender", "now": 3, "sender_id": sender,
                                       "status": "fenced", "evidence_digest": "sha256:" + "e" * 64})
        stopped = reduce(stopped, {"type": "native_cancellation", "now": 4, "status": "not_required",
                                   "evidence_digest": "sha256:" + "e" * 64})
        stopped = reduce(stopped, {"type": "confirm_stopped", "now": 5, "evidence_digest": "sha256:" + "e" * 64})

        accepted = (
            (active, {"type": "optional_counter", "now": 2, "name": "tokens", "value": 1,
                      "reason": None, "evidence_digest": "sha256:" + "f" * 64}),
            (exhausted, {"type": "outcome", "now": 1000, "outcome": "blocked",
                         "evidence_digest": "sha256:" + "f" * 64}),
            (unconfirmed, {"type": "stop_run", "now": 3, "persistence_confirmed": False,
                           "evidence_digest": "sha256:" + "f" * 64,
                           "authentication": {**authentication, "source_event_id": "stop-matrix-2"}}),
            (stopping, {"type": "native_cancellation", "now": 3, "status": "requested",
                        "evidence_digest": "sha256:" + "f" * 64}),
            (intervention, {"type": "stop_current_turn", "now": 4}),
        )
        for state, event in accepted:
            with self.subTest(status=state["status"], event=event["type"]):
                returned = reduce(state, event)
                self.assertEqual(load_state(serialize_state(returned)), returned)
        with self.assertRaisesRegex(ContinuationError, "stopped"):
            reduce(stopped, {"type": "stop_current_turn", "now": 6})

    def test_open_intervals_must_close_before_terminal_handback_but_can_close_in_refusal_states(self) -> None:
        digest = lambda character: "sha256:" + character * 64

        def successful_with_open_interval(outcome: str) -> tuple[dict, str]:
            state = reduce(self.observed(initial_state(envelope())), admit())
            operation_id = next(iter(state["operations"]))
            state = reduce(state, {"type": "result", "now": 2, "operation_id": operation_id,
                                   "transport": "accepted", "completion": "succeeded",
                                   "verification": "succeeded", "known_effects": "succeeded",
                                   "evidence_digest": digest("a")})
            state = reduce(state, {"type": "checkpoint", "now": 3,
                                   "checkpoint_id": outcome + "-checkpoint", "outcome": outcome,
                                   "operation_id": operation_id, "evidence_digest": digest("b")})
            interval_id = outcome + "-open"
            state = reduce(state, {"type": "interval_start", "now": 4,
                                   "interval_id": interval_id, "phase": "verify"})
            return state, interval_id

        for outcome in ("complete", "verified"):
            with self.subTest(handback=outcome):
                state, interval_id = successful_with_open_interval(outcome)
                with self.assertRaisesRegex(ContinuationError, "quiescent"):
                    reduce(state, {"type": "outcome", "now": 5, "outcome": outcome,
                                   "evidence_digest": digest("c")})
                state = reduce(state, {"type": "interval_stop", "now": 6, "interval_id": interval_id})
                terminal = reduce(state, {"type": "outcome", "now": 6, "outcome": outcome,
                                          "evidence_digest": digest("c")})
                self.assertEqual(load_state(serialize_state(terminal))["status"], "terminal")
                self.assertEqual(terminal["ledger"]["total_seconds"], 2)
                edited = json.loads(serialize_state(terminal))
                edited["ledger"]["open_intervals"] = {"stale-open": {"phase": "verify", "started": 6}}
                with self.assertRaisesRegex(ContinuationError, "quiescent"):
                    load_state(json.dumps(edited))

        stopping = self.observed(initial_state(envelope()))
        stopping = reduce(stopping, {"type": "interval_start", "now": 2,
                                     "interval_id": "stop-open", "phase": "build"})
        stopping = reduce(stopping, {"type": "stop_run", "now": 3, "persistence_confirmed": True,
                                     "evidence_digest": digest("d"), "authentication": {
                                         "validated": True, "source_event_id": "stop-accounting",
                                         "channel": "operator-stop-1"}})
        for sender in ("builder-1", "verify-1"):
            stopping = reduce(stopping, {"type": "fence_sender", "now": 4, "sender_id": sender,
                                         "status": "fenced", "evidence_digest": digest("d")})
        stopping = reduce(stopping, {"type": "native_cancellation", "now": 4, "status": "not_required",
                                     "evidence_digest": digest("d")})
        with self.assertRaisesRegex(ContinuationError, "intervals"):
            reduce(stopping, {"type": "confirm_stopped", "now": 5, "evidence_digest": digest("d")})
        stopping = reduce(stopping, {"type": "interval_stop", "now": 6, "interval_id": "stop-open"})
        stopped = reduce(stopping, {"type": "confirm_stopped", "now": 6, "evidence_digest": digest("d")})
        self.assertEqual(load_state(serialize_state(stopped))["ledger"]["total_seconds"], 4)

        refusal_events = (
            ("incomplete", 3), ("blocked", 3), ("intervention_required", 3),
            ("ambiguous", 3), ("expired", 1000),
        )
        for outcome, outcome_now in refusal_events:
            with self.subTest(refusal=outcome):
                state = self.observed(initial_state(envelope()))
                interval_id = outcome + "-open"
                state = reduce(state, {"type": "interval_start", "now": 2,
                                       "interval_id": interval_id, "phase": "build"})
                state = reduce(state, {"type": "outcome", "now": outcome_now, "outcome": outcome,
                                       "evidence_digest": digest("e")})
                closed = reduce(state, {"type": "interval_stop", "now": outcome_now + 1,
                                        "interval_id": interval_id, "evidence_digest": digest("f")})
                self.assertEqual(load_state(serialize_state(closed))["ledger"]["open_intervals"], {})
                with self.assertRaises(ContinuationError):
                    reduce(closed, {"type": "interval_start", "now": outcome_now + 2,
                                    "interval_id": "successor", "phase": "build"})

        for confirmed, expected_status in ((False, "stop_not_confirmed"), (True, "stopping")):
            with self.subTest(stop_status=expected_status):
                state = self.observed(initial_state(envelope()))
                state = reduce(state, {"type": "interval_start", "now": 2,
                                       "interval_id": expected_status, "phase": "build"})
                state = reduce(state, {"type": "stop_run", "now": 3, "persistence_confirmed": confirmed,
                                       "evidence_digest": digest("0"), "authentication": {
                                           "validated": True, "source_event_id": "stop-" + expected_status,
                                           "channel": "operator-stop-1"}})
                state = reduce(state, {"type": "interval_stop", "now": 4,
                                       "interval_id": expected_status, "evidence_digest": digest("1")})
                self.assertEqual(load_state(serialize_state(state))["status"], expected_status)

        short_envelope = envelope()
        short_envelope["limits"]["active_seconds_max"] = 10
        short_envelope["limits"]["verification_reserve_seconds"] = 2
        overrun = self.observed(initial_state(short_envelope))
        overrun = reduce(overrun, {"type": "interval_start", "now": 2,
                                   "interval_id": "overrun", "phase": "build"})
        overrun = reduce(overrun, {"type": "outcome", "now": 3, "outcome": "incomplete",
                                   "evidence_digest": digest("2")})
        overrun = reduce(overrun, {"type": "interval_stop", "now": 20,
                                   "interval_id": "overrun", "evidence_digest": digest("3")})
        self.assertEqual((overrun["status"], overrun["ledger"]["total_seconds"],
                          overrun["ledger"]["open_intervals"]), ("blocked", 18, {}))
        self.assertIsNotNone(overrun["ceiling_report"])
        self.assertEqual(reduce(overrun, {"type": "interval_stop", "now": 21,
                                          "interval_id": "overrun", "evidence_digest": digest("3")}), overrun)

        stop_overrun = self.observed(initial_state(short_envelope))
        stop_overrun = reduce(stop_overrun, {"type": "interval_start", "now": 2,
                                             "interval_id": "stop-overrun", "phase": "build"})
        stop_overrun = reduce(stop_overrun, {"type": "stop_run", "now": 3,
                                             "persistence_confirmed": True, "evidence_digest": digest("4"),
                                             "authentication": {"validated": True,
                                                                "source_event_id": "stop-overrun",
                                                                "channel": "operator-stop-1"}})
        stop_overrun = reduce(stop_overrun, {"type": "interval_stop", "now": 20,
                                             "interval_id": "stop-overrun", "evidence_digest": digest("5")})
        self.assertEqual((stop_overrun["status"], stop_overrun["ledger"]["total_seconds"]),
                         ("stopping", 18))
        self.assertIsNotNone(load_state(serialize_state(stop_overrun))["ceiling_report"])


if __name__ == "__main__":
    unittest.main()
