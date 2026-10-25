"""Preserving Conductor setup composition inside the existing adoption gate."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import zipfile

SETTINGS = '.conductor/settings.toml'
SCRIPT = '.playbook/conductor-setup.sh'
MARKER = '# Playbook adopted Conductor setup'
SUFFIX = '''# Playbook adopted Conductor setup
__playbook_setup_status=$?
if [ "$__playbook_setup_status" -ne 0 ]; then
  printf '%s\\n' 'Prior project setup failed; repair it before retrying Playbook setup.' >&2
  exit "$__playbook_setup_status"
fi
(
  cd "${CONDUCTOR_WORKSPACE_PATH:?Restore Conductor workspace environment before setup}" || exit 2
  if ! command -v sh >/dev/null 2>&1; then
    printf '%s\\n' 'Playbook setup needs a POSIX sh on PATH; restore the noninteractive shell toolchain.' >&2
    exit 2
  fi
  sh .playbook/conductor-setup.sh
)'''


def regular(path):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError('preserve linked or nonregular setup input ' + path.name + '; restore a regular project file before adoption')
    return path.read_bytes() if path.exists() else None


def statements(text):
    """Locate TOML statements without treating strings/comments as table headers."""
    start = i = depth = 0
    quote = None
    comment = None
    while i < len(text):
        if quote:
            if quote.startswith('"') and text[i] == '\\':
                i += 2
                continue
            if text.startswith(quote, i):
                i += len(quote)
                quote = None
                continue
        else:
            c = text[i]
            if c == '#':
                comment = i
                end = text.find('\n', i)
                i = len(text) if end < 0 else end
                continue
            if c in ('"', "'"):
                quote = c * 3 if text.startswith(c * 3, i) else c
                i += len(quote)
                continue
            if c in '[{':
                depth += 1
            elif c in ']}':
                depth -= 1
            elif c == '\n' and depth == 0:
                yield start, i, text[start:i], comment
                start = i + 1
                comment = None
        i += 1
    if start < len(text):
        yield start, len(text), text[start:], comment


def compose(text):
    try:
        import tomllib
    except ImportError:
        raise ValueError('Conductor configuration adoption needs Python 3.11+ with tomllib; use an available compatible interpreter for this explicit preview/Apply, without changing global defaults') from None
    try:
        parsed = tomllib.loads(text)
        scripts = parsed.get('scripts', {})
        if not isinstance(scripts, dict):
            raise ValueError('scripts must be a TOML table')
        old = scripts.get('setup', '')
        if not isinstance(old, str):
            raise ValueError('scripts.setup must be a shell string')
        if old.endswith(SUFFIX):
            return text
        if MARKER in old:
            raise ValueError('customized Playbook setup suffix; preserve it and explicitly reconcile the hook before adoption')
        try:
            tokens = list(shlex.shlex(old, posix=True, punctuation_chars=True))
        except ValueError:
            raise ValueError('prior setup cannot be scanned safely for terminating commands (for example a heredoc '
                             'or unbalanced quote); preserve those commands in a project helper script that setup '
                             'calls, then preview again') from None
        if any(token in ('exit', 'exec', 'return') for token in tokens):
            raise ValueError('terminating setup control requires explicit reconciliation; preserve the prior commands in a project helper that returns to the configured shell before appending the hook')
        combined = old + ('\n' if old else '') + SUFFIX
        # TOML basic strings take literal non-ASCII; JSON surrogate escapes are invalid TOML.
        encoded = json.dumps(combined, ensure_ascii=False).replace('\x7f', '\\u007f')
        table, header, location = None, None, None
        for start, end, statement, comment in statements(text):
            stripped = statement.strip()
            if stripped.startswith('['):
                table = stripped.split('#', 1)[0].strip()
                if table == '[scripts]':
                    header = end
            elif ((table == '[scripts]' and re.match(r'^setup\s*=', stripped))
                  or (table is None and re.match(r'^scripts\.setup\s*=', stripped))):
                if location is not None:
                    raise ValueError('ambiguous setup assignment')
                equal = statement.index('=')
                value_end = comment if comment is not None else end
                while value_end > start and text[value_end - 1] in ' \t':
                    value_end -= 1
                location = (start + equal + 1, value_end)
        if location is not None:
            result = text[:location[0]] + ' ' + encoded + text[location[1]:]
        elif 'setup' in scripts:
            raise ValueError('use a standalone setup assignment in a [scripts] table before preview; preserve other settings')
        elif header is not None:
            result = text[:header] + '\nsetup = ' + encoded + text[header:]
        else:
            result = text + ('\n' if text and not text.endswith('\n') else '') + '\n[scripts]\nsetup = ' + encoded + '\n'
        expected = {**parsed, 'scripts': {**scripts, 'setup': combined}}
        if tomllib.loads(result) != expected:
            raise ValueError('setup composition would alter other settings')
        return result
    except (ValueError, TypeError) as error:
        raise ValueError('Conductor setup composition blocked: ' + str(error) + '; settings are preserved; resolve this before preview/Apply') from None


def prepare(project, source, previous, current_launcher):
    for relative in ('.conductor', '.playbook'):
        directory = project / relative
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise ValueError('preserve conflicting ' + relative + ' directory before setup adoption')
    for name in ('conductor.json', '.conductor/settings.json'):
        if (project / name).exists() or (project / name).is_symlink():
            raise ValueError('legacy ' + name + ' requires explicit settings migration first; preserve its setup/actions and other settings before adopting the shared TOML hook')
    settings = regular(project / SETTINGS)
    script, material = owned_hook(project, source, previous, current_launcher)
    if script is not None and script is not material and script != material:
        raise ValueError('preserve customized conductor-setup.sh; explicitly reconcile its owned/custom content before setup adoption')
    try:
        text = settings.decode('utf-8') if settings else ''
    except UnicodeDecodeError:
        raise ValueError('Conductor setup composition blocked: ' + SETTINGS + ' is not UTF-8 TOML; preserve it and '
                         'restore a UTF-8 encoding before preview/Apply') from None
    after = compose(text)
    import tomllib
    return {'files': {SETTINGS: {'before': settings, 'after': after.encode('utf-8')},
                      SCRIPT: {'before': script, 'after': material}},
            'setup': tomllib.loads(after)['scripts']['setup']}


def owned_hook(project, source, previous, current_launcher):
    """Return the existing hook and the release hook; identical objects mark a pristine prior hook."""
    script = regular(project / SCRIPT)
    material = (source / 'v0.5/scripts/conductor-setup.sh').read_bytes()
    if script is None or script == material:
        return script, material
    known = None
    if previous and current_launcher and hashlib.sha256(current_launcher).hexdigest() == previous['launcher_sha256']:
        import io
        try:
            with zipfile.ZipFile(io.BytesIO(current_launcher)) as archive:
                known = archive.read('conductor-setup.sh')
        except (KeyError, zipfile.BadZipFile):
            pass
    return (material if known == script else script), material


def refresh(project, source, previous, current_launcher):
    """Keep an already adopted, unmodified hook paired with its replacement launcher."""
    script, material = owned_hook(project, source, previous, current_launcher)
    if script is not material or regular(project / SCRIPT) == material:
        return None
    return {'files': {SCRIPT: {'before': regular(project / SCRIPT), 'after': material}}}


def apply(project, plan):
    for name, value in plan['files'].items():
        if regular(project / name) != value['before']:
            raise ValueError('setup inputs changed after preview; preserve edits and preview again')
    changed = []
    for name in (SCRIPT, SETTINGS):
        if name not in plan['files']:
            continue
        value = plan['files'][name]
        if value['before'] != value['after']:
            path = project / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value['after'])
            changed.append(str(path))
    return changed


def rollback(project, plan):
    for name, value in plan['files'].items():
        path = project / name
        if regular(path) == value['after'] and value['before'] != value['after']:
            if value['before'] is None:
                path.unlink()
            else:
                path.write_bytes(value['before'])


def prune_aliases(project):
    """Remove only setup-owned Claude aliases whose canonical skill directory is gone."""
    parents = (project / '.claude', project / '.claude/skills')
    if any(p.is_symlink() or not p.is_dir() for p in parents):
        return []
    removed = []
    for alias in sorted(parents[1].iterdir()):
        if (alias.is_symlink() and os.readlink(alias) == '../../.agents/skills/' + alias.name
                and not (project / '.agents/skills' / alias.name).exists()):
            alias.unlink()
            removed.append('.claude/skills/' + alias.name)
    return removed


def discovery_aliases(project, names, *, apply=False):
    """Observe canonical Codex locations and safe whole-directory Claude aliases."""
    rows = []
    parents = (project / '.claude', project / '.claude/skills')
    unsafe_parent = any(p.is_symlink() or (p.exists() and not p.is_dir()) for p in parents)
    for name in sorted(names):
        target = project / '.agents/skills' / name
        if target.is_symlink() or not (target / 'SKILL.md').is_file():
            continue
        rows.append({'runtime': 'codex', 'path': '.agents/skills/' + name,
                     'status': 'canonical', 'qualification': 'unverified'})
        alias = project / '.claude/skills' / name
        legacy = project / '.claude/commands' / (name + '.md')
        status = 'missing'
        if unsafe_parent or legacy.exists() or legacy.is_symlink():
            status = 'conflict'
        elif alias.is_symlink():
            try:
                status = 'linked' if alias.resolve(strict=True) == target.resolve(strict=True) else 'conflict'
            except (OSError, RuntimeError):
                status = 'conflict'
        elif alias.exists():
            status = 'conflict'
        rows.append({'runtime': 'claude', 'path': '.claude/skills/' + name,
                     'target': '../../.agents/skills/' + name, 'status': status,
                     'qualification': 'unverified'})
    conflicts = any(r['status'] == 'conflict' for r in rows)
    changed = []
    # Withhold only conflicting routes; an unsafe parent withholds every alias.
    if apply and not unsafe_parent:
        for row in rows:
            if row['runtime'] != 'claude' or row['status'] != 'missing':
                continue
            if any(p.is_symlink() or (p.exists() and not p.is_dir()) for p in parents):
                raise ValueError('discovery parents changed; preserve endpoints and reconcile .claude/skills before retrying')
            path = project / row['path']
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.symlink_to(row['target'], target_is_directory=True)
            except OSError:
                row['status'] = 'conflict'
                conflicts = True
                continue
            row['status'] = 'linked'
            changed.append(row['path'])
    return rows, changed, conflicts
