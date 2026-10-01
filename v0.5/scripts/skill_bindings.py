"""Versioned job eligibility and report-only resolution, never a launcher."""

from copy import deepcopy
import hashlib
import importlib.util
import os
from pathlib import Path, PurePosixPath
import re

from playbook_config import ConfigError, strict_json
from playbook_state import parse_top_level_map
from upstream_registry import load as load_registry


ROOT = Path(__file__).resolve().parent.parent
VERSION = 1
JOBS = {
    "alignment": {
        "owner": "01", "stage": "01-align.md",
        "inputs": ["user goal", "project context", "constraints", "non-goals"],
        "outputs": ["settled terminology", "decisions", "human-confirmed alignment"],
        "effects": ["repository reads", "alignment documents and ADRs"],
        "forms": ["single", "ordered composition", "adapter", "manual"],
    },
    "specification": {
        "owner": "03", "stage": "03-spec.md",
        "inputs": ["confirmed alignment", "context and ADRs"],
        "outputs": ["specification", "acceptance criteria", "confirmed test seams"],
        "effects": ["repository reads", "specification documents"],
        "forms": ["single", "adapter", "manual"],
    },
    "implementation": {
        "owner": "07", "stage": "07-implementation-tdd.md",
        "inputs": ["approved specification", "approved slice", "confirmed test seams"],
        "outputs": ["failing test evidence", "passing test evidence", "slice implementation"],
        "effects": ["scoped source and test edits", "approved verification commands"],
        "forms": ["single", "adapter", "manual"],
    },
    "code_review": {
        "owner": "08", "stage": "08-review.md",
        "inputs": ["candidate diff", "approved specification", "independent verifier identity"],
        "outputs": ["standards findings", "spec-fidelity findings", "evidence", "verdict"],
        "effects": ["repository reads", "verification commands", "review evidence output"],
        "forms": ["single", "adapter", "manual"],
    },
    "application_qa": {
        "owner": "09", "stage": "09-qa.md",
        "inputs": ["candidate application", "behavior contract", "existing verification route"],
        "outputs": ["browser evidence", "defect reproductions", "verdict"],
        "effects": ["repository reads", "browser verification", "review evidence output"],
        "forms": ["project route", "manual"],
    },
}
AUTHORITY = ["human confirmation", "tests", "independent review/QA evidence", "commits",
             "launches", "permission boundaries", "configuration", "maintenance opt-in"]
for job_name, job_contract in JOBS.items():
    job_contract["fallback"] = "manual: stage " + job_contract["owner"] + " " + job_contract["stage"]
    job_contract["prohibited_effects"] = ["unowned commits or launches", "configuration changes", "self-upgrade", "permission expansion"]
PREFIXES = {"mattpocock-skills": "Matt Pocock", "gstack": "gstack"}
FORBIDDEN = {"product or source edits", "commits", "configuration changes", "self-upgrade"}
SPEC = importlib.util.spec_from_file_location("binding_upstream_compatibility", ROOT / "scripts/check-upstream-compatibility.py")
COMPATIBILITY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPATIBILITY)


def fingerprint(source):
    return hashlib.sha256(Path(source).read_bytes()).hexdigest()


class CustomEvidenceError(ConfigError):
    pass


def portable_identity(identity):
    return (isinstance(identity, str)
            and re.fullmatch(r"[a-z0-9_-]+:[A-Za-z0-9._/-]+", identity) is not None
            and ".." not in identity and "//" not in identity
            and not identity.split(":", 1)[1].startswith("/"))


def validate_bindings(value):
    if (not isinstance(value, dict) or set(value) != {"contract_version", "jobs"}
            or type(value["contract_version"]) is not int or value["contract_version"] != VERSION
            or not isinstance(value["jobs"], dict) or set(value["jobs"]) != set(JOBS)):
        raise ConfigError("Unsupported job contract; preserve choices and use a compatible editor.")
    for job, bindings in value["jobs"].items():
        if not isinstance(bindings, list) or not bindings or (job != "alignment" and len(bindings) != 1):
            raise ConfigError("Only alignment permits ordered composition; retain one binding for each other job.")
        seen = set()
        for binding in bindings:
            if (not isinstance(binding, dict) or set(binding) != {"source_id", "source_sha256", "contract_sha256"}
                    or not portable_identity(binding["source_id"])
                    or re.fullmatch(r"[0-9a-f]{64}", str(binding["source_sha256"])) is None
                    or re.fullmatch(r"[0-9a-f]{64}", str(binding["contract_sha256"])) is None
                    or binding["source_id"] in seen):
                raise ConfigError("Bindings require unique logical source identities and exact fingerprints, not names or host paths.")
            seen.add(binding["source_id"])
    return value


