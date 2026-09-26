"""Descriptor-relative deletion for manifest-owned regular files.

Every path component is opened beneath one already-open root directory with
``O_DIRECTORY|O_NOFOLLOW``. The final unlink is relative to the validated
parent descriptor, so replacing a lexical parent with a symlink cannot redirect
deletion outside the root.
"""

from __future__ import annotations

import errno
import hashlib
import os
import stat
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Callable


BeforeUnlink = Callable[[str], None]


class DescriptorDeleteError(RuntimeError):
    pass


def canonical_parts(relative: object) -> tuple[str, ...]:
    """Return portable canonical components or fail closed."""
    if not isinstance(relative, str) or not relative or "\x00" in relative or "\\" in relative:
        raise DescriptorDeleteError(f"unsafe non-canonical owned path: {relative!r}")
    if any(part in {"", ".", ".."} for part in relative.split("/")):
        raise DescriptorDeleteError(f"unsafe non-canonical owned path: {relative!r}")
    posix = PurePosixPath(relative)
    windows = PureWindowsPath(relative)
    if posix.is_absolute() or windows.is_absolute() or windows.drive or posix.as_posix() != relative:
        raise DescriptorDeleteError(f"unsafe non-canonical owned path: {relative!r}")
    return tuple(posix.parts)


def _directory_flags() -> int:
    required = ("O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os, name) for name in required):
        raise DescriptorDeleteError(
            "descriptor-safe deletion requires O_DIRECTORY and O_NOFOLLOW"
        )
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _file_flags() -> int:
    if not hasattr(os, "O_NOFOLLOW"):
        raise DescriptorDeleteError("descriptor-safe deletion requires O_NOFOLLOW")
    return os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _identity(fd: int) -> tuple[int, int]:
    value = os.fstat(fd)
    return value.st_dev, value.st_ino


def _digest(fd: int, prefixed: bool) -> str:
    os.lseek(fd, 0, os.SEEK_SET)
    value = hashlib.sha256()
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            break
        value.update(chunk)
    rendered = value.hexdigest()
    return "sha256:" + rendered if prefixed else rendered


class DescriptorTree:
    """An opened root with bounded no-follow traversal and deletion methods."""

    def __init__(self, root: Path):
        self.root = root.resolve(strict=True)
        self.root_fd: int | None = None
        self.root_identity: tuple[int, int] | None = None

    def __enter__(self) -> "DescriptorTree":
        try:
            self.root_fd = os.open(self.root, _directory_flags())
        except OSError as error:
            raise DescriptorDeleteError(
                f"cannot open deletion root without following symlinks: {self.root}: {error}"
            ) from error
        self.root_identity = _identity(self.root_fd)
        return self

    def __exit__(self, _kind, _value, _traceback) -> None:
        if self.root_fd is not None:
            os.close(self.root_fd)
            self.root_fd = None

    def _opened_root(self) -> int:
        if self.root_fd is None:
            raise DescriptorDeleteError("descriptor deletion root is not open")
        return self.root_fd

    def _open_parent_from(self, base_fd: int, components: tuple[str, ...]) -> int:
        current = os.dup(base_fd)
        try:
            for component in components:
                following = os.open(component, _directory_flags(), dir_fd=current)
                os.close(current)
                current = following
            return current
        except OSError as error:
            os.close(current)
            raise DescriptorDeleteError(
                "owned path parent is missing, a symlink, or not a directory: "
                + "/".join(components)
            ) from error

    def _verify_attached_parent(self, parent_fd: int, components: tuple[str, ...]) -> None:
        try:
            fresh_root = os.open(self.root, _directory_flags())
        except OSError as error:
            raise DescriptorDeleteError("deletion root changed during removal") from error
        try:
            if _identity(fresh_root) != self.root_identity:
                raise DescriptorDeleteError("deletion root identity changed during removal")
            fresh_parent = self._open_parent_from(fresh_root, components)
            try:
                if _identity(fresh_parent) != _identity(parent_fd):
                    raise DescriptorDeleteError("owned path parent changed during removal")
            finally:
                os.close(fresh_parent)
        finally:
            os.close(fresh_root)

    def unlink(
        self,
        relative: str,
        *,
        expected_digest: str | None,
        missing_ok: bool = False,
        before_unlink: BeforeUnlink | None = None,
    ) -> bool:
        """Digest-check and unlink a regular file through one validated parent FD."""
        parts = canonical_parts(relative)
        parent_fd = self._open_parent_from(self._opened_root(), parts[:-1])
        target_fd: int | None = None
        try:
            try:
                target_fd = os.open(parts[-1], _file_flags(), dir_fd=parent_fd)
            except FileNotFoundError:
                if missing_ok:
                    return False
                raise DescriptorDeleteError(f"owned file is missing: {relative}")
            except OSError as error:
                raise DescriptorDeleteError(
                    f"owned file is a symlink or cannot be opened safely: {relative}"
                ) from error
            target_stat = os.fstat(target_fd)
            if not stat.S_ISREG(target_stat.st_mode):
                raise DescriptorDeleteError(f"owned path is not a regular file: {relative}")
            if expected_digest is not None:
                actual = _digest(target_fd, expected_digest.startswith("sha256:"))
                if actual != expected_digest:
                    raise DescriptorDeleteError(f"owned file digest changed: {relative}")
            if before_unlink is not None:
                before_unlink(relative)
            self._verify_attached_parent(parent_fd, parts[:-1])
            current = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            if stat.S_ISLNK(current.st_mode) or (
                current.st_dev,
                current.st_ino,
            ) != (target_stat.st_dev, target_stat.st_ino):
                raise DescriptorDeleteError(f"owned file identity changed during removal: {relative}")
            if expected_digest is not None:
                actual = _digest(target_fd, expected_digest.startswith("sha256:"))
                if actual != expected_digest:
                    raise DescriptorDeleteError(f"owned file digest changed during removal: {relative}")
            os.unlink(parts[-1], dir_fd=parent_fd)
            return True
        finally:
            if target_fd is not None:
                os.close(target_fd)
            os.close(parent_fd)

    def rmdir(self, relative: str, *, missing_ok: bool = True) -> bool:
        """Remove one empty directory without following any path component."""
        parts = canonical_parts(relative)
        parent_fd = self._open_parent_from(self._opened_root(), parts[:-1])
        try:
            try:
                value = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                if missing_ok:
                    return False
                raise DescriptorDeleteError(f"owned directory is missing: {relative}")
            if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode):
                raise DescriptorDeleteError(f"owned directory is a symlink or not a directory: {relative}")
            self._verify_attached_parent(parent_fd, parts[:-1])
            try:
                os.rmdir(parts[-1], dir_fd=parent_fd)
            except OSError as error:
                if error.errno in {errno.ENOTEMPTY, errno.EEXIST}:
                    return False
                raise DescriptorDeleteError(f"cannot safely remove owned directory: {relative}") from error
            return True
        finally:
            os.close(parent_fd)
