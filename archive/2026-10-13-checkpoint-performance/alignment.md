# Checkpoint performance alignment

Status: `sliced`; spec and all six slices accepted for sequential Sol implementation.

The maintainer requested a specification synthesising the initial feasibility
analysis, the subsequent whole-file review, and the review's additional probes.
The existing performance targets remain the contract. This work follows the
accepted [verifier performance improvements](../verifier-performance/spec.md).

The problem is repeated checkpoint work in recovery and coordinator tests, plus
a small remaining reviewed-guidance performance gap. Whole-file diagnostics
support investigating Git costs before Python cleanup. They do not establish
that the proposed optimisations can meet every target.

The [spec](spec.md) preserves exact-ref compare-and-set, effective remote target
validation, lineage checks, durable recovery boundaries, fresh public-operation
admission, and every existing test assertion and matrix dimension. It retains
transport-mode clones. A proposed single-command remote URL shortcut is rejected
because it can hide extra configured fetch URLs.

The maintainer explicitly accepted an immutable seed built once per test class,
with independently owned copies for individual tests. Review refined this to
one seed per class per worker, restored before each sequential test at the same
reserved path so immutable approved remote URLs stay valid. This authorises a bounded
experiment in the spec; it is not permission to reduce the real publication,
clone, or reload checks within any matrix cell. Existing seed construction stays
as the fallback if isolation or timing acceptance fails. All other proposed work
preserves those semantics. The maintainer subsequently accepted the complete
spec and six-slice breakdown and selected build all with Sol.

The draft was manually synthesised using the stage-03 structure; the author did
not resolve the specification job binding first. A subsequent installation check
confirmed that the upstream specification skill is absent in this cloud checkout.
No external spec skill or additional worker was invoked. This maintainer checkout
has no consumer runtime state; state stays in [planning status](../STATUS.md).
Implementation authority is recorded in the approved [breakdown](slices.md).

Maintenance: before implementation and again before release, check the relevant
upstream Git and Python behaviour and the actual CI runner versions. Recheck
after a toolchain, runner, skill, or model-setting update affecting execution.
Preserve user customisations, existing repository settings, and release pins;
any migration must be explicit and verified. No dependency or model change is
required by this spec.
