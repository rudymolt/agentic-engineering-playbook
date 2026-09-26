"""GitHub CLI adapter for the K4.1 expected-head merge boundary."""

from __future__ import annotations

import base64
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .canonical import canonical_bytes, digest, load_strict
from .contracts import ContractError, ContractRegistry, SHA256


Runner = Callable[..., subprocess.CompletedProcess[str]]


class GitHubCliDecisionStore:
    """Persist and independently re-read canonical decisions on the PR host."""

    def __init__(self, runner: Runner = subprocess.run):
        self.runner = runner

    def _json(self, command: list[str]) -> Any:
        result = self.runner(command, text=True, capture_output=True, check=False, timeout=60)
        if result.returncode:
            raise ContractError(f"GitHub durable-store operation failed with exit {result.returncode}")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ContractError("GitHub durable-store operation returned malformed JSON") from exc

    @staticmethod
    def _locator(repository: str, pr_number: int, comment_id: int) -> str:
        return f"github:issue-comment:{repository}:{pr_number}:{comment_id}"

    @staticmethod
    def _parse_locator(locator: str) -> tuple[str, int, int]:
        matched = re.fullmatch(
            r"github:issue-comment:([^/\s:]+/[^/\s:]+):([1-9][0-9]*):([1-9][0-9]*)", locator,
        )
        if not matched:
            raise ContractError("merge-decision-attestation: invalid GitHub comment locator")
        return matched.group(1), int(matched.group(2)), int(matched.group(3))

    def persist(self, decision: dict[str, Any]) -> dict[str, Any]:
        body = canonical_bytes(decision).decode("utf-8")
        created = self._json([
            "gh", "api", "--method", "POST",
            f"repos/{decision['repository']}/issues/{decision['pr_number']}/comments",
            "-f", f"body={body}",
        ])
        comment_id = created.get("id")
        if not isinstance(comment_id, int) or comment_id < 1:
            raise ContractError("GitHub decision persistence returned no comment ID")
        locator = self._locator(decision["repository"], decision["pr_number"], comment_id)
        attestation = {
            "schema_version": 1,
            "attestation_id": f"merge-decision-attestation-{comment_id}",
            "decision_digest": digest(decision),
            "readback_digest": digest(decision),
            "source_event_id": locator,
            "session_id": decision["agent"]["session_id"],
            "attested_at": created.get("created_at"),
        }
        self.verify(attestation, decision)
        return attestation

    def verify(self, attestation: dict[str, Any], decision: dict[str, Any]) -> None:
        repository, pr_number, comment_id = self._parse_locator(str(attestation.get("source_event_id", "")))
        if repository != decision.get("repository") or pr_number != decision.get("pr_number"):
            raise ContractError("merge-decision-attestation: repository or PR mismatch")
        observed = self._json(["gh", "api", f"repos/{repository}/issues/comments/{comment_id}"])
        expected_body = canonical_bytes(decision).decode("utf-8")
        if observed.get("body") != expected_body:
            raise ContractError("merge-decision-attestation: host readback body mismatch")
        if observed.get("created_at") != attestation.get("attested_at"):
            raise ContractError("merge-decision-attestation: host timestamp mismatch")
        if observed.get("issue_url") != f"https://api.github.com/repos/{repository}/issues/{pr_number}":
            raise ContractError("merge-decision-attestation: host comment subject mismatch")


