"""Publish host-specific gstack skills using the shared installation journal."""
from __future__ import annotations

import json
import fcntl
import os
from pathlib import Path
import re
import stat

import gstack_package as package
import gstack_runtime as runtime
import provisioning_state as history
import host_transaction
from host_skill_name import declared_name
import upstream_bundle as bundle

ADAPTER_REVISION = 3
SAFETY = {'careful', 'freeze', 'guard', 'unfreeze'}


def layout(project, host):
    return history.Layout(project / ('.agents/skills' if host == 'codex' else '.claude/skills'),
                          project / '.playbook/gstack-history' / host)


def validate_parents(project, destination):
    for path in (destination.skills, destination.state):
        while path != project:
            if path.is_symlink() or (path.exists() and not path.is_dir()):
                raise bundle.BundleError('linked or non-directory host installation parent; preserve and reconcile it')
            path = path.parent


def relocate(text, support, name, launchers):
    # These are pinned upstream lookup conventions, not arbitrary shell input.
    # A safe absolute store path can appear in quoted shell, YAML and Markdown.
    if not re.fullmatch(r'/[A-Za-z0-9_./+\-]+', str(support)):
        raise bundle.BundleError('host activation requires a runtime store path using letters, digits, /, _, ., + or -')
    # Codex's generated startup and per-command snippets each discover a root,
    # preferring an ambient GSTACK_ROOT over the project and user installations.
    # A managed endpoint always uses the runtime recorded in its provenance.
    text = re.sub(r'^([ \t]*)\[ -d "\$\{GSTACK_ROOT:-/-\}/lib" \].*\|\|GSTACK_ROOT=.*\n'
                  r'\[ -d "\$GSTACK_ROOT/bin" \].*\|\|GSTACK_ROOT=.*\n'
                  r'\[ -d "\$GSTACK_ROOT/bin" \].*\|\|echo "gstack: no install found .*$',
                  lambda m: f'{m[1]}GSTACK_ROOT={support}', text, flags=re.M)
    text = re.sub(r'^([ \t]*)\[ -d "\$\{GSTACK_ROOT:-/-\}/bin" \].*\|\|\{ _r=.*;GSTACK_ROOT=\$_r;\}$',
                  lambda m: f'{m[1]}GSTACK_ROOT={support}', text, flags=re.M)
    if name == 'ship':
        for host, directory in (('claude', 'document-release'), ('agents', 'gstack-document-release')):
            text = text.replace(f'${{HOME}}/.{host}/skills/gstack/document-release/SKILL.md',
                                f'.{host}/skills/{directory}/SKILL.md')
    pattern = r'(?:\$\{HOME\}/|\$HOME/|~/|\$\{_ROOT\}/|\$_ROOT/)?\.(?:agents|claude|codex)/skills/gstack(?=/|[\s\x22\x27`]|$)'
    text = re.sub(pattern, lambda _: str(support), text)
    text = text.replace('$GSTACK_ROOT/', f'{support}/').replace('$GSTACK_BIN/', f'{support}/bin/')
    # Claude's absolute section references must load the adapted host copy.
    text = text.replace(f'{support}/{name}/sections/', 'sections/')
    if name == 'review':
        text = text.replace(f'Read `{support}/review/checklist.md`.',
                            'Read `checklist.md` in this installed review skill directory.')

    def helper_path(match):
        filename = match[1]
        # Files passed to Bun or sourced into a shell need their original bytes.
        if filename in launchers and not filename.endswith(('.ts', '.sh')):
            return f'{support}/playbook-bin/{filename}'
        return match[0]

    text = re.sub(re.escape(str(support)) + r'/bin/([\w.\-]+)', helper_path, text)
    # The generated review imports this bundled module through a named variable.
    if f'GSTACK_SHARED_LIB={support}/lib/review-evidence.ts\n' in text:
        text = text.replace('"$GSTACK_SHARED_LIB"', f'"{support}/lib/review-evidence.ts"')
    # Bind Bun only where its script or inline program's input is in the runtime.
    # An extensionless Bun script must be interpreted from bin/, not its shell launcher.
    bun_command = (r'(?<![\w./-])bun(?P<args>(?:[ \t]+--[\w-]+(?:=[\w./-]+)?)*'
                   r"(?:[ \t]+run|[ \t]+-e[ \t]+'[^'\n]+')?[ \t]+[\x22\x27]?)"
                   + re.escape(str(support)) + r'/(?P<dir>bin|playbook-bin|scripts|lib)/')

    def bundled_bun(match):
        directory = 'bin' if match['dir'] == 'playbook-bin' else match['dir']
        return f"{support.parent}/bin/bun{match['args']}{support}/{directory}/"

    return re.sub(bun_command, bundled_bun, text)


