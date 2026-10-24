"""Registry-derived bundle bytes and their integrity contract (no runtime authority)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import upstream_registry

PACKAGE = 'mattpocock-skills'
BUNDLE = Path('bundles') / PACKAGE


class BundleError(ValueError):
    """Bundle material cannot safely supply the selected inventory."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def files(root: Path) -> dict[str, bytes]:
    """Read a complete regular tree; aliases never confer ownership."""
    if root.is_symlink() or not root.is_dir():
        raise BundleError(f'{root.name}: missing directory or symbolic link')
    result = {}
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            raise BundleError(f'{p.name}: symbolic link is not bundle material')
        if p.is_dir():
            continue
        if not p.is_file():
            raise BundleError(f'{p.name}: non-regular bundle material')
        result[p.relative_to(root).as_posix()] = p.read_bytes()
    return result


def selected(registry):
    return sorted((s for s in registry.skills.values() if s.project_bundle), key=lambda s: s.name)


def scalar(value: str) -> str:
    """Read the plain/quoted strings used by the reviewed frontmatter subset."""
    if value.startswith('"'):
        result = json.loads(value)
        if not isinstance(result, str):
            raise ValueError('expected a quoted string')
        return result
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            raise ValueError('unterminated quoted string')
        return value[1:-1].replace("''", "'")
    if not value or ': ' in value or value.startswith(('{', '[', '&', '*', '!', '|', '>')):
        raise ValueError('unsupported scalar')
    return value


def metadata(skill, material: dict[str, bytes]) -> None:
    """Validate the upstream metadata subset without rewriting upstream YAML."""
    try:
        text = material['SKILL.md'].decode('utf-8')
        codex = material['agents/openai.yaml'].decode('utf-8')
    except (KeyError, UnicodeDecodeError) as error:
        raise BundleError(f'{skill.name}: missing or unreadable invocation metadata') from error
    head = re.match(r'\A---\n(.*?)\n---\n', text, re.S)
    if head is None:
        raise BundleError(f'{skill.name}: invalid SKILL.md frontmatter')
    fields = {}
    for line in head[1].splitlines():
        key, sep, value = line.partition(':')
        if not sep or key in fields:
            raise BundleError(f'{skill.name}: invalid or duplicate frontmatter field')
        try:
            fields[key] = scalar(value.strip())
        except ValueError as error:
            raise BundleError(f'{skill.name}: invalid frontmatter metadata: {error}') from error
    if fields.get('name') != skill.name or not fields.get('description'):
        raise BundleError(f'{skill.name}: invalid name or description metadata')
    disabled = fields.get('disable-model-invocation')
    if (skill.invocation == 'user' and disabled != 'true'
            or skill.invocation == 'model' and disabled is not None):
        raise BundleError(f'{skill.name}: Claude invocation policy differs from registry')
    # Support the reviewed mapping subset and reject duplicate keys/sections.
    # A regex presence check would accept a second `policy: {}` that replaces
    # the first mapping in YAML and removes the explicit-invocation restriction.
    sections = {}
    current = None
    for line in codex.splitlines():
        if not line or line.lstrip().startswith('#'):
            continue
        match = re.fullmatch(r'([a-z_]+):', line)
        if match:
            current = match[1]
            if current not in {'interface', 'policy'} or current in sections:
                raise BundleError(f'{skill.name}: duplicate or unsupported Codex metadata section')
            sections[current] = {}
            continue
        match = re.fullmatch(r'  ([a-z_]+): (.+)', line)
        if match is None or current is None or match[1] in sections[current]:
            raise BundleError(f'{skill.name}: invalid or duplicate Codex metadata field')
        sections[current][match[1]] = match[2]
    interface = sections.get('interface', {})
    if not {'display_name', 'short_description'} <= set(interface):
        raise BundleError(f'{skill.name}: invalid Codex interface metadata')
    for value in interface.values():
        try:
            decoded = json.loads(value)
            if not isinstance(decoded, str) or not decoded:
                raise ValueError('expected nonempty quoted string')
        except ValueError as error:
            raise BundleError(f'{skill.name}: invalid Codex interface metadata') from error
    policy = sections.get('policy')
    if (skill.invocation == 'user' and policy != {'allow_implicit_invocation': 'false'}
            or skill.invocation == 'model' and policy is not None):
        raise BundleError(f'{skill.name}: Codex invocation policy metadata differs from registry')


def record(registry, material: dict[str, bytes], tag_object: str) -> dict:
    """Generate hashes from the complete selected directories and root license."""
    package = registry.packages[PACKAGE]
    skills = selected(registry)
    if not skills or any(s.package != PACKAGE for s in skills):
        raise BundleError('bundle selection must use the reviewed Matt package')
    expected_heads = {'LICENSE', *(s.name for s in skills)}
    if {p.split('/')[0] for p in material} != expected_heads:
        raise BundleError('bundle inventory differs from registry selection')
    if b'MIT License' not in material.get('LICENSE', b''):
        raise BundleError('missing upstream MIT LICENSE')
    records = {}
    for skill in skills:
        prefix = skill.name + '/'
        content = {p[len(prefix):]: data for p, data in material.items() if p.startswith(prefix)}
        metadata(skill, content)
        records[skill.name] = {
            'upstream_path': skill.upstream_path,
            'invocation': skill.invocation,
            'dependencies': list(skill.dependencies),
        }
    return {
        'schema_version': 1,
        'package': PACKAGE,
        'source': package.source,
        'version': package.pin['value'],
        'commit': package.pin['commit'],
        'tag_object': tag_object,
        'skills': records,
        'files': {p: {'sha256': digest(data), 'size': len(data)}
                  for p, data in sorted(material.items())},
    }


def load(edition: Path) -> tuple[dict, dict[str, dict[str, bytes]], upstream_registry.Registry]:
    registry = upstream_registry.load(edition / 'upstream-skills.json')
    root = edition / BUNDLE
    raw = files(root)
    try:
        manifest = json.loads(raw.pop('integrity.json'))
        if not isinstance(manifest, dict) or not isinstance(manifest.get('files'), dict):
            raise ValueError('bundle integrity record and files must be objects')
        tag_object = manifest['tag_object']
        if not isinstance(tag_object, str) or not re.fullmatch('[0-9a-f]{40}', tag_object):
            raise ValueError('invalid upstream tag object')
        expected = record(registry, raw, tag_object)
    except (KeyError, TypeError, ValueError) as error:
        raise BundleError(f'invalid bundle record or metadata: {error}') from error
    if manifest != expected:
        recorded = manifest.get('files', {})
        differences = [p for p in sorted(set(recorded) | set(expected['files']))
                       if recorded.get(p) != expected['files'].get(p)]
        detail = ', '.join(differences) if differences else 'registry selection or source identity'
        raise BundleError('bundle integrity mismatch: ' + detail)
    packages = {}
    for skill in selected(registry):
        prefix = skill.name + '/'
        packages[skill.name] = {p[len(prefix):]: b for p, b in raw.items() if p.startswith(prefix)}
        # Each installed substantial copy carries the unchanged upstream notice.
        packages[skill.name]['LICENSE'] = raw['LICENSE']
    return manifest, packages, registry
