# Public playbook release profile

The public repository starts with V0.5.0. Its version source is `v0.5/CHANGELOG.md`; stable GitHub Releases point at annotated tags on the independently verified public history.

Before tagging, run `python3 v0.5/scripts/verify-playbook.py`, review the privacy report for the exact commit, confirm the root `LICENSE` and third-party `NOTICE` files, and verify that no old edition tree or private Git ancestor exists. The private historical benchmark suite is not a public release gate.

During a documentation-only release PR update, run focused Markdown, link, public-content, and affected generated-file checks. Run the full verifier on the final release candidate before tagging, rather than after each small edit; if that candidate changes, refresh the required final-candidate evidence.