def adapt_skill(data, support, host, name, launchers, user_only):
    text = relocate(data.decode('utf-8'), support, name, launchers)
    text = re.sub(r'^_UPD=.*$', '_UPD="" # Adopted releases update through Playbook migration.', text, flags=re.M)
    if not text.startswith('---\n') or '\n---\n' not in text[4:]:
        raise bundle.BundleError('pinned host skill lacks a frontmatter boundary')
    end = text.index('\n---\n', 4) + 5
    header, body = text[:end], text[end:]
    if name == 'cso':
        return ('---\nname: cso\ndescription: Route security review to the Playbook stage 08 manual static review.\n'
                '---\n\nUse the manual static-review procedure in Playbook stage 08. '
                'The dedicated upstream launcher requires separate host qualification. '
                'Report the reviewed scope, supporting source locations and remaining coverage gaps.\n').encode()
    if host == 'claude' and user_only and 'disable-model-invocation: true\n' not in header:
        header = re.sub(r'^disable-model-invocation:.*\n', '', header, flags=re.M)
        header = header[:-4] + 'disable-model-invocation: true\n---\n'
    if host == 'codex' and name in SAFETY:
        # Generated upstream instructions claim hook enforcement absent in Codex.
        # Publish an explicit limitation, with no ineffective hook instructions.
        return (f'---\nname: {name}\ndescription: Report the unsupported Codex {name} hook capability and host-native fallback.\n'
                'disable-model-invocation: true\n---\n\n'
                f'# {name}: hook enforcement unsupported in Codex\n\n'
                'Tell the user that this pinned skill cannot install or remove Claude session hooks in Codex. '
                'Do not claim any guard is active. Use the host’s native permission and isolation controls; '
                'a change to those controls requires the user’s explicit choice. '
                'This notice does not change settings or execute the upstream hook workflow.\n').encode()
    if name == 'gstack-upgrade':
        return (f'---\nname: gstack-upgrade\ndescription: Explain the adopted pinned gstack update procedure.\n'
                'disable-model-invocation: true\n---\n\n'
                'This installation is owned by the adopted Playbook release. Report the recorded pin and '
                'route an upgrade through a reviewed release, inventory preview and deliberate project adoption. '
                'Preserve customizations and requalify changed host behavior. '
                'Do not run upstream setup, pull latest, or replace this managed runtime directly.\n').encode()
    note = ('\n## Adopted runtime contract\n\n'
            f'Use the pinned runtime at `{support}` for helpers and shared references. '
            'The installed support tree is managed material; keep it unchanged. '
            'When the skill-start or skill-end launcher prints `PLAYBOOK_MANAGED_SESSION: true`, proceed directly to the task or its result. '
            'The upstream onboarding, telemetry and degraded-mode setup or upgrade prompts do not apply. Never retry through the raw lifecycle helpers. '
            'Skip upstream installation, upgrade, vendoring, onboarding, telemetry opt-in and settings changes. '
            'Those operations belong to deliberate Playbook adoption or a separate explicit user request. '
            'Follow the skill’s task procedure within the current stage’s authority. '
            'Installation grants no embedded review compatibility or permission to ship, merge or deploy. '
            'Read sections/ relative to this installed SKILL.md. Invoke nested workflows through their installed host endpoints; raw support SKILL.md files are provenance, not alternate execution routes. '
            'Browser/display, external services and host-specific tools still require capability checks.\n\n')
    return (header + note + body).encode()


