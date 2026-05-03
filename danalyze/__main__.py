"""Minimal entry point — full CLI wiring comes in Phase 13."""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

from danalyze.filesystem import RealFilesystem
from danalyze.models import AppMode, DriveInfo, FileNode, FileTree
from danalyze.scanner import DiskScanner
from danalyze.state import AppState
from danalyze.tui.app import DiskAnalyzerApp


async def _run(start: Path) -> None:
    root = FileNode(path=start, name=start.name or str(start), is_dir=True)
    usage = shutil.disk_usage(start)
    drive_info = DriveInfo(
        device=str(start),
        total=usage.total,
        used=usage.used,
        free=usage.free,
        mount_point=start,
    )
    fs = RealFilesystem()
    scanner = DiskScanner(fs)
    await scanner.list_directory(root)
    state = AppState(
        view_root=root,
        selected_index=0,
        notes={},
        mode=AppMode.BROWSE,
        pending_input="",
        drive_info=drive_info,
        tree=FileTree(root=root),
    )
    app = DiskAnalyzerApp(state=state, scanner=scanner)
    await app.run_async()


def main() -> None:
    """Launch danalyze from the command line."""
    start = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    if not start.is_dir():
        sys.exit(f"Not a directory: {start}")
    asyncio.run(_run(start))


if __name__ == "__main__":
    main()
