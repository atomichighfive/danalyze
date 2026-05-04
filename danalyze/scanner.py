"""Async directory scanner with caching and per-node error isolation."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from danalyze.filesystem import FilesystemProtocol
from danalyze.logging_config import get_logger
from danalyze.models import FileNode, ScanStatus

log = get_logger(__name__)


def _short_error(exc: Exception) -> str:
    """Return a short, human-readable error description.

    Args:
        exc: The exception to describe.

    Returns:
        A lowercase one-line summary string.
    """
    if isinstance(exc, PermissionError):
        return "permission denied"
    msg = str(exc).lower()
    return msg or "i/o error"


class DiskScanner:
    """Async scanner that lists directories and computes recursive sizes.

    All results are cached on the FileNode objects themselves. Calling
    list_directory or scan_sizes on an already-processed node is a no-op
    unless invalidate() has been called first.

    Args:
        fs: Filesystem implementation to use for OS calls.
        on_progress: Optional callback invoked after each directory is fully
            scanned. Receives the just-completed directory FileNode.
    """

    def __init__(
        self,
        fs: FilesystemProtocol,
        on_progress: Callable[[FileNode], None] | None = None,
    ) -> None:
        """Initialise the scanner.

        Args:
            fs: Filesystem protocol implementation.
            on_progress: Callback fired after each directory scan completes.
        """
        self._fs = fs
        self._on_progress = on_progress
        self._registry: dict[Path, FileNode] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def list_directory(self, node: FileNode) -> None:
        """Populate node.children with UNSCANNED stubs via a single scandir call.

        Cached — subsequent calls are no-ops if node.scan_status is not UNSCANNED.

        Args:
            node: Directory node to list. Must have is_dir == True.

        Side effects:
            Sets node.children, node.scan_status, and possibly node.error.
            On PermissionError or OSError: sets scan_status=ERROR, error=message,
            returns normally without raising.
        """
        if node.scan_status != ScanStatus.UNSCANNED:
            log.debug("scanner.list_dir.cached", "Skipping already-listed %s", node.path)
            return

        log.debug("scanner.list_dir.start", "Listing %s", node.path)
        try:
            entries = list(self._fs.scandir(node.path))
        except (PermissionError, OSError) as exc:
            node.scan_status = ScanStatus.ERROR
            node.error = _short_error(exc)
            log.error(
                "scanner.list_dir.perm_denied",
                "Cannot list %s: %s",
                node.path,
                exc,
                exc_info=True,
            )
            return

        node.children = []
        for entry in entries:
            is_sym = entry.is_symlink()
            try:
                is_dir_val = entry.is_dir()
            except OSError:
                is_dir_val = False
            child = FileNode(
                path=Path(entry.path),
                name=entry.name,
                is_dir=is_dir_val,
                is_symlink=is_sym,
                scan_status=ScanStatus.UNSCANNED,
            )
            node.children.append(child)
            self._registry[child.path] = child

        self._registry[node.path] = node
        node.scan_status = ScanStatus.LISTED

    async def scan_sizes(self, node: FileNode) -> None:
        """Recursively compute sizes for node and all descendants.

        Calls list_directory on any UNSCANNED directory encountered.
        Cached — no-op if node.scan_status is already DONE.

        Args:
            node: Root of the subtree to scan.

        Side effects:
            Sets scan_status, size, and possibly error on node and all
            descendants. On per-child errors, that child is marked ERROR
            and scanning continues for remaining siblings.
        """
        self._registry[node.path] = node
        if node.is_symlink:
            # Never compute sizes for a symlink. If invalidate() cleared children,
            # relist so the view remains usable when navigated inside the symlink.
            if node.scan_status == ScanStatus.UNSCANNED:
                await self.list_directory(node)
            return
        if node.is_dir:
            await self._scan_dir(node)
        else:
            await self._scan_file(node)

    def invalidate(self, path: Path) -> None:
        """Reset a node and all its descendants to UNSCANNED.

        After calling this, the next scan_sizes call will perform a fresh
        recursive scan rather than returning cached results.

        Args:
            path: Absolute path of the node to invalidate. No-op if unknown.

        Side effects:
            Resets scan_status=UNSCANNED, size=None, error=None, children=None
            on the node and all descendants currently in the registry.
        """
        log.debug("scanner.invalidate.called", "Invalidating %s", path)
        node = self._registry.get(path)
        if node is None:
            return
        self._reset_subtree(node)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _scan_dir(self, node: FileNode) -> None:
        """Recursively scan a directory node.

        Args:
            node: Directory node to scan.

        Side effects:
            Mutates node and all descendant nodes.
        """
        if node.scan_status == ScanStatus.DONE:
            return

        if node.scan_status == ScanStatus.UNSCANNED:
            await self.list_directory(node)

        if node.scan_status == ScanStatus.ERROR:
            return

        log.debug("scanner.scan_sizes.start", "Scanning %s", node.path)
        node.scan_status = ScanStatus.SCANNING

        total = 0
        for child in node.children or []:
            self._registry[child.path] = child
            if child.is_symlink:
                log.debug(
                    "scanner.scan_sizes.symlink_skipped",
                    "Skipping symlink %s",
                    child.path,
                )
                continue
            elif child.is_dir:
                await self._scan_dir(child)
                if child.scan_status == ScanStatus.DONE and child.size is not None:
                    total += child.size
            else:
                await self._scan_file(child)
                if child.scan_status == ScanStatus.DONE and child.size is not None:
                    total += child.size

        node.size = total
        node.scan_status = ScanStatus.DONE
        log.debug("scanner.scan_sizes.done", "Done scanning %s size=%d", node.path, total)

        if self._on_progress is not None:
            self._on_progress(node)

    async def _scan_file(self, node: FileNode) -> None:
        """Stat a single file node and record its size.

        Args:
            node: File node to stat.

        Side effects:
            Sets node.size and node.scan_status. On error, sets node.error.
        """
        if node.scan_status == ScanStatus.DONE:
            return
        try:
            stat = self._fs.stat(node.path)
            node.size = stat.st_size
            node.scan_status = ScanStatus.DONE
        except (PermissionError, OSError) as exc:
            node.scan_status = ScanStatus.ERROR
            node.error = _short_error(exc)
            log.error(
                "scanner.scan_sizes.perm_denied",
                "Cannot stat %s: %s",
                node.path,
                exc,
                exc_info=True,
            )

    def _reset_subtree(self, node: FileNode) -> None:
        """Recursively reset a node and all descendants to UNSCANNED.

        Args:
            node: Root of the subtree to reset.

        Side effects:
            Clears scan_status, size, error, and children on node and all
            descendants. Removes descendants from the registry.
        """
        if node.children:
            for child in node.children:
                self._registry.pop(child.path, None)
                self._reset_subtree(child)
        node.scan_status = ScanStatus.UNSCANNED
        node.size = None
        node.error = None
        node.children = None
