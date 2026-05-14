"""End-to-end tests for scripted-mode CLI wiring."""

from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from danalyze.filesystem import InMemoryFilesystem
from danalyze.models import AppMode, DriveInfo, FileNode
from danalyze.scanner import DiskScanner
from danalyze.state import AppState, FileTree


async def test_scripted_frame_reflects_state_after_key_down(tmp_path: Path) -> None:
    """Full integration: scripted input produces frame with expected content."""
    # Build a simple filesystem: /root with apple/ and zebra/ subdirs
    fs = InMemoryFilesystem({"/root": {"apple": {}, "zebra": {}}})
    root = FileNode(path=Path("/root"), name="root", is_dir=True)
    scanner = DiskScanner(fs)
    await scanner.list_directory(root)

    # Build app state with the scanned root
    drive_info = DriveInfo(
        device="/dev/sda1",
        total=500 * 1024**3,
        used=200 * 1024**3,
        free=300 * 1024**3,
        mount_point=Path("/"),
    )
    state = AppState(
        view_root=root,
        selected_index=0,
        notes={},
        mode=AppMode.BROWSE,
        pending_input="",
        drive_info=drive_info,
        tree=FileTree(root=root),
    )

    from danalyze.tui.app import DiskAnalyzerApp

    # Set scripted_inputs after on_mount to avoid timer auto-starting in run_test
    app = DiskAnalyzerApp(state=state, scanner=scanner)

    captured = StringIO()
    async with app.run_test(size=(80, 24)):
        app._scripted_inputs = ["key.down"]
        with patch.object(sys, "stdout", captured):
            await app._run_script()

    output = captured.getvalue()
    assert "--- key.down ---" in output
    # After key.down, zebra (index 1) should be selected/highlighted
    frame = output.split("--- key.down ---")[1]
    assert "zebra" in frame
