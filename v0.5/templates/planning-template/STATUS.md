# planning/ status

active_features: 0

> **This is a definitive empty state, not an error.** Created at bootstrap. If this file says 0 and there are no feature folders alongside it, the project genuinely has no features in flight — do not treat the empty folder as a wrong path or a failed bootstrap.

## Maintenance rule

Whoever opens or closes a feature folder updates this file in the same change:

- Stage 01 (align) creates `planning/{slug}/` → increment the count and add a line below.
- Stage 10 (ship) moves the folder to `archive/` → decrement the count and remove the line.

## Active features

*(none — add one line per feature: `- {slug} · {status} · opened {YYYY-MM-DD}`, mirroring `active_features` in `.playbook-state.yml`)*

## Pending Plan routes

*(none — add `- {request title} · {route status} · {model label} via {runner} · handoff {path|automatic}`, mirroring resumable `pending_model_routes` without increasing `active_features`)*

## Open Wayfinder maps

*(none — while pre-spec discovery is open, add `- [{map title}]({locator}) — {one-line destination}`, mirroring `active_wayfinding_maps` without increasing `active_features`)*
