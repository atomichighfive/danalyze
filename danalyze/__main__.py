"""Entry point for danalyze."""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from pathlib import Path

from danalyze.exceptions import ExportError
from danalyze.export import load_notes_from_csv
from danalyze.filesystem import RealFilesystem
from danalyze.logging_config import setup_logging
from danalyze.models import AppMode, DriveInfo, FileNode, FileTree
from danalyze.scanner import DiskScanner
from danalyze.script_runner import parse_script_arg
from danalyze.state import AppState
from danalyze.tui.app import DiskAnalyzerApp


def main(argv: list[str] | None = None) -> None:
    """Launch danalyze from the command line.

    Args:
        argv: Argument list. Defaults to sys.argv[1:] when None.

    Side effects:
        Calls sys.exit on invalid arguments or unreadable inputs.
        Launches the Textual TUI.
    """
    parser = argparse.ArgumentParser(
        prog="danalyze",
        description="Terminal UI for disk space analysis.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        metavar="PATH",
        help="Starting directory (default: current working directory)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--log-file",
        metavar="FILE",
        type=Path,
        default=None,
        dest="log_file",
        help="Log file path (default: danalyze.log, only used with --debug)",
    )
    parser.add_argument(
        "-o",
        metavar="OUTPUT_CSV",
        dest="output_csv",
        type=Path,
        default=None,
        help="Pre-load notes from a previous export CSV",
    )
    parser.add_argument(
        "--script",
        metavar="JSON",
        type=str,
        default=None,
        dest="script",
        help='JSON array of inputs, e.g. \'["key.down", "[my note]", "key.enter"]\'',
    )

    args = parser.parse_args(argv)

    start: Path = Path(args.path).resolve() if args.path is not None else Path.cwd()

    if not start.is_dir():
        sys.exit(f"Error: not a directory: {start}")

    notes: dict[str, str] = {}
    if args.output_csv is not None:
        try:
            notes = load_notes_from_csv(args.output_csv)
        except ExportError as exc:
            sys.exit(f"Error loading {args.output_csv}: {exc}")

    scripted_inputs: list[str] | None = None
    if args.script is not None:
        try:
            scripted_inputs = parse_script_arg(args.script)
        except ValueError as exc:
            sys.exit(f"Error: invalid --script value: {exc}")

    setup_logging(debug=args.debug, log_file=args.log_file)

    usage = shutil.disk_usage(start)
    drive_info = DriveInfo(
        device=str(start),
        total=usage.total,
        used=usage.used,
        free=usage.free,
        mount_point=start,
    )
    root = FileNode(path=start, name=start.name or str(start), is_dir=True)
    fs = RealFilesystem()
    scanner = DiskScanner(fs)
    asyncio.run(scanner.list_directory(root))
    state = AppState(
        view_root=root,
        selected_index=0,
        notes=notes,
        mode=AppMode.BROWSE,
        pending_input="",
        drive_info=drive_info,
        tree=FileTree(root=root),
    )
    app = DiskAnalyzerApp(state=state, scanner=scanner, scripted_inputs=scripted_inputs)
    if scripted_inputs is not None:
        app.run(headless=True, size=(120, 40))
    else:
        app.run()


def cli() -> None:
    """Console script entry point.

    Returns:
        None
    """
    main()


if __name__ == "__main__":
    main()
