"""CSV export and import for annotated disk-usage data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from danalyze.exceptions import ExportError


def build_notes_df(notes: dict[str, str]) -> pd.DataFrame:
    """Build a two-column DataFrame containing only paths that have notes.

    Args:
        notes: Mapping of absolute path string to note text.

    Returns:
        DataFrame with columns: path, note.
        Only rows where note is a non-empty string are included,
        sorted by path.
    """
    rows = [{"path": p, "note": n} for p, n in sorted(notes.items()) if n]
    return pd.DataFrame(rows, columns=["path", "note"])


def write_export(df: pd.DataFrame, file_path: Path) -> None:
    """Write a DataFrame to a CSV file.

    Args:
        df: DataFrame to write.
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
