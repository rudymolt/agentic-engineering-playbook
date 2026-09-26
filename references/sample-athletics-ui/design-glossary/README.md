# Sample design glossary — split (progressive-disclosure) form

Reference implementation of the **split** glossary form introduced in V0.2.10. It is the worked-example glossary (`v0.2/templates/DESIGN-GLOSSARY.md`) rendered as a directory of one-entry-per-file plus a read-first `index.md`, so an agent working on a single component loads that entry instead of the whole glossary.

Layout:

- `index.md` — progressive-disclosure index: one line per component (name · one-line definition · kitchen-sink anchor · link). **Read this first.**
- `components/<term>.md` — one component entry, same sub-structure as a monolith glossary entry, plus a `**Related.**` line of bundle-relative links to the components it references.

Regenerate / validate (from `v0.2/`):

```
python3 scripts/check-glossary.py build-index ../references/sample-athletics-ui/design-glossary
python3 scripts/check-glossary.py check      ../references/sample-athletics-ui/design-glossary \
  --kitchen-sink ../references/sample-athletics-ui/sample-athletics-ui-kitchen-sink.html
```

`index.md` is a **generated** artefact — edit entries under `components/`, then rebuild the index; do not hand-edit `index.md`. The split lets agents read one component entry at a time.
