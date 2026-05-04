"""Filesystem abstraction layer: protocol, real implementation, and in-memory fake."""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NamedTuple, Protocol, runtime_checkable


@runtime_checkable
class FilesystemProtocol(Protocol):
    """Protocol for all OS-level filesystem operations used by the app.

    Args:
        None

    Side effects:
        None — this is a Protocol definition only.
    """

    def scandir(self, path: Path) -> Iterator[os.DirEntry[str]]:
        """List directory contents.

        Args:
            path: Directory to list.

        Returns:
            Iterator of DirEntry objects.

        Raises:
            PermissionError: If the directory cannot be read.
            OSError: On other OS-level errors.
        """
        ...

    def stat(self, path: Path) -> os.stat_result:
        """Return stat result for a path.

        Args:
            path: File or directory path.

        Returns:
            os.stat_result with at minimum st_size populated.

        Raises:
            PermissionError: If the path cannot be stat-ed.
            OSError: On other OS-level errors.
        """
        ...

    def disk_usage(self, path: Path) -> Any:
        """Return disk usage for the filesystem containing path.

        Args:
            path: Any path on the target filesystem.

        Returns:
            Object with .total, .used, .free attributes (all int bytes),
            matching the shape of shutil.disk_usage namedtuple.
        """
        ...

    def is_mount(self, path: Path) -> bool:
        """Return True if path is a filesystem mount point.

        Args:
            path: Path to check.

        Returns:
            True if path is a mount point, False otherwise.
        """
        ...


class RealFilesystem:
    """Production filesystem implementation delegating to OS calls.

    Args:
        None
    """

    def scandir(self, path: Path) -> Iterator[os.DirEntry[str]]:
        """List directory contents via os.scandir.

        Args:
            path: Directory to list.

        Returns:
            Iterator of DirEntry objects.

        Raises:
            PermissionError: If the directory cannot be read.
            OSError: On other OS-level errors.
        """
        return os.scandir(path)

    def stat(self, path: Path) -> os.stat_result:
        """Return stat result via os.stat.

        Args:
            path: File or directory path.

        Returns:
            os.stat_result.

        Raises:
            PermissionError: If the path cannot be stat-ed.
            OSError: On other OS-level errors.
        """
        return os.stat(path)

    def disk_usage(self, path: Path) -> Any:
        """Return disk usage via shutil.disk_usage.

        Args:
            path: Any path on the target filesystem.

        Returns:
            shutil.disk_usage namedtuple with total, used, free fields.
        """
        return shutil.disk_usage(path)

    def is_mount(self, path: Path) -> bool:
        """Return True if path is a mount point via os.path.ismount.

        Args:
            path: Path to check.

        Returns:
            True if path is a mount point.
        """
        return os.path.ismount(path)


# ---------------------------------------------------------------------------
# In-memory fake used in tests
# ---------------------------------------------------------------------------


class _DiskUsage(NamedTuple):
    total: int
    used: int
    free: int


class _FakeStatResult:
    """Minimal stat_result stand-in carrying only st_size.

    Args:
        size: File size in bytes.
    """

    def __init__(self, size: int) -> None:
        """Initialise with a byte size.

        Args:
            size: File size in bytes.
        """
        self.st_size = size


