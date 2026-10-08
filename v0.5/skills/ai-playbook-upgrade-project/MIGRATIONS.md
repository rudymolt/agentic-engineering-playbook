# Matt v1.3.1 domain glossary migration

This same-edition migration is detected from filenames and provenance even when
`playbook_version` already says V0.5.0. Complete it before switching Matt's skills.
`DESIGN-GLOSSARY.md` and `design-glossary/` remain the separate UI vocabulary.

## Preview and managed root glossary

Run the read-only preview from the destination pinned release checkout:

```bash
python3 PUBLIC_STABLE_CHECKOUT/v0.5/scripts/upgrade-project.py PROJECT --plan-glossary
```

Inspect the project's definitions, active domain links, tracker configuration,
and any broader custom material in CONTEXT.md. Preserve vocabulary verbatim;
split broader material only through a reviewed project edit. Show the rename and
any manual items in the upgrade skill's existing approval step.

For a managed root glossary with a verified pristine base, `--apply-safe` moves
CONTEXT.md and its `.playbook-base/` snapshot to GLOSSARY.md and transfers the
provenance entry. The normal three-way merge then updates template wording and
managed entry-file references. Unrelated state and user definitions are retained.
Missing/edited bases, both-name collisions, symlinks or unknown provenance stop
before ordinary upgrade work. Restore the recorded base from version control;
never replace a missing base with guessed content.

A temporary `.playbook-base/.glossary-migration.json` records the original bytes
while the rename is in progress. Keep it local while interrupted; rerun the same
command to finish. Recovery accepts only the recorded before/after bytes. If a
file changed in the meantime, reconcile it against the receipt with the project
owner before retrying. Successful completion removes the receipt. Rollback uses
the pre-upgrade project checkpoint, including state, bases and installed skills.

## User-owned maps, broader context and filename collisions

These are tier 3. The upgrader deliberately does not infer map ownership or domain
boundaries from prose. Review the map and every referenced context with the owner:

1. Preserve the original files in version control. Move CONTEXT-MAP.md to
   GLOSSARY-MAP.md and each mapped CONTEXT.md to its sibling GLOSSARY.md. If both
   names exist, reconcile their definitions into one authoritative glossary;
   retain broader custom material in an appropriate project document.
2. Update the map links and active consumers: AGENTS.md, CLAUDE.md,
   docs/agents/domain.md, active planning links and any custom domain loaders.
   Keep tracker labels, ADRs, model choices and accepted decisions intact.
3. If a managed root CONTEXT.md was manually renamed, leave its recorded base
   and provenance intact, then run `--apply-safe --adopt-current GLOSSARY.md`
   after the owner accepts the new file. This explicit adoption transfers the
   old record and resets the base to the current template after review. A missing
   or edited old base still needs restoration; the adoption flag does not bypass it.
   Mapped files without managed provenance remain project-owned and need no
   invented provenance entries.
4. Run the upgrade again, require no unresolved review and a no-change second
   run, then run the cold capability check. For a mapped project the domain
   prerequisite is GLOSSARY-MAP.md plus all resolved mapped glossaries.

Matt v1.3.1 removed the dedicated merge-conflict skill without a replacement.
Old installations may retain the file; remove or archive it only as an explicit
host cleanup after checking local edits. New conflict work uses the procedure in
`91-delegation-track.md`; no default command depends on the retired skill.

---

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
