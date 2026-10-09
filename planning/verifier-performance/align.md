# Verifier performance alignment

The tracker issue is the product brief. The maintainer confirmed building all five slices in order, with one PR per slice.

Goal: reduce the full local verifier below 20 minutes, the public CI job below 10 minutes, and the delivery CI job below 5 minutes without deleting tests or weakening assertions outside the narrowly specified CLI sampling in slice 4.

Constraints: preserve both required CI jobs, keep each slice independently verifiable, measure before and after, regenerate manifests and status after edition changes, and run the full verifier on each final PR candidate.

Scope: verifier scheduling, test loading and test cost, and repeated product work described in the issue. Workflow changes and new test dependencies are out of scope.

Maintenance: check upstream Python, unittest, GitHub runner, and playbook changes during normal dependency and release reviews; verify affected behavior before migration and preserve project settings and local customizations.