class _FakeDirEntry:
    """Minimal DirEntry stand-in for InMemoryFilesystem.

    Args:
        name: Entry name (not the full path).
        full_path: Absolute path string of this entry.
        nodes: Reference to the filesystem's live node registry so that
            stat() reflects updates made via update_file_size().
        _is_dir: Whether this entry is a directory (or symlink pointing to one).
        _is_symlink: Whether this entry is a symbolic link.
        _denied: Whether stat should raise PermissionError.
    """

    def __init__(
        self,
        name: str,
        full_path: str,
        nodes: dict[str, tuple[str, Any]],
        *,
        _is_dir: bool,
        _is_symlink: bool = False,
        _denied: bool = False,
    ) -> None:
        """Initialise the fake dir entry.

        Args:
            name: Entry name.
            full_path: Absolute path string.
            nodes: Shared node registry from InMemoryFilesystem.
            _is_dir: Whether this is a directory or symlink pointing to one.
            _is_symlink: Whether this entry is a symbolic link.
            _denied: If True, stat raises PermissionError.
        """
        self.name = name
        self.path = full_path
        self._nodes = nodes
        self._is_dir_flag = _is_dir
        self._is_symlink_flag = _is_symlink
        self._denied = _denied

    def is_dir(self) -> bool:
        """Return whether this entry is a directory.

        Returns:
            True if directory or symlink pointing to a directory.
        """
        return self._is_dir_flag

    def is_symlink(self) -> bool:
        """Return whether this entry is a symbolic link.

        Returns:
            True if symlink.
        """
        return self._is_symlink_flag

    def stat(self) -> _FakeStatResult:
        """Return a minimal stat result, reading size from the live node registry.

        Returns:
            _FakeStatResult with st_size set to the current size.

        Raises:
            PermissionError: If this entry has been marked permission-denied.
        """
        if self._denied:
            raise PermissionError(f"Permission denied: {self.path}")
        kind, value = self._nodes.get(self.path, (None, None))
        size = value if kind == "file" else 0
        return _FakeStatResult(size)