class JobBindings:
    def __init__(self, project, *, installed=None, manifest=None, registry=None, custom_dir=None):
        self.project = Path(project)
        self.registry = registry or load_registry()
        self.manifest = Path(manifest) if manifest else ROOT / "upstream-integrations.json"
        self.installed = installed if installed is not None else self._installed()
        self.live_inventory = installed is None
        self.rejections = []
        self.custom_dir = Path(custom_dir) if custom_dir is not None else Path.home() / ".config/ai-playbook/custom-skills"
        self._check_custom_store()

    def _check_custom_store(self):
        try:
            locations = [self.custom_dir.resolve()] + [(self.custom_dir / name).resolve()
                         for name in ("bindings.json", "approvals.json", "evidence")]
            project = self.project.resolve()
        except (OSError, RuntimeError):
            raise ConfigError("Custom binding/audit storage cannot be resolved. Restore an external machine-local store.") from None
        if locations[0].is_relative_to(project):
            raise ConfigError("Custom bindings and retained audits require a machine-local directory outside the shareable project. "
                              "Choose an external --custom-bindings-dir; do not copy, track or publish that store.")
        for location in locations[1:]:
            if location.is_relative_to(project):
                raise ConfigError("Custom binding/audit storage points into the shareable project. "
                                  "Restore an external machine-local store; do not copy, track or publish it.")
        for name in ("bindings.json", "approvals.json"):
            path = self.custom_dir / name
            if path.exists():
                self._check_single_link(path.stat())

    def _check_single_link(self, metadata):
        if metadata.st_nlink != 1:
            raise CustomEvidenceError("separate single-link local inventory, approvals and retained evidence; "
                                      "remove published aliases and restore independent external files before retrying")

    def _read_custom_file(self, path):
        if path.resolve().is_relative_to(self.project.resolve()):
            raise CustomEvidenceError("independently retained evidence outside the shareable project")
        with path.open("rb") as stream:
            self._check_single_link(os.fstat(stream.fileno()))
            return stream.read()

    def _installed(self):
        found = {}
        for skill in self.registry.skills.values():
            if skill.status != "current" or not skill.manifest_key:
                continue
            package = self.registry.packages[skill.package]
            paths = []
            for base in (self.project, Path.home()):
                for root in package.install.get("roots", []):
                    directory = base / root
                    paths.extend(directory.glob(f"{skill.name}/SKILL.md"))
                    paths.extend(directory.glob(f"*/{skill.name}/SKILL.md"))
                    paths.extend(directory.glob(f"gstack-{skill.name}/SKILL.md"))
            found[f"{skill.package}:{skill.name}"] = sorted(set(path.resolve() for path in paths))
        return found

    def _candidate(self, identity, source, form, label, invocation, provenance=None):
        from playbook_config import encoded
        if not portable_identity(identity):
            raise ConfigError("Canonical portable source identity required; repair the local inventory "
                              "or stage-owned selection and reload without rewriting saved choices.")
        provenance = provenance or {"kind": "playbook-" + form, "source": "Playbook stage"}
        evidence = {"version": VERSION, "jobs": JOBS, "authority": AUTHORITY,
                    "provenance": provenance, "invocation": invocation}
        return {"binding": {"source_id": identity, "source_sha256": fingerprint(source),
                            "contract_sha256": hashlib.sha256(encoded(evidence)).hexdigest()},
                "label": label, "form": form, "invocation": invocation, "provenance": provenance}

    def defaults(self):
        return {"contract_version": VERSION, "jobs": {
            job: [self.options(job)[0]["binding"]] for job in JOBS}}

    def _reject(self, identity, reason):
        rejection = {"source_id": identity if portable_identity(identity) else "custom:unresolved", "reason": reason}
        if rejection not in self.rejections:
            self.rejections.append(rejection)

    def options(self, job):
        if job not in JOBS:
            raise ConfigError("Unknown Playbook job; select one of the five versioned contracts.")
        contract = JOBS[job]
        if self.live_inventory:
            self.installed = self._installed()
        source = ROOT / "10-process" / contract["stage"]
        manual = self._candidate(f"playbook:{job}-manual", source, "manual",
                                 f"(Playbook manual) {job}", f"stage {contract['owner']}: {contract['stage']}")
        choices = [manual]
        if job != "application_qa":
            choices.append(self._candidate(f"playbook:{job}-adapter", source, "adapter",
                                          f"(Playbook adapter) {job}", manual["invocation"]))
        if job == "alignment":
            for suffix, axis in (("context", "facts vs decisions"), ("decisions", "confirmation gate")):
                choices.append(self._candidate(f"playbook:alignment-{suffix}", source, "adapter",
                                              f"(Playbook adapter) alignment {suffix}", manual["invocation"] + "; " + axis))
        if job == "code_review":
            for skill in self.registry.skills.values():
                if skill.status == "current" and skill.manifest_key == "code-review":
                    identity = f"{skill.package}:{skill.name}"
                    paths = self.installed.get(identity, [])
                    if len(paths) != 1:
                        self._reject(identity, "source collision" if paths else "not installed")
                        continue
                    candidate = self._embedded(job, skill, paths[0])
                    if candidate:
                        choices.append(candidate)
        if job == "application_qa":
            candidate = self._project_qa()
            if candidate:
                choices.append(candidate)
        choices.extend(self._custom_options(job))
        return choices

    def _custom_options(self, job):
        choices = []
        try:
            self._check_custom_store()
            local = self._custom_inventory(job)
            for identity, binding in local["sources"].items():
                try:
                    if (not portable_identity(identity)
                            or identity.split(":", 1)[0] not in {"custom", "project"}
                            or not isinstance(binding, dict) or set(binding) != {"source", "audits"}
                            or not isinstance(binding["audits"], dict)):
                        raise ConfigError("canonical portable identity and local binding")
                    if job not in binding["audits"]:
                        continue
                    choices.append(self._custom_candidate(identity, binding, job))
                except (ConfigError, OSError, UnicodeError, KeyError, TypeError, ValueError, RuntimeError) as error:
                    requirement = str(error) if isinstance(error, CustomEvidenceError) else "readable separate local binding, approval and evidence"
                    self._reject(identity,
                        "Unmet requirement: " + requirement + ". Required: exact-source independent retained audit, job inputs/outputs, "
                        "owner, invocation, form, permitted effects and retained authority; "
                        "restore the local binding and stage-owned evidence or explicitly select " + JOBS[job]["fallback"])
        except (ConfigError, OSError, UnicodeError, KeyError, TypeError, ValueError, RuntimeError) as error:
            requirement = str(error) if isinstance(error, CustomEvidenceError) else "local binding schema; repair local inventory"
            self._reject("custom:unresolved", "Unmet " + requirement + "; or explicitly select " + JOBS[job]["fallback"])
        return choices

    def _custom_inventory(self, job):
        inventory = self.custom_dir / "bindings.json"
        local = strict_json(self._read_custom_file(inventory).decode()) if inventory.exists() else {"version": VERSION, "sources": {}}
        if (set(local) != {"version", "sources"} or type(local["version"]) is not int
                or local["version"] != VERSION or not isinstance(local["sources"], dict)):
            raise ConfigError("local binding schema")
        approvals = self.custom_dir / "approvals.json"
        if approvals.exists():
            approvals = strict_json(self._read_custom_file(approvals).decode())
            if (set(approvals) != {"version", "audits"} or type(approvals["version"]) is not int
                    or approvals["version"] != VERSION or not isinstance(approvals["audits"], dict)):
                raise ConfigError("local approval schema")
            canonical = {}
            for audit, approval in approvals["audits"].items():
                identity = approval.get("source_id") if isinstance(approval, dict) else None
                if isinstance(identity, str) and identity.startswith("project:") and approval.get("job") == job:
                    if identity in canonical:
                        raise ConfigError("project audit collision")
                    canonical[identity] = {"source": identity.split(":", 1)[1], "audits": {job: audit}}
            for identity, binding in canonical.items():
                local["sources"].setdefault(identity, binding)
        return local

    def _custom_candidate(self, identity, binding, job):
        locator = binding["source"]
        if not isinstance(locator, str) or not locator:
            raise CustomEvidenceError("source locator")
        if identity.startswith("project:"):
            if locator != identity.split(":", 1)[1]:
                raise CustomEvidenceError("canonical project source")
            source = self._owned(locator)
        else:
            source = Path(locator)
            if not source.is_absolute() or not source.is_file():
                raise CustomEvidenceError("local source resolution")
        audit = binding["audits"][job]
        if not isinstance(audit, str) or re.fullmatch(r"[a-z0-9_-]+", audit) is None:
            raise CustomEvidenceError("retained audit locator")
        approvals = strict_json(self._read_custom_file(self.custom_dir / "approvals.json").decode())
        if (set(approvals) != {"version", "audits"} or type(approvals["version"]) is not int
                or approvals["version"] != VERSION):
            raise CustomEvidenceError("stage-owned audit inventory")
        approval = approvals["audits"][audit]
        contract = JOBS[job]
        resolution = hashlib.sha256(source.resolve().as_posix().encode()).hexdigest()
        if (set(approval) != {"source_id", "job", "owner", "revision", "evidence_sha256", "resolution_sha256"}
                or approval["source_id"] != identity or approval["job"] != job
                or approval["owner"] != contract["owner"] or approval["resolution_sha256"] != resolution
                or not isinstance(approval["revision"], str)
                or re.fullmatch(r"[a-z0-9_-]+", approval["revision"]) is None):
            raise CustomEvidenceError("stage-owned exact-resolution audit approval")
        proof_path = self.custom_dir / "evidence" / (audit + ".json")
        if proof_path.resolve().is_relative_to(self.project.resolve()):
            raise CustomEvidenceError("independently retained evidence outside the shareable project")
        proof_bytes = self._read_custom_file(proof_path)
        proof_sha = hashlib.sha256(proof_bytes).hexdigest()
        if approval["evidence_sha256"] != proof_sha:
            raise CustomEvidenceError("retained evidence fingerprint")
        proof = strict_json(proof_bytes.decode())
        invocation = identity + (" --report-only" if job in {"code_review", "application_qa"} else "")
        expected = {"contract_version": VERSION, "source_id": identity, "job": job,
                    "owner": contract["owner"], "source_sha256": fingerprint(source),
                    "inputs": contract["inputs"], "outputs": contract["outputs"],
                    "prohibited_effects": contract["prohibited_effects"], "retained_authority": AUTHORITY,
                    "invocation": invocation, "form": "project route" if job == "application_qa" else "single",
                    "report_only": job in {"code_review", "application_qa"}, "verdict": "pass", "independent": True}
        if set(proof) not in (set(expected) | {"effects"}, set(expected) | {"effects", "embedded_source_id"}):
            raise CustomEvidenceError("complete exact job contract fields")
        for key, value in expected.items():
            if type(proof[key]) is not type(value) or proof[key] != value:
                raise CustomEvidenceError("exact job contract field " + key)
        if (not isinstance(proof["effects"], list) or not proof["effects"]
                or any(not isinstance(effect, str) for effect in proof["effects"])
                or not set(proof["effects"]) <= set(contract["effects"])):
            raise CustomEvidenceError("permitted job effects")
        label = "(Custom) " + identity.split(":", 1)[1]
        if "embedded_source_id" in proof:
            raise CustomEvidenceError("custom embedded forms are unsupported; select the existing uniquely installed S3 source binding")
        qa_route = None
        if job == "application_qa":
            qa_route = self._project_qa()
            if (qa_route is None or source.resolve() != (self.project / qa_route["invocation"]).resolve()):
                raise CustomEvidenceError("existing stage-owned QA selection and qualification")
            label = qa_route["label"]
        return self._candidate(identity, source, expected["form"], label, invocation,
                               {"kind": "custom-retained-audit", "evidence_sha256": proof_sha,
                                "audit_id": audit, "audit_revision": approval["revision"],
                                "qa_route": qa_route})

    def invocation_source(self, saved, job, owner, identity):
        if job not in JOBS or owner != JOBS[job]["owner"]:
            raise ConfigError("Only the owning stage may resolve a custom invocation source.")
        routes = self.resolve(saved, job)
        if not any(route["binding"]["source_id"] == identity
                   and route["provenance"]["kind"] == "custom-retained-audit" for route in routes):
            raise ConfigError("Custom invocation requires the exact eligible saved binding.")
        local = self._custom_inventory(job)
        binding = local["sources"][identity]
        candidate = self._custom_candidate(identity, binding, job)
        if not any(route["binding"] == candidate["binding"] for route in routes):
            raise ConfigError("Custom resolution changed before invocation; requalify and preview explicitly.")
        return self._owned(binding["source"]) if identity.startswith("project:") else Path(binding["source"]).resolve()

    def _embedded(self, job, skill, source):
        try:
            decision = COMPATIBILITY.evaluate(skill.manifest_key, Path(source), "manual: stage " + JOBS[job]["owner"], self.manifest)
            entry = COMPATIBILITY.load_manifest(self.manifest)["integrations"].get(skill.manifest_key, {})
        except COMPATIBILITY.ManifestError as error:
            raise ConfigError("Invalid exact-source compatibility evidence; reconcile before binding.") from error
        contract = JOBS[job]
        package = self.registry.packages[skill.package]
        eligible = (decision.may_invoke and skill.package in PREFIXES and package.kind == "upstream"
                    and entry.get("upstream", "") in package.source
                    and set(contract["outputs"]) <= set(entry.get("required_outputs", []))
                    and set(entry.get("permitted_side_effects", [])) <= set(contract["effects"])
                    and FORBIDDEN <= set(entry.get("prohibited_side_effects", [])))
        if not eligible:
            self._reject(f"{skill.package}:{skill.name}", decision.reason + "; job contract required")
            return None
        return self._candidate(f"{skill.package}:{skill.name}", source, "single",
                               f"({PREFIXES[skill.package]}) {skill.name}", decision.embedded_invocation,
                               {"kind": "unmodified-upstream", "collection": package.source,
                                "pin": package.pin, "evidence": entry})

    def _owned(self, locator):
        if not isinstance(locator, str) or not locator or "\\" in locator:
            raise ConfigError("QA evidence requires a project-relative locator.")
        relative = PurePosixPath(locator)
        if relative.is_absolute() or ".." in relative.parts or str(relative) != locator:
            raise ConfigError("QA evidence requires a canonical project-relative locator.")
        source = self.project / locator
        if not source.resolve().is_relative_to(self.project.resolve()) or not source.is_file():
            raise ConfigError("QA route or proof is missing or outside this project.")
        return source

    def _project_qa(self):
        record = self.project / ".playbook-qa-eligibility.json"
        artifact = "eligibility record"
        try:
            if not record.exists():
                return None
            record = self._owned(".playbook-qa-eligibility.json")
            proof = strict_json(record.read_text())
            artifact = "selection state"
            state = (self.project / ".playbook-state.yml").read_text()
            decisions = parse_top_level_map(state, "decisions")
            selected = decisions.get("verification_harness_path")
            if (type(proof["contract_version"]) is not int or proof["contract_version"] != VERSION or proof["owner"] != "09"
                    or proof["route"] != selected or decisions.get("verification_harness_binding") != selected):
                raise ConfigError("QA route must already have stage-owned selection and eligibility evidence.")
            artifact = "skill source"
            source = self._owned(selected + "/SKILL.md")
            source_sha256 = fingerprint(source)
            artifact = "retained evidence"
            evidence = self._owned(proof["evidence"])
            observed = strict_json(evidence.read_text())
            evidence_sha256 = fingerprint(evidence)
            artifact = "skill source"
            if (proof["source_sha256"] != source_sha256 or proof["evidence_sha256"] != evidence_sha256
                    or observed["source_sha256"] != fingerprint(source)
                    or observed["verdict"] != "pass" or observed["independent"] is not True
                    or observed["lifecycle"] != ["Launch", "Doctor", "Drive", "Evidence", "Cleanup"]
                    or not isinstance(observed["outputs"], list) or not isinstance(observed["effects"], list)
                    or not observed["effects"]
                    or set(observed["outputs"]) != set(JOBS["application_qa"]["outputs"])
                    or not set(observed["effects"]) <= set(JOBS["application_qa"]["effects"])):
                raise ConfigError("QA requires retained independent exact-source lifecycle and contract proof.")
            embedded = proof.get("embedded_source_id")
            embedded_choice = None
            if embedded:
                matches = [skill for skill in self.registry.skills.values()
                           if f"{skill.package}:{skill.name}" == embedded and skill.manifest_key == "qa-only"]
                paths = self.installed.get(embedded, [])
                if len(matches) == 1 and len(paths) == 1:
                    artifact = "embedded skill source"
                    embedded_choice = self._embedded("application_qa", matches[0], paths[0])
                if proof.get("mode") != "embedded-report-only" or not embedded_choice:
                    raise ConfigError("Project QA's embedded source failed exact-source report-only compatibility.")
            elif proof.get("mode") != "project-report-only":
                raise ConfigError("QA proof must declare a project-report-only route, not an upstream adaptation.")
            artifact = "eligibility record"
            eligibility_sha256 = fingerprint(record)
            artifact = "retained evidence"
            evidence_sha256 = fingerprint(evidence)
            artifact = "skill source"
            candidate = self._candidate("project:" + selected, source, "project route",
                                        "(Project route) " + selected, selected + "/SKILL.md",
                                        {"kind": "project-route", "eligibility_sha256": eligibility_sha256,
                                         "evidence_sha256": evidence_sha256, "embedded": embedded_choice})
            return candidate
        except (ConfigError, OSError, KeyError, TypeError, UnicodeError) as error:
            error_class = (type(error).__name__ if isinstance(error, OSError) else "invalid qualification")
            self._reject("project:application_qa", "QA " + artifact + ": " + error_class + ". "
                         "Restore readable project-owned QA artifacts and have stage 09 revalidate selection, "
                         "exact-source lifecycle and retained independent contract evidence; otherwise explicitly "
                         "select " + JOBS["application_qa"]["fallback"] + ". No automatic fallback or evidence creation.")
            return None

    def resolve(self, saved, job):
        validate_bindings(saved)
        options = self.options(job)
        routes = []
        for binding in saved["jobs"][job]:
            matches = [option for option in options if option["binding"] == binding]
            if len(matches) != 1:
                if binding["source_id"].startswith(("custom:", "project:")):
                    raise ConfigError("Saved selection unresolved: local binding or exact-source contract evidence is missing, changed or rejected. "
                                      "Restore its own local binding and independently retained stage audit; otherwise explicitly select "
                                      + JOBS[job]["fallback"] + ". No source rewrite or automatic fallback.")
                raise ConfigError("Selected skill is unknown, changed, colliding or incompatible; explicitly edit to the declared manual/adapter fallback or block. A warning is not approval.")
            routes.append({**deepcopy(matches[0]), "source_id": binding["source_id"]})
        if len(routes) > 1 and [route["source_id"] for route in routes] != ["playbook:alignment-context", "playbook:alignment-decisions"]:
            raise ConfigError("Ordered alignment composition requires the stage-owned complementary adapters.")
        return routes

    def dispatch(self, saved, job, owner, invoke):
        if job not in JOBS or owner != JOBS[job]["owner"]:
            raise ConfigError("Only the owning stage may consume this job binding.")
        routes = self.resolve(saved, job)
        result = {"configured": True, "job": job, "owner": owner, "contract_version": VERSION,
                  "routes": routes, "retained_authority": deepcopy(AUTHORITY),
                  "contract": deepcopy(JOBS[job]), "launched": False}
        if invoke is not None:
            for route in routes:
                invoke(route)
        return result