def _validate_remote_mission(control: dict[str, Any], now: datetime) -> None:
    """Validate merge-critical Mission V1 structure and chronology fail-closed."""

    revision = control.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ContractError("Mission Control revision must be positive")
    prior = control.get("prior_digest")
    if (revision == 1 and prior is not None) or (revision > 1 and not SHA256.fullmatch(str(prior))):
        raise ContractError("Mission Control prior digest does not match revision")
    try:
        updated_at = datetime.fromisoformat(str(control.get("updated_at", "")).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("Mission Control updated_at is invalid") from exc
    if updated_at.tzinfo is None or updated_at.utcoffset() is None or updated_at > now:
        raise ContractError("Mission Control chronology is invalid")
    controller = control.get("controller")
    if not isinstance(controller, dict) or not {
        "generation", "workspace_id", "session_id",
    } <= set(controller):
        raise ContractError("Mission Control controller is incomplete")
    if (
        not isinstance(controller["generation"], int)
        or isinstance(controller["generation"], bool)
        or controller["generation"] < 1
        or any(not isinstance(controller[field], str) or not controller[field] for field in ("workspace_id", "session_id"))
    ):
        raise ContractError("Mission Control controller is invalid")
    candidate = control.get("candidate")
    required_candidate = {"head_sha", "tree_sha", "builder_session_ids", "frozen_at"}
    if not isinstance(candidate, dict) or not required_candidate <= set(candidate):
        raise ContractError("Mission Control candidate is incomplete")
    if any(not re.fullmatch(r"[0-9a-f]{40}", str(candidate[field])) for field in ("head_sha", "tree_sha")):
        raise ContractError("Mission Control candidate tuple is invalid")
    builders = candidate["builder_session_ids"]
    if not isinstance(builders, list) or not builders or any(not isinstance(item, str) or not item for item in builders):
        raise ContractError("Mission Control builder sessions are invalid")
    try:
        frozen_at = datetime.fromisoformat(str(candidate["frozen_at"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("Mission Control frozen_at is invalid") from exc
    if frozen_at.tzinfo is None or frozen_at.utcoffset() is None or frozen_at > updated_at:
        raise ContractError("Mission Control candidate chronology is invalid")
    authority = control.get("authority")
    if (
        not isinstance(authority, dict)
        or authority.get("command") != "deliver-to-pr"
        or authority.get("requested_tier") != "A"
        or authority.get("effective_tier") != "A"
        or authority.get("policy_kind") != "pilot-composite"
        or not isinstance(authority.get("envelope_digest"), str)
        or not SHA256.fullmatch(authority["envelope_digest"])
    ):
        raise ContractError("Mission Control authority is invalid")
    aggregate = control.get("aggregate")
    if not isinstance(aggregate, dict) or not {"phase", "status", "terminal_outcome", "wake_guard"} <= set(aggregate):
        raise ContractError("Mission Control aggregate is incomplete")
    if (
        aggregate.get("phase") not in {"pr-ready", "handback"}
        or aggregate.get("status") != "running"
        or aggregate.get("terminal_outcome") is not None
        or aggregate.get("wake_guard") is not None
    ):
        raise ContractError("Mission Control aggregate is not merge-eligible")
    for label in ("findings", "interrupts"):
        items = control.get(label)
        if not isinstance(items, list) or any(not isinstance(item, dict) or not isinstance(item.get("status"), str) for item in items):
            raise ContractError(f"Mission Control {label} are invalid")
    if not isinstance(control.get("required_actions"), list):
        raise ContractError("Mission Control required actions are invalid")


class GitHubCliMergeHost:
    def __init__(
        self,
        *,
        merge_method: str,
        standing_authority: dict[str, Any],
        expected_controller_generation: int,
        expected_candidate: dict[str, Any],
        expected_envelope_digest: str,
        mission_id: str,
        runner: Runner = subprocess.run,
    ):
        self.merge_method = merge_method
        self.standing_authority = standing_authority
        self.expected_controller_generation = expected_controller_generation
        self.expected_candidate = expected_candidate
        self.expected_envelope_digest = expected_envelope_digest
        self.mission_id = mission_id
        self.runner = runner

    def _json(self, command: list[str]) -> Any:
        result = self.runner(command, text=True, capture_output=True, check=False, timeout=60)
        if result.returncode:
            raise ContractError(f"GitHub observation failed with exit {result.returncode}")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ContractError("GitHub observation returned malformed JSON") from exc

    @staticmethod
    def _split(repository: str) -> tuple[str, str]:
        parts = repository.split("/")
        if len(parts) != 2 or any(not part for part in parts):
            raise ContractError("repository must be owner/name")
        return parts[0], parts[1]

    def inspect(self, repository: str, pr_number: int) -> dict[str, Any]:
        owner, name = self._split(repository)
        fields = "state,isDraft,headRefOid,baseRefName,baseRefOid,mergeable,mergeStateStatus,statusCheckRollup,reviewDecision,mergedAt,mergedBy,mergeCommit,url"
        pr = self._json(["gh", "pr", "view", str(pr_number), "-R", repository, "--json", fields])
        observed_head = pr.get("headRefOid")
        if not isinstance(observed_head, str) or not re.fullmatch(r"[0-9a-f]{40}", observed_head):
            raise ContractError("pull-request head observation is incomplete")
        head_commit = self._json(["gh", "api", f"repos/{repository}/git/commits/{observed_head}"])
        observed_tree = head_commit.get("tree", {}).get("sha")
        if not isinstance(observed_tree, str) or not re.fullmatch(r"[0-9a-f]{40}", observed_tree):
            raise ContractError("pull-request tree observation is incomplete")
        repository_data = self._json(["gh", "api", f"repos/{repository}"])
        default_branch = repository_data.get("default_branch")
        if not isinstance(default_branch, str) or not default_branch:
            raise ContractError("repository default branch observation is incomplete")
        policy_path = self.standing_authority.get("policy_path")
        if not isinstance(policy_path, str) or not policy_path or policy_path.startswith("/") or ".." in policy_path.split("/"):
            raise ContractError("standing authority policy path is invalid")
        policy_data = self._json(["gh", "api", f"repos/{repository}/contents/{policy_path}?ref={default_branch}"])
        if policy_data.get("encoding") != "base64" or not isinstance(policy_data.get("content"), str):
            raise ContractError("default-branch policy content is incomplete")
        try:
            policy = load_strict(base64.b64decode(policy_data["content"].replace("\n", ""), validate=True))
        except (ValueError, TypeError) as exc:
            raise ContractError("default-branch policy content is invalid") from exc
        policy_digest = digest(policy)
        authority_path = self.standing_authority.get("authority_path")
        if not isinstance(authority_path, str) or not authority_path or authority_path.startswith("/") or ".." in authority_path.split("/"):
            raise ContractError("standing authority path is invalid")
        authority_data = self._json(["gh", "api", f"repos/{repository}/contents/{authority_path}?ref={default_branch}"])
        if authority_data.get("encoding") != "base64" or not isinstance(authority_data.get("content"), str):
            raise ContractError("default-branch standing authority is incomplete")
        try:
            observed_authority = load_strict(base64.b64decode(authority_data["content"].replace("\n", ""), validate=True))
        except (ValueError, TypeError) as exc:
            raise ContractError("default-branch standing authority is invalid") from exc
        observed_authority_digest = digest(observed_authority)
        graph_data = self._json([
            "gh", "api", "graphql",
            "-f", "query=query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){pullRequest(number:$number){reviewThreads(first:100){nodes{isResolved}pageInfo{hasNextPage}}}}}",
            "-F", f"owner={owner}", "-F", f"name={name}", "-F", f"number={pr_number}",
        ])
        if graph_data.get("errors"):
            raise ContractError("pull-request observation returned GraphQL errors")
        pull_request = graph_data.get("data", {}).get("repository", {}).get("pullRequest", {})
        threads = pull_request.get("reviewThreads", {})
        if not isinstance(threads.get("nodes"), list) or not isinstance(threads.get("pageInfo"), dict):
            raise ContractError("review-thread observation is incomplete")
        if threads.get("pageInfo", {}).get("hasNextPage") is not False:
            raise ContractError("review-thread observation is incomplete")
        file_pages = self._json([
            "gh", "api", "--paginate", "--slurp", f"repos/{repository}/pulls/{pr_number}/files?per_page=100",
        ])
        if not isinstance(file_pages, list) or any(not isinstance(page, list) for page in file_pages):
            raise ContractError("changed-path observation is incomplete")
        file_items = [item for page in file_pages for item in page]
        if len(file_items) >= 3000:
            raise ContractError("changed-path observation reached the GitHub files API limit")
        changed_paths: list[str] = []
        for item in file_items:
            if not isinstance(item, dict):
                raise ContractError("changed-path observation is invalid")
            changed_paths.append(item.get("filename"))
            if item.get("status") == "renamed":
                changed_paths.append(item.get("previous_filename"))
        if any(not isinstance(path, str) or not path for path in changed_paths):
            raise ContractError("changed-path observation is invalid")
        review_threads_closed = all(item.get("isResolved") is True for item in threads.get("nodes", []))
        reviews_clear = pr.get("reviewDecision") not in {"CHANGES_REQUESTED", "REVIEW_REQUIRED"}
        checks = pr.get("statusCheckRollup") or []
        conclusions = {str(item.get("conclusion") or item.get("state") or item.get("status") or "").upper() for item in checks}
        checks_pass = all(conclusion == "SUCCESS" for conclusion in conclusions)
        now = datetime.now(timezone.utc)
        approved = datetime.fromisoformat(str(self.standing_authority.get("approved_at", "")).replace("Z", "+00:00"))
        expires = datetime.fromisoformat(str(self.standing_authority.get("expires_at", "")).replace("Z", "+00:00"))
        authority_current = (
            self.standing_authority.get("enabled") is True
            and observed_authority_digest == digest(self.standing_authority)
            and self.standing_authority.get("repository") == repository
            and self.standing_authority.get("default_branch") == default_branch
            and approved <= now <= expires
        )
        control_ref = f"refs/heads/delivery-control/{self.mission_id}"
        control_ref_data = self._json(["gh", "api", f"repos/{repository}/git/ref/heads/delivery-control/{self.mission_id}"])
        control_commit = control_ref_data.get("object", {}).get("sha")
        if not isinstance(control_commit, str) or len(control_commit) != 40:
            raise ContractError("Mission Control ref observation is incomplete")
        control_data = self._json(["gh", "api", f"repos/{repository}/contents/mission.yml?ref={control_commit}"])
        if control_data.get("encoding") != "base64" or not isinstance(control_data.get("content"), str):
            raise ContractError("Mission Control record observation is incomplete")
        try:
            control = load_strict(base64.b64decode(control_data["content"].replace("\n", ""), validate=True))
        except (ValueError, TypeError) as exc:
            raise ContractError("Mission Control record is invalid") from exc
        ContractRegistry.load(Path(__file__).resolve().parents[2] / "contracts" / "registry.yml").validate(
            "mission", control,
        )
        _validate_remote_mission(control, now)
        chain_control = control
        chain_commit = control_commit
        if chain_control["revision"] > 512:
            raise ContractError("Mission Control history exceeds the bounded replay limit")
        while chain_control["revision"] > 1:
            commit_data = self._json(["gh", "api", f"repos/{repository}/git/commits/{chain_commit}"])
            parents = commit_data.get("parents")
            if (
                not isinstance(parents, list)
                or len(parents) != 1
                or not isinstance(parents[0], dict)
                or not isinstance(parents[0].get("sha"), str)
            ):
                raise ContractError("Mission Control prior commit observation is incomplete")
            prior_commit = parents[0]["sha"]
            prior_data = self._json(["gh", "api", f"repos/{repository}/contents/mission.yml?ref={prior_commit}"])
            if prior_data.get("encoding") != "base64" or not isinstance(prior_data.get("content"), str):
                raise ContractError("Mission Control prior record observation is incomplete")
            try:
                prior_control = load_strict(base64.b64decode(prior_data["content"].replace("\n", ""), validate=True))
            except (ValueError, TypeError) as exc:
                raise ContractError("Mission Control prior record is invalid") from exc
            ContractRegistry.load(Path(__file__).resolve().parents[2] / "contracts" / "registry.yml").validate(
                "mission", prior_control,
            )
            if chain_control["prior_digest"] != digest(prior_control) or prior_control["revision"] != chain_control["revision"] - 1:
                raise ContractError("Mission Control prior chain does not match")
            current_time = datetime.fromisoformat(chain_control["updated_at"].replace("Z", "+00:00"))
            prior_time = datetime.fromisoformat(prior_control["updated_at"].replace("Z", "+00:00"))
            if prior_time > current_time:
                raise ContractError("Mission Control prior chronology is invalid")
            chain_control = prior_control
            chain_commit = prior_commit
        controller = control.get("controller", {})
        candidate = control.get("candidate", {})
        builder_session_ids = candidate.get("builder_session_ids")
        aggregate = control.get("aggregate", {})
        authority = control.get("authority", {})
        control_current = (
            control.get("mission_id") == self.mission_id
            and control.get("control_ref") == control_ref
            and controller.get("generation") == self.expected_controller_generation
            and candidate.get("head_sha") == pr.get("headRefOid")
            and {field: candidate.get(field) for field in self.expected_candidate} == self.expected_candidate
            and candidate.get("tree_sha") == observed_tree
            and candidate.get("base_sha") == pr.get("baseRefOid")
            and isinstance(builder_session_ids, list)
            and bool(builder_session_ids)
            and all(isinstance(item, str) and item for item in builder_session_ids)
            and authority.get("envelope_digest") == self.expected_envelope_digest
            and aggregate.get("phase") in {"pr-ready", "handback"}
            and aggregate.get("status") == "running"
            and aggregate.get("terminal_outcome") is None
            and aggregate.get("wake_guard") is None
            and not control.get("required_actions")
            and not any(item.get("status") != "resolved" for item in control.get("interrupts", []))
            and not any(item.get("status") != "closed" for item in control.get("findings", []))
        )
        merge_commit = pr.get("mergeCommit") or {}
        merged = bool(pr.get("mergedAt")) or pr.get("state") == "MERGED"
        return {
            "repository": repository,
            "pr_number": pr_number,
            "base_ref": pr.get("baseRefName"),
            "default_branch": default_branch,
            "default_branch_policy_digest": policy_digest,
            "head_sha": observed_head,
            "tree_sha": observed_tree,
            "candidate": {field: candidate.get(field) for field in self.expected_candidate},
            "merge_method": self.merge_method,
            "mergeable": pr.get("mergeable") == "MERGEABLE" and pr.get("mergeStateStatus") == "CLEAN" and pr.get("isDraft") is False,
            "checks_pass": checks_pass,
            "pr_open": pr.get("state") == "OPEN" and pr.get("isDraft") is False,
            "review_threads_closed": review_threads_closed,
            "reviews_clear": reviews_clear,
            "standing_authority_current": authority_current,
            "standing_authority_digest": observed_authority_digest,
            "default_branch_policy_current": policy_digest == self.standing_authority.get("policy_digest"),
            "kill_switch_enabled": self.standing_authority.get("enabled") is True,
            "generation_current": control_current,
            "findings_closed": not any(
                item.get("status") != "closed" for item in control.get("findings", [])
            ),
            "required_actions_closed": not bool(control.get("required_actions")),
            "controller_generation": controller.get("generation"),
            "coordinator_session_id": controller.get("session_id"),
            "builder_session_ids": builder_session_ids,
            "control_ref": control_ref,
            "control_commit": control_commit,
            "control_digest": digest(control),
            "changed_paths": sorted(changed_paths),
            "merged": merged,
            "merged_head_sha": pr.get("headRefOid") if merged else None,
            "merged_by": (pr.get("mergedBy") or {}).get("login") if merged else None,
            "merge_commit_sha": merge_commit.get("oid") if merged else None,
            "evidence_locator": "github:" + str(pr.get("url")),
            "host_evidence": {
                "pull_request": pr,
                "head_commit": {"sha": observed_head, "tree_sha": observed_tree},
                "review_threads": threads,
                "changed_paths": sorted(changed_paths),
                "mission_control": {"ref": control_ref, "commit": control_commit, "digest": digest(control)},
                "repository": {"default_branch": default_branch},
                "default_branch_policy": {
                    "path": policy_path,
                    "blob_sha": policy_data.get("sha"),
                    "digest": policy_digest,
                },
                "standing_authority": {
                    "path": authority_path,
                    "blob_sha": authority_data.get("sha"),
                    "digest": observed_authority_digest,
                },
            },
        }

    def merge(
        self,
        repository: str,
        pr_number: int,
        expected_head_sha: str,
        merge_method: str,
        operation_id: str,
    ) -> dict[str, Any]:
        if not re.fullmatch(r"op-merge-[0-9a-f]{64}", operation_id):
            raise ContractError("merge operation ID is invalid")
        # claim_operation durably binds this ID before GitHub's expected-head
        # compare-and-set call; the merge endpoint has no idempotency field.
        try:
            result = self.runner([
                "gh", "api", "--method", "PUT",
                f"repos/{repository}/pulls/{pr_number}/merge",
                "-f", f"sha={expected_head_sha}",
                "-f", f"merge_method={merge_method}",
            ], text=True, capture_output=True, check=False, timeout=60)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError("GitHub merge response timed out") from exc
        if result.returncode:
            raise ContractError(f"GitHub merge request failed with exit {result.returncode}")
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise TimeoutError("GitHub merge response was not authoritative JSON") from exc
        if response.get("merged") is not True:
            raise ContractError("GitHub declined the expected-head merge")
        return response

    def claim_operation(
        self,
        repository: str,
        pr_number: int,
        operation_id: str,
        decision_digest: str,
        expected_head_sha: str,
    ) -> bool:
        del pr_number
        if decision_digest != "sha256:" + operation_id.removeprefix("op-merge-"):
            raise ContractError("merge-operation intent does not bind the decision digest")
        operation_ref = f"refs/heads/delivery-operations/{operation_id}"
        marker = {
            "decision_digest": decision_digest,
            "expected_head_sha": expected_head_sha,
            "operation_id": operation_id,
            "operation_ref": operation_ref,
            "schema_version": 1,
            "status": "intent_committed",
        }
        ContractRegistry.load(Path(__file__).resolve().parents[2] / "contracts" / "registry.yml").validate(
            "merge-operation-intent", marker,
        )
        result = self.runner([
            "gh", "api", "--method", "POST", f"repos/{repository}/git/refs",
            "-f", f"ref={operation_ref}", "-f", f"sha={expected_head_sha}",
        ], text=True, capture_output=True, check=False, timeout=60)
        if result.returncode not in {0, 1}:
            raise ContractError(f"merge-operation atomic claim failed with exit {result.returncode}")
        created = result.returncode == 0
        observed = self._json([
            "gh", "api", f"repos/{repository}/git/ref/heads/delivery-operations/{operation_id}",
        ])
        if observed.get("ref") != operation_ref or observed.get("object", {}).get("sha") != expected_head_sha:
            raise ContractError("merge-operation atomic claim readback mismatch")
        return created

    def operation_claimed(self, repository: str, operation_id: str, expected_head_sha: str) -> bool:
        operation_ref = f"refs/heads/delivery-operations/{operation_id}"
        result = self.runner([
            "gh", "api", f"repos/{repository}/git/ref/heads/delivery-operations/{operation_id}",
        ], text=True, capture_output=True, check=False, timeout=60)
        if result.returncode == 1:
            return False
        if result.returncode:
            raise ContractError(f"merge-operation claim observation failed with exit {result.returncode}")
        try:
            observed = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ContractError("merge-operation claim observation returned malformed JSON") from exc
        if observed.get("ref") != operation_ref or observed.get("object", {}).get("sha") != expected_head_sha:
            raise ContractError("merge-operation claim observation mismatch")
        return True
