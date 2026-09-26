"""Frozen K1 external-operation interface signatures."""

from __future__ import annotations

from typing import Any

from .operations import OperationCoordinator


class ExternalOperations:
    def __init__(self, coordinator: OperationCoordinator, mission_id: str, generation: int):
        self.coordinator = coordinator
        self.mission_id = mission_id
        self.generation = generation

    def _run(self, kind: str, target: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.coordinator.run(self.mission_id, self.generation, kind, target, payload)

    def control_ref_create(self, control_ref: str, genesis_payload: dict[str, Any], expected_absent: bool) -> dict[str, Any]:
        return self._run("control-ref-create", control_ref, {
            "control_ref": control_ref,
            "genesis_payload": genesis_payload,
            "expected_absent": expected_absent,
        })

    def registry_locator_upsert(self, locator_payload: dict[str, Any], expected_registry_revision: int) -> dict[str, Any]:
        return self._run("registry-locator-upsert", "protected-registry", {
            "locator_payload": locator_payload,
            "expected_registry_revision": expected_registry_revision,
        })

    def branch_ensure(self, repository: str, branch: str, from_sha: str, expected_absent_or_sha: str) -> dict[str, Any]:
        return self._run("branch-ensure", f"{repository}#{branch}", {
            "repository": repository,
            "branch": branch,
            "from_sha": from_sha,
            "expected_absent_or_sha": expected_absent_or_sha,
        })

    def pr_upsert(
        self,
        repository: str,
        branch: str,
        target: str,
        marker: str,
        metadata_digest: str,
        expected_head_sha: str,
    ) -> dict[str, Any]:
        return self._run("pr-upsert", f"{repository}#{marker}", {
            "repository": repository,
            "branch": branch,
            "target": target,
            "marker": marker,
            "metadata_digest": metadata_digest,
            "expected_head_sha": expected_head_sha,
        })

    def question_publish(self, tracker_ref: str, question_id: str, revision: int, payload_digest: str) -> dict[str, Any]:
        return self._run("question-publish", f"{tracker_ref}#{question_id}:{revision}", {
            "tracker_ref": tracker_ref,
            "question_id": question_id,
            "revision": revision,
            "payload_digest": payload_digest,
        })
