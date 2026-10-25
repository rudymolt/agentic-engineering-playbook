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
