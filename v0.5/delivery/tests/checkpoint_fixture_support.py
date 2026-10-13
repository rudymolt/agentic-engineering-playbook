"""Maintenance only for opted-in, sequential disposable checkpoint fixtures.

The fixture owns its TemporaryDirectory and finishes every synchronous write
before calling before_clone. Concurrent writer fixtures never opt in. Nothing
here schedules background work or changes production/user repository settings.
"""
from pathlib import Path
import tempfile


class OwnedRemoteMaintenance:
    def __init__(self, temporary, remote, git, *, threshold=512):
        if not isinstance(temporary, tempfile.TemporaryDirectory):
            raise ValueError('maintenance requires the owning TemporaryDirectory')
        self.temporary = temporary
        self.root = Path(temporary.name)
        self.remote = Path(remote)
        self.git = git
        self.threshold = threshold
        if threshold < 1:
            raise ValueError('maintenance threshold must be positive')
        self._check_owned()

    def _check_owned(self):
        if (self.root.is_symlink() or self.remote.is_symlink() or
                self.remote != self.root / 'remote.git' or not self.root.is_dir()):
            raise ValueError('maintenance target must be the owned disposable remote')

    def configure(self):
        self._check_owned()
        # Receiving Git processes must see these locally, independent of the
        # profiler/verifier's inherited -c environment configuration.
        for key, value in (('gc.auto', '0'), ('maintenance.auto', 'false'), ('receive.autogc', 'false')):
            self.git('config', key, value, cwd=self.remote)

    def before_clone(self):
        self._check_owned()
        objects = self.remote / 'objects'
        if objects.is_symlink() or (objects / 'pack').is_symlink():
            raise ValueError('owned object storage cannot be a symlink')
        loose = 0
        for directory in objects.iterdir():
            if len(directory.name) != 2 or any(c not in '0123456789abcdef' for c in directory.name):
                continue
            if directory.is_symlink():
                raise ValueError('owned object directory cannot be a symlink')
            if directory.is_dir():
                loose += sum(1 for item in directory.iterdir() if item.is_file() and
                             len(item.name) in (38, 62) and
                             all(c in '0123456789abcdef' for c in item.name))
        if loose < self.threshold:
            return False
        # Foreground repack preserves reachable history; no detached gc/prune.
        self.git('repack', '-a', '-d', cwd=self.remote)
        return True
