# Open Knowledge Format (OKF) — what it is and where it's useful

> A plain-language explainer of the Open Knowledge Format, written to help decide where (and whether) it's worth using. Based on the OKF v0.1 draft specification and the reference proof of concept published by Google Cloud Platform.
>
> Sources: [OKF README](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/README.md), [OKF v0.1 SPEC](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md). Status: external draft spec, v0.1, single vendor, no established ecosystem yet.

## What OKF is, in one sentence

OKF is a convention for representing *knowledge* — the context, metadata, and curated insight around data and systems — as a directory of plain markdown files with YAML frontmatter, version-controlled in git, readable by both humans and AI agents without any special tooling.

That's the whole idea. If you can `cat` a file you can read OKF; if you can `git clone` a repo you can ship it. There is no schema registry, no central authority, and no required software.

## The format itself

An OKF **bundle** is just a directory tree of markdown files. Each file is a **concept** — one unit of knowledge (a database table, an API, a metric, a playbook, a reference page). The structure is deliberately thin:

- **Frontmatter.** A YAML block at the top of each file. The only *required* field is `type` (a short, self-describing string like `BigQuery Table`, `Metric`, or `Playbook`). Recommended-but-optional fields are `title`, `description`, `resource` (a URI for the underlying asset), `tags`, and `timestamp`. Producers may add any other keys they like.
- **Body.** Standard markdown. A few section headings carry conventional meaning when present — `# Schema`, `# Examples`, `# Citations` — but none are required.
- **Cross-links.** Concepts reference each other with ordinary markdown links (bundle-relative paths like `/tables/customers.md` are preferred). A link asserts *some* relationship; the prose around it says what kind. Broken links are explicitly tolerated — they just mean knowledge not yet written.
- **`index.md`.** An optional per-directory listing that enables *progressive disclosure*: an agent or person can see what a directory contains before opening everything, rather than loading the whole bundle into context.
- **`log.md`.** An optional per-directory, newest-first history of changes.

The design philosophy is "minimally opinionated": standardise only the few rules needed for different tools to interoperate, and leave everything else to the producer. Consumers are required to be permissive — they must not reject a bundle for missing optional fields, unknown `type` values, extra keys, or broken links.

## The format is separable from the Google tooling

This is the most important distinction for anyone evaluating OKF. The repository ships three things, and only the first is OKF:

1. **The spec** — the format described above. Vendor-neutral, framework-neutral, model-neutral.
2. **An enrichment agent** — a proof-of-concept *producer* built on Google's Agent Development Kit with Gemini, reading BigQuery metadata and crawling seed URLs to generate bundles automatically.
3. **A visualiser** — a proof-of-concept *consumer* that renders a bundle as a self-contained interactive HTML graph (force-directed nodes, a detail panel, backlinks, search).

Adopting OKF means adopting (1). It carries no obligation to use Gemini, ADK, or BigQuery. The agent and visualiser exist only to make the format tangible at the production and consumption ends.

## What problem it actually solves

OKF is a reaction to knowledge living in service-owned metadata stores that you can only reach through a proprietary API or SDK. By contrast, knowledge written as markdown-in-git gains a set of properties more or less for free:

| Property | What it buys you |
|---|---|
| Human- and agent-readable | No SDK or query language between a reader and the content; an LLM ingests it verbatim |
| Version-controlled | Diffs, blame, pull requests, review — knowledge curation becomes normal software engineering |
| Portable / lock-in-free | A bundle is a directory; ship it as a tarball, a repo, or a mounted filesystem |
| Structured *and* unstructured | Frontmatter for the few fields you query or filter on; body prose for what humans and LLMs actually read |
| Composable | Notion, Obsidian, MkDocs, Hugo, Jekyll already speak markdown + frontmatter |
| Progressive disclosure | `index.md` lets a reader navigate one level at a time instead of loading everything |
| Graph-shaped | Cross-links express relationships richer than the parent/child of a directory tree |

## Where OKF is genuinely useful

OKF earns its keep when the knowledge is **large, homogeneous, and machine-traversed**. The strongest fits:

- **Data catalogues.** Its origin and best fit. Hundreds-to-thousands of tables, datasets, schemas, and metrics, each a concept, each carrying queryable frontmatter. This is where a typed-concept model and a graph view pay off.
- **Agent-readable knowledge bases / RAG corpora.** When you want an LLM agent to navigate a knowledge corpus deliberately — read an index, pick a concept, follow a link — rather than have the whole thing flattened into a context window.
- **Cross-organisation knowledge exchange.** A vendor-neutral file format is a sensible lingua franca for shipping curated metadata between companies or tools without forcing a shared platform.
- **Metadata-as-code shops.** Teams that already keep catalogue metadata next to source code, reviewed through the same pull-request workflow, get a published convention instead of a bespoke in-house one.
- **Migration / portability.** Exporting from one catalogue system (Dataplex, Unity Catalog, Collibra) into a neutral format that can be re-imported elsewhere or simply browsed as files.

## Where OKF is *not* a good fit

Being even-handed, it's easy to over-apply:

- **Small or prose-heavy corpora.** A few dozen narrative documents don't shard cleanly into typed concepts. Adding `type:` frontmatter and a conformance lint to a handful of well-named files is ceremony that guards against a confusion that doesn't exist. A plain table of contents serves a small corpus better than a concept graph.
- **Where a graph view would mislead.** Force-directed graphs impress in demos but inform poorly below a few hundred nodes — and can imply more complexity than really exists, which is the opposite of reassuring for a non-technical audience.
- **As a lifecycle.** OKF is a *representation* convention. It says nothing about when a document is created, promoted, archived, or retired. If you already have a working document lifecycle, OKF doesn't replace it; at most it standardises how the surviving artefacts are serialised.
- **As a stable foundation today.** It's a v0.1 draft from a single vendor with no ecosystem yet. Coupling a governed, versioned product to it means taking on an external dependency you'd have to track and migrate against.

## How to think about adopting it

OKF is best treated as a **set of conventions to borrow selectively**, not a platform to adopt wholesale, and certainly not a reason to pull in the Google enrichment agent. Before adopting any part, name the specific pain you expect it to fix — agents missing context, readers not trusting the artefacts, docs drifting — and check whether OKF actually addresses *that* particular pain. If the honest answer is "it would make the files a bit tidier," that's usually not worth a new dependency.

Its quieter, more durable value is **conceptual**: it's independent confirmation that "knowledge as plain markdown in git, read by humans and agents" is a sound architecture, and it supplies clean vocabulary — *concept*, *bundle*, *progressive disclosure*, *conformance* — for explaining that architecture to others.

## One-line summary

OKF is markdown-plus-frontmatter knowledge in git, specified just enough to interoperate; it shines for large machine-traversed catalogues and cross-tool exchange, and is mostly overhead for small, prose-heavy, human-read document sets.
