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

This is package proof only. Runtime builds, acquisition, discovery connections,
repair, and actual host qualification remain required before declaring Cloud
provisioning complete. The portable provisioner does not yet activate this package.
