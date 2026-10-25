# Implementation loop notes

## Read-only Git discovery

Git status can refresh the index even when a source probe is intended to be
read-only. Use `git --no-optional-locks status` for local version observations.
A public provisioner fixture with a Git-managed skill source detected an index
mtime change in its before/after home snapshot; the same snapshot stayed
identical after disabling optional locks. Keep full directory differences
separate from Git ancestry, retained job eligibility and actual invocation.

## Source observation boundaries

Disabling optional Git locks alone does not prevent a repository's configured
fsmonitor helper from executing during status. Process-local fsmonitor
suppression plus disabled optional locks preserved the executable-helper
fixture's home bytes, modes and mtimes without rewriting Git settings. Resolve
complete source-directory aliases before reading, while retaining the literal
`SKILL.md` entry for regular-file checks. Explicit named-location enumeration
keeps cyclic, dangling and access-denied sources visible across Python glob
versions; per-source failures must also survive live catalog refresh so an
inaccessible competitor cannot become a uniquely eligible saved selection.

## Complete supporting-directory observation

A readable entrypoint does not prove its supporting directories can be
enumerated. Recursive glob can suppress a permission failure and return a
partial file set. Explicit directory iteration and lstat propagate that failure
at the existing complete-tree reader. A public CLI fixture with search-only
access to `agents/` proves its metadata and known YAML file still exist while
listing fails: both supported local Python interpreters now report the source
unknown/blocked, then exact after directory access is restored. Preserve the
same failure semantics for installation, retained content and recovery reads.

## Reachable exact-source recovery

A helper inside the absent checkout cannot recover that checkout. Explicitly
exporting the same provenance/state/bundle readers as a portable Python zipapp
keeps recovery reachable without another release resolver. Public CLI fixtures
run that launcher with no Python import path, ignore a newer remote release,
and verify the recorded annotated tag object and commit before activation.
Separate temporary acquisition from the published cache, then delegate to the
validated release's existing provisioner. Offline cache replay and conflicting
project edits retain the existing adoption and customization boundaries.

## Source caches and portable adoption

Bootstrap must filter runtime caches at the same installation boundary as its
managed-file inventory. A public fixture explicitly compiles a source skill
between bootstrap calls, crosses a clock tick, then compares the whole consumer
bytes/modes/mtimes snapshot and existing ignore-file mtime. This exposes cache-driven
state recomputation even when ordinary runs suppress bytecode. Keep inventory
adoption inside the existing preview/Apply gate: bind a source-derived revision,
write the portable choice to existing state, and retain prior certification and
launcher if required completion fails. File installation and actual runtime
qualification remain separate observations.

Repeated delivery install independently rewrites identical owned files and its
manifest lock. Bootstrap uses the existing public verify seam for an installed
current pack, retaining source/pack/owned-registry/file validation. A pending
install-state marker remains incomplete even after integrity passes. Public
fixtures preserve complete consumer metadata across cache/plain repeats and
confirm drift/partial/stale inputs block; supported explicit repair is followed
by an unchanged repeat. No delivery policy/runtime change is needed.

## Readable proof versus writable adoption state

A regular-file check follows a symlink and is sufficient only for the existing
read-only proof reader. Inventory Apply and failed-completion rollback must
reject linked state before writing, preserving both link and target for explicit
owner repair. Public bootstrap/upgrade fixtures compare link metadata and the
complete target/consumer bytes, modes and mtimes on refusal, then restore regular
state and apply the same reviewed revision. Keep the read-only recovery control
separate so a write-boundary repair does not remove supported proof reads.

## Same-shell setup composition and failure recovery

Preserve prior noninteractive shell commands and exports when adding a setup
hook; execute only the hook in a workspace-rooted subshell. Bind the settings and
hook bytes into the existing adoption preview revision, retain inline comments,
and reject ambiguous/terminating bodies instead of guessing how to rewrite them.
A public upgrade fixture with a read-only settings file exposed a partially
written hook: rollback must restore setup outputs as well as certification and
launcher state. Compare complete fixture bytes, modes and mtimes on refusal and
unchanged repeats. Directory aliases must preserve the complete skill target and
existing unknown endpoints; file wiring still proves no runtime invocation.

## Preservation oracles and per-route failure

Compare preserved endpoints by mode, inode, device, links, owner, size, mtime,
ctime and link target, not whole `stat` results: reads may refresh access time.
Age the access time before the baseline so that refresh is deterministic on Linux.
Exercise one conflicting route in a fresh fixture, not only after a complete
install, and assert the unaffected routes are still wired. Every printed repair
must be executable through the entry point that printed it.
