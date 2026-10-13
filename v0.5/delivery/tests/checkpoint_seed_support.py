"""Process/class-owned complete seeds for sequential disposable test fixtures.

Git only runs against the reserved working path. The template is a separate,
read-only, ordinary copy; approval URLs and checkpoint history are never edited.
"""
import atexit
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile

from checkpoint_fixture_support import OwnedRemoteMaintenance
from delivery_pilot.canonical import canonical_bytes, digest
from delivery_pilot.interim import InterimCheckpointSnapshot, validate_record


class CheckpointSeed:
    def __init__(self, build):
        self.pid = os.getpid()
        self.active = False
        self.closed = False
        self.template_owner = tempfile.TemporaryDirectory()
        self.template = Path(self.template_owner.name) / 'tree'
        self.owner = None
        try:
            base, snapshot = build()
            self.owner = base.temp
            self.root = Path(self.owner.name)
            validate_record(snapshot.value)
            self.value_bytes = canonical_bytes(snapshot.value)
            if digest(snapshot.value) != snapshot.digest:
                raise ValueError('seed checkpoint digest mismatch')
            self.identity = (snapshot.digest, snapshot.commit_sha, snapshot.reconciled, snapshot.parent_commits)
            self.modes = {}
            for path in (self.root, *self.root.rglob('*')):
                if path.is_symlink() or (path.is_file() and path.stat().st_nlink != 1):
                    raise ValueError('seed cannot contain symlinks or hard links')
                if path.name == 'alternates' and path.parent.name == 'info':
                    raise ValueError('seed cannot contain object alternates')
                self.modes[path.relative_to(self.root)] = stat.S_IMODE(path.stat().st_mode)
            shutil.copytree(self.root, self.template)
            for relative, mode in self.modes.items():
                (self.template / relative).chmod(mode & ~0o222)
            base.tearDown()
        except BaseException:
            self.close()
            raise
        atexit.register(self.close)

    def restore(self, base):
        if self.closed or os.getpid() != self.pid:
            raise RuntimeError('seed belongs to another or closed process')
        if self.active:
            raise RuntimeError('seed restoration requires sequential fixture ownership')
        self.active = True
        try:
            if self.root.is_symlink():
                self.root.unlink()
            elif self.root.exists():
                shutil.rmtree(self.root)
            shutil.copytree(self.template, self.root)
            for relative, mode in self.modes.items():
                (self.root / relative).chmod(mode)
            base.temp = self.owner
            base.root = self.root
            base.remote = self.root / 'remote.git'
            base.first, base.second = self.root / 'first', self.root / 'second'
            base.remote_maintenance = OwnedRemoteMaintenance(
                self.owner, base.remote, base.git, threshold=base.maintenance_loose_threshold)
            value = validate_record(json.loads(self.value_bytes))
            return InterimCheckpointSnapshot(value, *self.identity)
        except BaseException:
            self.active = False
            raise

    def release(self):
        self.active = False

    def close(self):
        if self.closed or os.getpid() != self.pid:
            return
        self.closed = True
        if self.owner is not None:
            self.owner.cleanup()
        # Only cleanup writes template permissions, after its lifetime ends.
        if self.template.exists():
            for path in (self.template, *self.template.rglob('*')):
                path.chmod(stat.S_IMODE(path.stat().st_mode) | 0o700)
        self.template_owner.cleanup()
