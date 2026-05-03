"""Shared pytest fixtures for danalyze tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from danalyze.models import AppMode, DriveInfo, FileNode, FileTree, ScanStatus


@pytest.fixture
def sample_tree() -> FileNode:
    """Return a hand-built FileNode tree for use in state and TUI tests.

    Tree shape (root has 4 children):
      /root/                   LISTED dir
        docs/                  LISTED dir, 2 file children
          a.txt                DONE file, 100 B
          b.txt                DONE file, 200 B
        downloads/             LISTED dir, empty children list
        readme.txt             DONE file, 1024 B
        private/               ERROR dir, permission denied

    Returns:
        Root FileNode of the sample tree.
    """
    file_a = FileNode(
        path=Path("/root/docs/a.txt"),
        name="a.txt",
        is_dir=False,
        size=100,
        scan_status=ScanStatus.DONE,
    )
    file_b = FileNode(
        path=Path("/root/docs/b.txt"),
        name="b.txt",
        is_dir=False,
        size=200,
        scan_status=ScanStatus.DONE,
    )
    docs = FileNode(
        path=Path("/root/docs"),
        name="docs",
        is_dir=True,
        children=[file_a, file_b],
        scan_status=ScanStatus.LISTED,
    )
    downloads = FileNode(
        path=Path("/root/downloads"),
        name="downloads",
        is_dir=True,
        children=[],
        scan_status=ScanStatus.LISTED,
    )
    readme = FileNode(
        path=Path("/root/readme.txt"),
        name="readme.txt",
        is_dir=False,
        size=1024,
        scan_status=ScanStatus.DONE,
    )
    private = FileNode(
        path=Path("/root/private"),
        name="private",
        is_dir=True,
        scan_status=ScanStatus.ERROR,
        error="permission denied",
    )
    root = FileNode(
        path=Path("/root"),
        name="root",
        is_dir=True,
        children=[docs, downloads, readme, private],
        scan_status=ScanStatus.LISTED,
    )
    return root


@pytest.fixture
def base_state(sample_tree: FileNode):
    """Factory fixture returning an AppState built from sample_tree.

    Returns a callable that accepts keyword overrides for any AppState field.
    Importing AppState here would create a circular dep risk; callers may
    import it directly from danalyze.state.

    Args:
        sample_tree: Root FileNode fixture.

    Returns:
        A factory function: base_state(**overrides) -> AppState.
    """
    from danalyze.state import AppState

    _drive = DriveInfo(
        device="/dev/sda1",
        total=500 * 1024**3,
        used=200 * 1024**3,
        free=300 * 1024**3,
        mount_point=Path("/"),
    )
    _tree = FileTree(root=sample_tree)

    def _make(**overrides: object) -> AppState:
        defaults: dict = dict(
            view_root=sample_tree,
            selected_index=0,
            notes={},
            mode=AppMode.BROWSE,
            pending_input="",
            drive_info=_drive,
            tree=_tree,
        )
        defaults.update(overrides)
        return AppState(**defaults)

    return _make
