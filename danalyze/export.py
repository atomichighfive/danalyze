"""CSV export and import for annotated disk-usage data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from danalyze.exceptions import ExportError
from danalyze.formatter import format_size
from danalyze.models import FileNode, ScanStatus


def build_export_df(
    notes: dict[str, str],
    nodes: dict[str, FileNode],
) -> pd.DataFrame:
    """Build a pandas DataFrame from notes and scanned nodes.

    Includes a row for every path that either has a note or has
    scan_status == DONE. Paths with notes but no matching node (e.g. from a
    previous session) are included with size_bytes == pd.NA.

    Args:
        notes: Mapping of absolute path string to note text.
        nodes: Mapping of absolute path string to FileNode.

    Returns:
        DataFrame with columns: path, size_bytes, size_human, note.
        size_bytes is int for DONE nodes, pd.NA otherwise.
        size_human is a formatted string for DONE nodes, "" otherwise.
        note is "" when no note exists for that path.
    """
    paths: set[str] = set(notes) | {p for p, n in nodes.items() if n.scan_status == ScanStatus.DONE}

    rows: list[dict] = []
    for path_str in sorted(paths):
        node = nodes.get(path_str)
        is_done = node is not None and node.scan_status == ScanStatus.DONE
        size_bytes: int | pd._libs.missing.NAType = pd.NA
        size_human = ""
        if is_done and node is not None and node.size is not None:
            size_bytes = node.size
            size_human = format_size(node.size)
        rows.append(
            {
                "path": path_str,
                "size_bytes": size_bytes,
                "size_human": size_human,
                "note": notes.get(path_str, ""),
            }
        )

    return pd.DataFrame(rows, columns=["path", "size_bytes", "size_human", "note"])


def write_export(df: pd.DataFrame, file_path: Path) -> None:
    """Write a DataFrame to a CSV file.

    Args:
        df: DataFrame to write (as produced by build_export_df).
        file_path: Destination file path.

    Raises:
        ExportError: If file_path already exists (never overwrites).
        ExportError: On any I/O failure during writing.
    """
    if file_path.exists():
        raise ExportError(f"File already exists: {file_path}")
    try:
        df.to_csv(file_path, index=False)
    except OSError as exc:
        raise ExportError(f"Cannot write {file_path}: {exc}") from exc


def load_notes_from_csv(file_path: Path) -> dict[str, str]:
    """Read an export CSV and return a mapping of path to note text.

    Only rows with a non-empty note string are returned.

    Args:
        file_path: Path to an existing export CSV file.

    Returns:
        Dict mapping absolute path string to note text for rows where note
        is a non-empty string.

    Raises:
        ExportError: If the file does not exist or cannot be read.
        ExportError: If the CSV is missing the required "path" or "note" columns.
    """
    if not file_path.exists():
        raise ExportError(f"File not found: {file_path}")
    try:
        df = pd.read_csv(file_path)
    except Exception as exc:
        raise ExportError(f"Cannot read {file_path}: {exc}") from exc

    missing = {"path", "note"} - set(df.columns)
    if missing:
        raise ExportError(f"CSV missing required columns: {missing}")

    result: dict[str, str] = {}
    for _, row in df.iterrows():
        note = row["note"]
        if pd.notna(note) and str(note).strip():
            result[str(row["path"])] = str(note)
    return result
