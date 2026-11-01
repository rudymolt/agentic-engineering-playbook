# Pinned gstack package proof

`integrity.json` binds the existing registry commit to its complete Git archive,
file modes and sibling aliases, frozen dependency lock, and selected Claude and
Codex source directories. The source remains upstream MIT-licensed material; its
unchanged `LICENSE` is included in the source archive and must accompany installed
copies. This directory contains integrity metadata, not upstream runtime bytes.

Generate the record from the pinned commit object using Bun 1.4.4:

```sh
python3 v0.5/scripts/generate-skill-bundle.py --package gstack --upstream <checkout> --bun <reviewed-bun>
```

Generation archives canonical Git objects in an isolated repository and compares
every entry with the complete Git tree. Local replacement refs and export
attributes cannot change the source. It installs dependencies with the frozen
lock and lifecycle scripts disabled, then runs the static Codex document
generator with automatic installation disabled. Ambient ancestor dependency
directories are refused. No upstream setup is run. Only current skills enter the host
inventory. Existing output requires explicit reconciliation before regeneration.

Verify the record and, when available, its original Git archive offline:

```sh
python3 v0.5/scripts/generate-skill-bundle.py --package gstack --check
python3 v0.5/scripts/generate-skill-bundle.py --package gstack --check --archive <source.tar>
```

The directory name and frontmatter name are recorded separately: upstream Codex
output uses prefixed directories and short declared names. `connect-chrome` maps
to the browser skill, the upgrade command keeps its single prefix, and the Claude
Codex wrapper has no Codex counterpart. Codex safety skills lack hook enforcement;
activation must provide an honest adapter or explicit unsupported route.

## Runtime preparation

The existing provisioner prepares the reviewed Linux arm64 or x64 runtime in an
explicit store outside the consumer project and host discovery roots:

```sh
python3 v0.5/scripts/provision-skills.py --project <consumer> --source <verified-release-checkout> --runtime-store <separate-store> preview-runtime
python3 v0.5/scripts/provision-skills.py --project <consumer> --source <verified-release-checkout> --runtime-store <separate-store> prepare-runtime
python3 v0.5/scripts/provision-skills.py --project <consumer> --source <verified-release-checkout> --runtime-store <separate-store> --release <adopted-tag> --tag-object <recorded-tag-object> --commit <recorded-commit> --offline check-runtime
```

Ordinary release proof applies; maintainers may explicitly select `--candidate`
for disposable testing. Optional `--gstack-archive` and `--bun-archive` supply
the exact reviewed inputs without downloading them. `runtime.json` pins Bun's
official release artifacts by URL, size and SHA-256. Cold builds still need
network access for frozen dependencies. Offline preparation requires a complete
verified build cache; an incomplete cache exits nonzero without trying tools.

Preparation verifies inputs before extraction/execution, uses an isolated home
and physical temporary build directory, disables dependency lifecycle scripts,
and builds only the selected native tools. Bun copies dependencies so cached files
do not share mutable hard links with its transient install cache. Every command
has a 600-second bound; timeout or termination stops its process group. No stock setup, browser,
font or hook installer runs.

The store contains unchanged source and archive bytes, the exact Bun ZIP and
executable, the build tree and a complete integrity receipt. Reuse validates all
files, modes and internal links. Missing managed files can be rebuilt with network
access; the earlier tree is retained under `.gstack-previous-*`. Changed or extra
content blocks replacement. Preserve conflicts and explicitly select another
store when necessary. Builds use private `.gstack-staging-*` directories inside
the store and publish by atomic rename. Abruptly killed builds can leave a stage;
it is ignored and rerunning constructs a fresh one. No unknown directory is deleted.

Runtime commands report `runtime.complete` separately. Overall `complete` remains
false because these commands publish no discovery endpoints. Host activation
and actual Cloud qualification remain separate gates.
Browser/display access, safety enforcement and external services are not proved
by a successful build. Monthly upstream/host review requalifies changed artifacts
deliberately; startup never requests latest.

## Host activation and adoption

After preparation, use `preview-gstack`, `install-gstack`, `check-gstack` or
`recover-gstack` on the same provisioner with the same source and runtime store.
Activation publishes only selected endpoints: generated Codex directories under
`.agents/skills`, and Claude directories under `.claude/skills`. Helpers and the
complete source tree remain outside discovery. The runtime path must contain only
letters, digits, `/`, `_`, `.`, `+` or `-` so adapted shell/YAML references remain
literal. Missing managed files are repairable; edited files, unknown additions,
linked parents and duplicate same-host names block replacement and are preserved.
The shared installation journal retains previous bytes for explicit recovery;
interrupted writes require identical replay or recovery. A project lock serializes
activation across both hosts. Both journals and staging trees are checked before
publishing either host. A later write failure reports already changed paths;
recovery validates the runtime referenced by restored endpoints before writing.

Each endpoint includes the upstream license and original source identities.
Reports identify adapted bytes separately. Adapted instructions point helpers to
the verified runtime through receipt-bound helper launchers that prepend packaged
Bun to PATH. Original helper paths and source bytes remain intact. They defer installation/settings/upgrades to deliberate
adoption. Codex hook-based safety skills explicitly report unsupported enforcement;
the upgrade endpoint explains the reviewed release migration route. Explicit-only
skills retain their policy through `agents/openai.yaml`. Adaptation grants no
embedded review compatibility. Installation completeness does not establish host
discovery, invocation, browser availability or behavior qualification.

Add `--adopt-gstack` alongside `--adopt-skills` to bootstrap or upgrade preview and
Apply to include gstack in the portable inventory. The preview binds package and
runtime policy hashes; subsequent inventory adoption preserves that choice.
Cloud `setup` prepares the exact runtime and activates both host inventories,
using `$XDG_CACHE_HOME/agentic-engineering-playbook/runtimes` (or the HOME cache)
unless `--runtime-store` is supplied. Local setup reports discovery-only and
preserves existing installs. `setup --offline` prohibits source acquisition and
runtime builds; incomplete caches leave startup incomplete with repair guidance.