def materials(record, target, host):
    support = target / 'payload/build'
    launchers = runtime.helper_launchers(record)
    outputs, rows = {}, []
    for name, row in sorted(record['skills'].items()):
        spec = row[host]
        if spec['status'] != 'available':
            rows.append({'name': name, 'host': host, 'installation': 'excluded',
                         'reason': spec.get('reason', 'excluded by pinned upstream host inventory')})
            continue
        directory = spec['directory']
        source = support / ('.agents/skills/' + directory if host == 'codex' else directory)
        source_files = dict(spec['files'])
        # The generated Codex review uses the shared upstream checklist but
        # omits the file from its own endpoint. Publish a verified adapted copy.
        if host == 'codex' and name == 'review' and 'checklist.md' in row['claude']['files']:
            source_files.setdefault('checklist.md', row['claude']['files']['checklist.md'])
        files = {}
        for relative, expected in source_files.items():
            path = (source if relative in spec['files'] else support / 'review') / relative
            data = path.read_bytes()
            if bundle.digest(data) != expected['sha256'] or len(data) != expected['size']:
                raise bundle.BundleError('pinned host source differs before activation')
            if relative == 'SKILL.md':
                data = adapt_skill(data, support, host, name, launchers, row['invocation'] == 'user')
            elif name == 'cso':
                # The managed endpoint publishes only the static-review notice.
                continue
            elif relative.endswith(('.md', '.yaml', '.yml', '.tmpl')):
                data = relocate(data.decode('utf-8'), support, name, launchers).encode()
                if name == 'review' and relative == 'checklist.md':
                    data = data.replace(b"route it to /investigate's flake recipe (timing flakes)",
                                        b'route the timing flake to Playbook stage 11 for diagnosis')
            files[relative] = data
        files['LICENSE'] = (support / 'LICENSE').read_bytes()
        header = files['SKILL.md'].split(b'\n---\n', 1)[0].splitlines()
        explicit = (row['invocation'] == 'user' or b'disable-model-invocation: true' in header
                    or name == 'gstack-upgrade' or (host == 'codex' and name in SAFETY))
        if explicit:
            metadata = files.get('agents/openai.yaml', b'').decode()
            if not metadata.strip():
                metadata = f'interface:\n  display_name: "{name}"\n  short_description: "Explicit invocation of {name}"\n'
            if 'allow_implicit_invocation:' in metadata:
                metadata = re.sub(r'allow_implicit_invocation:\s*(?:true|false)', 'allow_implicit_invocation: false', metadata)
            else:
                metadata += '\npolicy:\n  allow_implicit_invocation: false\n'
            files['agents/openai.yaml'] = metadata.encode()
        files['PLAYBOOK-PROVENANCE.json'] = (json.dumps({
            'package': record['package'], 'commit': record['commit'], 'version': record['version'],
            'host': host, 'source_files': source_files, 'adapter_revision': ADAPTER_REVISION,
            'support': str(support), 'discovery': 'unverified', 'qualification': 'unverified',
        }, indent=2, sort_keys=True) + '\n').encode()
        outputs[directory] = files
        rows.append({'name': name, 'host': host, 'directory': directory, 'declared_name': spec['declared_name'],
                     'invocation': 'user' if explicit else row['invocation'],
                     'enforcement': 'unsupported' if host == 'codex' and name in SAFETY else 'unverified',
                     'source_sha256': spec['files']['SKILL.md']['sha256'],
                     'adapted_sha256': bundle.digest(files['SKILL.md']),
                     'embedded_compatible': False, 'discovery': 'unverified', 'qualification': 'unverified'})
        if name == 'cso':
            rows[-1]['fallback'] = 'stage-08-manual-static-review'
    return outputs, rows


def duplicates(project, host, rows):
    """Inspect same-host project/user endpoints without recursive source discovery."""
    names = {r['declared_name'] for r in rows if 'declared_name' in r}
    managed = {Path(r['path']) for r in rows if 'path' in r}
    roots = ([project / '.agents/skills', project / '.codex/skills',
              Path.home() / '.agents/skills', Path.home() / '.codex/skills'] if host == 'codex' else
             [project / '.claude/skills', Path.home() / '.claude/skills'])
    found = []
    for root in roots:
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if child in managed:
                continue
            skill = child / 'SKILL.md'
            if not skill.is_file():
                continue
            text = skill.read_text()
            try:
                name = declared_name(text)
            except ValueError:
                # An unclassified declaration could shadow the managed name.
                found.append(str(skill))
                continue
            if name in names:
                found.append(str(skill))
    commands = [project / '.claude/commands', Path.home() / '.claude/commands'] if host == 'claude' else []
    for root in commands:
        found.extend(str(root / (name + '.md')) for name in names if (root / (name + '.md')).exists())
    return sorted(set(found))