class InMemoryFilesystem:
    """Dict-based fake filesystem for unit tests.

    Constructor accepts a nested dict where directories are nested dicts and
    files are int byte sizes:

        fs = InMemoryFilesystem({
            "/home/user": {
                "docs": {"report.pdf": 1_024_000},
                ".bashrc": 4_096,
            }
        })

    The dict must have exactly one top-level key (the mount root).

    Args:
        tree: Nested dict describing the filesystem layout.

    Raises:
        ValueError: If tree does not have exactly one top-level key.
    """

    def __init__(self, tree: dict[str, dict[str, Any]]) -> None:
        """Initialise the in-memory filesystem from a nested dict.

        Args:
            tree: Mapping of root path string to contents dict.

        Raises:
            ValueError: If tree does not have exactly one top-level key.
        """
        if len(tree) != 1:
            raise ValueError("InMemoryFilesystem expects exactly one top-level root key")

        self._root_path: str = next(iter(tree))
        self._root_contents: dict[str, Any] = tree[self._root_path]

        # Flat map: absolute path str -> ("file", size) | ("dir", contents_dict)
        self._nodes: dict[str, tuple[str, Any]] = {}
        self._permission_denied: set[str] = set()
        self._scandir_call_count: int = 0

        self._index_tree(self._root_path, self._root_contents)

    # ------------------------------------------------------------------
    # Public test-control interface
    # ------------------------------------------------------------------

    @property
    def scandir_call_count(self) -> int:
        """Total number of scandir calls made against this filesystem.

        Returns:
            Non-negative integer call count.
        """
        return self._scandir_call_count

    def update_file_size(self, path_str: str, new_size: int) -> None:
        """Change the size of a file in the fake filesystem.

        Args:
            path_str: Absolute path string of the file.
            new_size: New byte size.

        Raises:
            KeyError: If path_str is not a known file.
        """
        kind, _ = self._nodes[path_str]
        if kind != "file":
            raise KeyError(f"{path_str!r} is not a file")
        self._nodes[path_str] = ("file", new_size)

    def set_permission_denied(self, path_str: str) -> None:
        """Mark a path as permission-denied; scandir and stat will raise PermissionError.

        Args:
            path_str: Absolute path string to deny.
        """
        self._permission_denied.add(path_str)

    def add_symlink(self, path_str: str, *, target_is_dir: bool = False) -> None:
        """Register a symlink under an existing directory in the fake filesystem.

        The immediate parent directory must already exist. The symlink is injected
        into the parent's live contents dict so that scandir discovers it.

        Args:
            path_str: Absolute path string for the symlink.
            target_is_dir: True if the symlink points to a directory; False for
                file targets and broken symlinks.

        Raises:
            ValueError: If the parent directory is not a known directory.
        """
        from pathlib import Path as _Path

        parent_str = str(_Path(path_str).parent)
        name = _Path(path_str).name
        kind, contents = self._nodes.get(parent_str, (None, None))
        if kind != "dir":
            raise ValueError(f"Parent {parent_str!r} is not a known directory")
        contents[name] = None  # sentinel; real type info is in _nodes[path_str]
        self._nodes[path_str] = ("symlink", target_is_dir)

    # ------------------------------------------------------------------
    # FilesystemProtocol implementation
    # ------------------------------------------------------------------

    def scandir(self, path: Path) -> Iterator[_FakeDirEntry]:
        """List directory contents from the in-memory tree.

        Args:
            path: Directory path to list.

        Returns:
            Iterator of _FakeDirEntry objects.

        Raises:
            PermissionError: If this path was marked with set_permission_denied.
            FileNotFoundError: If path is not a known directory.
        """
        self._scandir_call_count += 1
        path_str = str(path)
        if path_str in self._permission_denied:
            raise PermissionError(f"Permission denied: {path_str}")

        kind, contents = self._nodes.get(path_str, (None, None))
        if kind != "dir":
            raise FileNotFoundError(f"Not a directory: {path_str}")

        for name, value in contents.items():
            child_path = f"{path_str}/{name}" if not path_str.endswith("/") else f"{path_str}{name}"
            denied = child_path in self._permission_denied
            child_entry = self._nodes.get(child_path)
            if child_entry is not None and child_entry[0] == "symlink":
                yield _FakeDirEntry(
                    name,
                    child_path,
                    self._nodes,
                    _is_dir=child_entry[1],
                    _is_symlink=True,
                    _denied=denied,
                )
            else:
                yield _FakeDirEntry(
                    name,
                    child_path,
                    self._nodes,
                    _is_dir=isinstance(value, dict),
                    _is_symlink=False,
                    _denied=denied,
                )

    def stat(self, path: Path) -> _FakeStatResult:
        """Return stat information for a path.

        Args:
            path: File or directory path.

        Returns:
            _FakeStatResult with st_size set to the file's size (0 for dirs).

        Raises:
            PermissionError: If this path was marked with set_permission_denied.
            FileNotFoundError: If path is not known.
        """
        path_str = str(path)
        if path_str in self._permission_denied:
            raise PermissionError(f"Permission denied: {path_str}")

        kind, value = self._nodes.get(path_str, (None, None))
        if kind == "file":
            return _FakeStatResult(value)
        if kind == "dir":
            return _FakeStatResult(0)
        raise FileNotFoundError(f"No such file or directory: {path_str}")

    def disk_usage(self, path: Path) -> _DiskUsage:
        """Return total disk usage for the tree rooted at path.

        The fake treats all space as used; free is always 0.

        Args:
            path: Root path of the subtree to measure.

        Returns:
            _DiskUsage with total = used = sum of all file sizes; free = 0.
        """
        total = self._sum_sizes(str(path))
        return _DiskUsage(total=total, used=total, free=0)

    def is_mount(self, path: Path) -> bool:
        """Return True only for the top-level root path of the fake tree.

        Args:
            path: Path to check.

        Returns:
            True if path is the root of this filesystem, False otherwise.
        """
        return str(path) == self._root_path

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _index_tree(self, path_str: str, contents: dict[str, Any]) -> None:
        """Recursively register all nodes into self._nodes.

        Args:
            path_str: Absolute path string of the current directory.
            contents: Dict mapping entry names to size-or-subdict.
        """
        self._nodes[path_str] = ("dir", contents)
        for name, value in contents.items():
            child_path = f"{path_str}/{name}" if not path_str.endswith("/") else f"{path_str}{name}"
            if isinstance(value, dict):
                self._index_tree(child_path, value)
            else:
                self._nodes[child_path] = ("file", value)

    def _sum_sizes(self, path_str: str) -> int:
        """Recursively sum file sizes under path_str.

        Args:
            path_str: Absolute path string of the subtree root.

        Returns:
            Total bytes of all files under path_str.
        """
        kind, value = self._nodes.get(path_str, (None, None))
        if kind == "file":
            return value
        if kind == "dir":
            total = 0
            for name in value:
                child_path = (
                    f"{path_str}/{name}" if not path_str.endswith("/") else f"{path_str}{name}"
                )
                total += self._sum_sizes(child_path)
            return total
        return 0
