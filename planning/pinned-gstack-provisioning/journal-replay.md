# Completed host journal replay

This is an in-scope follow-up to the approved pinned inventory work: repeated
setup must preserve completed installation history when no host needs changes.
The existing provisioner CLI remains the acceptance seam. No source pin,
discovery policy, customization rule or recovery destination changes.

## Diagnosis and single fix slice

The matching-operation branch in `host_transaction.apply` rewrites a completed
group record as pending and then complete even when both host journals and
installed inventories already match. Per-host application correctly performs
no work, but atomic group-record replacement changes its file and parent
directory metadata. The unchanged check currently exists only in the branch
for a different operation.

Reproduce with the public gstack install/recover commands and a disposable
runtime fixture. Compare the complete history tree's bytes, modes and mtimes
before and after replay. Then move the unchanged decision after every host's
safety preflight and before either group-record branch. A pending group or
host transaction, missing material, source change, or unknown edit must still
take the existing repair/recovery/refusal path.

## Acceptance and verification

- Repeating completed install and recovery commands leaves group and host
  history bytes, modes and mtimes unchanged.
- Missing managed files still repair; interrupted work still finalizes and
  retains the original rollback target.
- Unknown edits and staging conflicts still block before publication.
- Run the transaction, activation, personal-source, local-skill and setup
  checks; regenerate the edition manifest and run the full release verifier
  on the final candidate before shipping.
- Fresh independent review and actual affected-host qualification remain
  gates. A local fixture result does not claim Cloud availability.

Status: the public-CLI regression failed before the fix because the completed
group record and its parent directory changed mtime. After the fix, unchanged
install and recovery replay both preserve the complete history snapshot.
Broader verification and fresh independent review remain pending. Keep this
follow-up local until review and the separate publication/release gates pass.
