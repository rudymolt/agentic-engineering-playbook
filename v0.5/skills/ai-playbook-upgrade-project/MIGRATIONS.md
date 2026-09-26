# Transition to the public V0.5 edition

The private V0.4.2 release is the source for this public V0.5 edition. Some V0.4.2 projects record `playbook_version: V0.4.0` because the installed template version is an edition stamp; both V0.4.0 and V0.4.2 are accepted as V0.4 starting stamps. A V0.3 project first uses the private migration bridge to V0.4. No direct public V0.3 upgrade is provided.

## Preparation

Pin a public V0.5 release tag in a separate stable checkout. Keep the private checkout available until each project has completed the transition. Confirm the project has a clean or intentionally preserved working tree and committed `.playbook-base/` pristine files. Run the skill's read-only plan before applying changes.

## Safe transition

```bash
python3 PUBLIC_STABLE_CHECKOUT/v0.5/scripts/upgrade-project.py PROJECT --apply-safe
python3 PUBLIC_STABLE_CHECKOUT/v0.5/scripts/compute-status.py PROJECT --check
```

The upgrader uses the project's recorded pristine bases to three-way merge managed files. It must preserve project-written content, retarget active playbook instructions from the old checkout to the public checkout, and produce a no-change second run. It updates the state and cadence file references without discarding project counters, decisions, or timestamps. A conflict, edited/missing base, or remaining old checkout reference produces `manual review:` and blocks the V0.5 stamp. Resolve the exact file, then rerun; use `--adopt-current FILE` only after accepting that file's final content.

After a clean run, verify that project `CLAUDE.md` and project `AGENTS.md` point at the public stable checkout, `.playbook-state.yml` says `V0.5.0`, `prereqs_required: true`, and the second run changes nothing. Run stage 00's cold path before resuming feature work. The project owner decides when to remove the old checkout; the upgrade tool does not delete it.

## Development checkout

Use a second checkout of public `main` for changes. Keep application projects pointed at the stable release checkout until a later upgrade is deliberately run. Do not retarget a project to the moving development checkout.
