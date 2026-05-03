from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class ScanStatus(StrEnum):
    """Lifecycle state of a FileNode's size scan."""

    UNSCANNED = "unscanned"
    LISTED = "listed"
    SCANNING = "scanning"
    DONE = "done"
    ERROR = "error"


class AppMode(StrEnum):
    """Current interaction mode of the TUI application."""

    BROWSE = "browse"
    NOTE_INPUT = "note_input"
    QUIT_PROMPT = "quit_prompt"
    SAVE_PROMPT = "save_prompt"


@dataclass
class FileNode:
    """A single entry in the filesystem tree.

    Args:
        path: Absolute path of this entry.
        name: Filename component (last segment of path).
        is_dir: True if this entry is a directory.
        size: Total byte count, or None until scanned.
        children: Direct children, or None until listed.
        scan_status: Current scan lifecycle state.
        error: Human-readable error message when scan_status == ERROR; None otherwise.
    """

    path: Path
    name: str
    is_dir: bool
    size: int | None = None
    children: list[FileNode] | None = None
    scan_status: ScanStatus = ScanStatus.UNSCANNED
    error: str | None = None


@dataclass
class DriveInfo:
    """Disk usage information for the current device.

    Args:
        device: Device name (e.g. "/dev/sda1").
        total: Total capacity in bytes.
        used: Used space in bytes.
        free: Free space in bytes.
        mount_point: Mount point path.
    """

    device: str
    total: int
    used: int
    free: int
    mount_point: Path


@dataclass
class FileTree:
    """A rooted tree of FileNode entries with lookup helpers.

    Args:
        root: The root FileNode of the tree.
    """

    root: FileNode

    def find_by_path(self, path: Path) -> FileNode | None:
        """Search the tree for the node with the given absolute path.

        Args:
            path: Absolute path to search for.

        Returns:
            The matching FileNode, or None if not found.
        """
        return self._search(self.root, path)

    def _search(self, node: FileNode, path: Path) -> FileNode | None:
        if node.path == path:
            return node
        if node.children:
            for child in node.children:
                result = self._search(child, path)
                if result is not None:
                    return result
        return None

    def ancestors(self, node: FileNode) -> list[FileNode]:
        """Return the path from root to node, excluding the node itself.

        Args:
            node: The node whose ancestors to return.

        Returns:
            List of ancestor FileNodes from root (inclusive) to node's parent
            (inclusive), in top-down order. Empty list if node is the root.
        """
        path: list[FileNode] = []
        if self._collect_path(self.root, node, path):
            return path[:-1]
        return []

    def _collect_path(self, current: FileNode, target: FileNode, acc: list[FileNode]) -> bool:
        acc.append(current)
        if current is target:
            return True
        if current.children:
            for child in current.children:
                if self._collect_path(child, target, acc):
                    return True
        acc.pop()
        return False
