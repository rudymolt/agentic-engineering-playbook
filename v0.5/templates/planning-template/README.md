# planning/

> Build-time planning documents live here, one folder per active feature.
>
> See `{playbook-path}/v0.5/30-document-lifecycle.md` for the full lifecycle policy.

---

## Layout

```
planning/
  {feature-slug}/
    office-hours.md        # stage 01, if {skill:office-hours} was run
    ceo-review.md          # stage 01, if {skill:plan-ceo-review} was run
    design-review.md       # stage 01, if {skill:plan-design-review} was run
    eng-review.md          # stage 01, if {skill:plan-eng-review} was run
    grilling-notes.md      # stage 01, {skill:grill-with-docs} output
    spec.md                 # stage 03, {skill:to-spec} output (formerly /to-prd)
    slices.md              # stage 04, {skill:to-tickets} output (formerly /to-issues; or just a list)
    slices/
      {slice-slug}/        # optional, for slices that need their own docs
        notes.md
  retros/
    {YYYY-MM-DD}.md        # weekly retros (per stage 12)
```

## Rules

- **One folder per active feature.** Slug matches `active_features[].slug` in `.playbook-state.yml`.
- **Tier 1 — ephemeral.** Everything in here is build-time scratch. Decisions that should survive are promoted to ADRs or `CONTEXT.md` at the doc-close ritual.
- **Move to `archive/` on ship.** Renamed to `{YYYY-MM-DD}-{feature-slug}/` and moved out of agent reach.
- **Agents must not read planning folders for features not in `active_features`.** This is enforced by the rule in `CLAUDE.md`.
- **Calibrate document length.** Size every file here to what its task needs — cover the substance, then stop; no filler sections, redundant summaries, or boilerplate. Planning documents are read back as agent context, so inflation compounds.

## What goes here

- Grilling transcripts, design-review outputs, CEO/eng/design plan reviews.
- The spec and the slice breakdown.
- Slice-level scratch notes if helpful.
- Weekly retros under `retros/`.

## What does NOT go here

- ADRs — those live at `docs/adr/`.
- Release notes — those live at `docs/releases/`.
- Domain vocabulary — that lives in `CONTEXT.md`.
- Project-wide rules — those live in `CLAUDE.md`.