def provision(edition, project, store, action, identity):
    if action not in ('install-gstack', 'recover-gstack'):
        return _provision(edition, project, store, action, identity)
    destination = layout(project, 'codex')
    validate_parents(project, destination)
    state_root = destination.state.parent
    state_root.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(state_root / 'activation.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise bundle.BundleError('host activation lock must be a regular private file')
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise bundle.BundleError('another host activation owns this project; retry when it finishes') from None
        return _provision(edition, project, store, action, identity)
    finally:
        os.close(descriptor)


def _provision(edition, project, store, action, identity):
    report = runtime.provision(edition, project, store, 'check-runtime', offline=True)
    report.update(scope='gstack-hosts', source=identity)
    if not report['runtime']['complete']:
        return report
    record = package.load(edition)
    target = Path(report['runtime']['path'])
    plans = []
    group_path = project / '.playbook/gstack-history/operation.json'
    recovery = host_transaction.recovery_targets(group_path, ('codex', 'claude')) if action == 'recover-gstack' else None
    for host in ('codex', 'claude'):
        destination = layout(project, host)
        validate_parents(project, destination)
        files, rows = materials(record, target, host)
        state = history.load(destination)
        source = {'release': identity, 'runtime': report['runtime']['identity'],
                  'path': str(target), 'adapter_revision': ADAPTER_REVISION, 'host': host}
        after = {'source': source, 'skills': {n: history.encode(c) for n, c in files.items()}}
        if action == 'recover-gstack':
            after = recovery[host]
            if any(value is not None for value in after['skills'].values()):
                restored = after['source']
                restored_path = Path(restored['path'])
                runtime.regular_ancestors(restored_path)
                pinned, artifact, expected_identity = runtime.configuration(edition)
                if restored['runtime'] != expected_identity:
                    raise bundle.BundleError('recovery requires its recorded adopted runtime policy; restore that release before retrying')
                restored_runtime = runtime.observe(restored_path, expected_identity, pinned, artifact)
                if not restored_runtime['complete']:
                    raise bundle.BundleError('recovery runtime support is incomplete; restore the recorded runtime before retrying')
                report.setdefault('requested_runtime', report['runtime'])
                report['runtime'] = restored_runtime
                report.setdefault('requested_source', report['source'])
                report['source'] = restored['release']
                files, rows = materials(record, restored_path, host)
                for row in rows:
                    if 'directory' in row:
                        saved = history.content(after, row['directory'])
                        if saved is None:
                            raise bundle.BundleError('restored inventory lacks a recorded host endpoint')
                        provenance = json.loads(saved['PLAYBOOK-PROVENANCE.json'])
                        row.update(adapted_sha256=bundle.digest(saved['SKILL.md']),
                                   source_sha256=provenance['source_files']['SKILL.md']['sha256'],
                                   restored_source=restored,
                                   adapter_revision=provenance['adapter_revision'])
                report.setdefault('restored_sources', {})[host] = restored
        for row in rows:
            if 'directory' not in row:
                continue
            name = row['directory']
            current = history.actual(destination, name)
            history.require_known_directories(destination.skills / name,
                                              [files[name], history.content(state['current'], name)])
            managed = history.content(state['current'], name)
            missing = (isinstance(current, dict) and isinstance(managed, dict) and set(current) < set(managed)
                       and all(managed.get(p) == data for p, data in current.items()))
            row['installation'] = ('installed' if current == files[name] else
                                   'missing' if current is None else
                                   'missing_files' if missing else
                                   'update_available' if current == history.content(state['current'], name) else 'conflict')
            row['path'] = str(destination.skills / name)
        # The new pin has no rows for endpoints it retires. Only the previous
        # managed inventory authorizes a removal from a host discovery root.
        previous = (state['current'] or {}).get('skills', {})
        for directory in sorted(previous.keys() - files.keys()):
            managed = history.content(state['current'], directory)
            if managed is None:
                continue
            path = destination.skills / directory
            status = 'retirement_pending'
            try:
                history.require_known_directories(path, [managed])
                current = history.actual(destination, directory)
                if current is None:
                    status = 'already_absent'
                elif current != managed:
                    status = 'conflict'
            except (OSError, ValueError):
                status = 'conflict'
            rows.append({'name': declared_name(managed['SKILL.md'].decode()), 'host': host,
                         'directory': directory, 'path': str(path), 'retiring': True,
                         'installation': status})
        duplicate_paths = duplicates(project, host, rows)
        if duplicate_paths:
            report.setdefault('duplicates', []).extend(duplicate_paths)
        plans.append((destination, state, after, rows))
    # Observe both hosts before writes, so a Claude conflict cannot silently yield
    # an apparently completed Codex-only installation.
    report['skills'] = [row for _, _, _, rows in plans for row in rows]
    if report.get('duplicates'):
        report['repair'] = 'Preserve duplicate host skill/command names; explicitly reconcile their selected source before activation.'
        return report
    if any(row.get('retiring') and row['installation'] == 'conflict' for row in report['skills']):
        report['repair'] = 'Save customized retired endpoints outside host discovery or restore their complete prior managed copies before retrying.'
        return report
    if action not in ('install-gstack', 'recover-gstack') and any(row.get('installation') == 'conflict' for row in report['skills']):
        report['repair'] = 'Preserve conflicting host skill content and explicitly reconcile or move it outside discovery before retrying.'
        return report
    if action in ('install-gstack', 'recover-gstack'):
        operation = 'recover' if action == 'recover-gstack' else 'install'
        observed = {}
        try:
            for destination, state, after, rows in plans:
                history.apply(destination, state, operation, after, repair_missing=True, dry_run=True)
                names = set(after['skills']) | set((state['current'] or {}).get('skills', {}))
                if state['transaction']:
                    names |= set(state['transaction']['before']['skills']) | set(state['transaction']['after']['skills'])
                observed[destination] = {n: history.actual(destination, n) for n in names}
            host_transaction.apply(group_path,
                                   {d.state.name: d for d, _, _, _ in plans}, operation,
                                   {d.state.name: after for d, _, after, _ in plans}, repair_missing=True)
        except (OSError, ValueError, KeyError) as error:
            report['error'] = str(error)
            report['repair'] = 'Preserve conflicts and staging evidence; retry the identical installation or recover the interrupted operation.'
        finally:
            for destination, state, after, rows in plans:
                actual = {}
                for name, before in observed.get(destination, {}).items():
                    try:
                        actual[name] = history.actual(destination, name)
                        if actual[name] != before:
                            report['changed'].append(str(destination.skills / name))
                    except (OSError, ValueError) as error:
                        report.setdefault('observation_errors', {})[str(destination.skills / name)] = str(error)
                for row in rows:
                    if 'directory' in row:
                        name = row['directory']
                        desired = history.content(after, name)
                        row['installation'] = ('unknown' if name not in actual else
                                               'retired' if row.get('retiring') and actual[name] is None else
                                               'installed' if desired is not None and actual[name] == desired else 'missing')
    report['complete'] = all(row['installation'] in ('installed', 'excluded', 'retired') for row in report['skills'])
    try:
        group = host_transaction.load(group_path, ('codex', 'claude'))
        report['transaction_pending'] = bool(group and group['pending']) or any(history.load(d)['transaction'] is not None for d, _, _, _ in plans)
    except (OSError, ValueError) as error:
        report['transaction_pending'] = True
        report['error'] = str(error)
    report['complete'] = report['complete'] and not report['transaction_pending'] and not report.get('error')
    if action == 'recover-gstack':
        report['recovery_complete'] = (not report.get('error') and not report['transaction_pending']
                                       and not report.get('observation_errors'))
    report['repair'] = None if report['complete'] else report.get('repair') or 'Run install-gstack after preparing the exact runtime; preserve conflicts.'
    return report
