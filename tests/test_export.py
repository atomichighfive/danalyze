"""Tests for danalyze.export — build_export_df, write_export, load_notes_from_csv."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from danalyze.exceptions import ExportError
from danalyze.export import build_export_df, load_notes_from_csv, write_export
from danalyze.models import FileNode, ScanStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _file(path: str, size: int, status: ScanStatus = ScanStatus.DONE) -> FileNode:
    p = Path(path)
    return FileNode(path=p, name=p.name, is_dir=False, size=size, scan_status=status)


def _dir(path: str, status: ScanStatus = ScanStatus.DONE, size: int = 0) -> FileNode:
    p = Path(path)
    return FileNode(path=p, name=p.name, is_dir=True, size=size, scan_status=status)


# ---------------------------------------------------------------------------
# build_export_df
# ---------------------------------------------------------------------------


def test_build_export_df_done_node_with_note() -> None:
    node = _file("/home/user/docs", 1024)
    notes = {"/home/user/docs": "important"}
    df = build_export_df(notes, {"/home/user/docs": node})
    row = df[df["path"] == "/home/user/docs"].iloc[0]
    assert row["size_bytes"] == 1024
    assert row["note"] == "important"
    assert isinstance(row["size_human"], str) and len(row["size_human"]) > 0


def test_build_export_df_error_node_with_note_has_na_size() -> None:
    node = _file("/home/user/secret", 0, ScanStatus.ERROR)
    notes = {"/home/user/secret": "check this"}
    df = build_export_df(notes, {"/home/user/secret": node})
    row = df[df["path"] == "/home/user/secret"].iloc[0]
    assert pd.isna(row["size_bytes"])
    assert row["note"] == "check this"


def test_build_export_df_done_node_no_note_included() -> None:
    node = _file("/home/user/large.bin", 9999)
    df = build_export_df({}, {"/home/user/large.bin": node})
    assert "/home/user/large.bin" in df["path"].values
    row = df[df["path"] == "/home/user/large.bin"].iloc[0]
    assert row["note"] == ""


def test_build_export_df_unscanned_node_no_note_excluded() -> None:
    node = _file("/home/user/unscanned.txt", 0, ScanStatus.UNSCANNED)
    df = build_export_df({}, {"/home/user/unscanned.txt": node})
    assert "/home/user/unscanned.txt" not in df["path"].values


def test_build_export_df_listed_node_no_note_excluded() -> None:
    node = _dir("/home/user/somedir", ScanStatus.LISTED)
    df = build_export_df({}, {"/home/user/somedir": node})
    assert "/home/user/somedir" not in df["path"].values


def test_build_export_df_note_only_path_not_in_nodes() -> None:
    # A path that has a note but no matching node (e.g. from a previous session)
    notes = {"/old/path": "remembered"}
    df = build_export_df(notes, {})
    assert "/old/path" in df["path"].values
    row = df[df["path"] == "/old/path"].iloc[0]
    assert pd.isna(row["size_bytes"])
    assert row["note"] == "remembered"


def test_build_export_df_columns() -> None:
    df = build_export_df({}, {})
    assert list(df.columns) == ["path", "size_bytes", "size_human", "note"]


def test_build_export_df_empty_inputs() -> None:
    df = build_export_df({}, {})
    assert len(df) == 0


def test_build_export_df_size_human_correct_for_done_node() -> None:
    node = _file("/f", 1024)
    df = build_export_df({}, {"/f": node})
    row = df[df["path"] == "/f"].iloc[0]
    assert row["size_human"] == "1.0 KB"


def test_build_export_df_size_human_empty_for_non_done_node() -> None:
    node = _file("/f", 0, ScanStatus.ERROR)
    df = build_export_df({"/f": "note"}, {"/f": node})
    row = df[df["path"] == "/f"].iloc[0]
    assert row["size_human"] == ""


# ---------------------------------------------------------------------------
# write_export
# ---------------------------------------------------------------------------


def test_write_export_creates_file(tmp_path: Path) -> None:
    dest = tmp_path / "out.csv"
    node = _file("/home/user/docs", 2048)
    df = build_export_df({"/home/user/docs": "saved"}, {"/home/user/docs": node})
    write_export(df, dest)
    assert dest.exists()


def test_write_export_roundtrip(tmp_path: Path) -> None:
    dest = tmp_path / "out.csv"
    node = _file("/home/user/docs", 2048)
    df = build_export_df({"/home/user/docs": "saved"}, {"/home/user/docs": node})
    write_export(df, dest)
    read_back = pd.read_csv(dest)
    assert read_back.iloc[0]["path"] == "/home/user/docs"
    assert read_back.iloc[0]["note"] == "saved"


def test_write_export_raises_if_file_exists(tmp_path: Path) -> None:
    dest = tmp_path / "out.csv"
    dest.write_text("existing")
    df = build_export_df({}, {})
    with pytest.raises(ExportError):
        write_export(df, dest)


# ---------------------------------------------------------------------------
# load_notes_from_csv
# ---------------------------------------------------------------------------


def test_load_notes_roundtrip(tmp_path: Path) -> None:
    dest = tmp_path / "notes.csv"
    node = _file("/home/user/docs", 1024)
    df = build_export_df({"/home/user/docs": "my note"}, {"/home/user/docs": node})
    write_export(df, dest)
    result = load_notes_from_csv(dest)
    assert result == {"/home/user/docs": "my note"}


def test_load_notes_skips_empty_note_rows(tmp_path: Path) -> None:
    dest = tmp_path / "notes.csv"
    node_a = _file("/a", 100)
    node_b = _file("/b", 200)
    df = build_export_df({"/a": "keep", "/b": ""}, {"/a": node_a, "/b": node_b})
    write_export(df, dest)
    result = load_notes_from_csv(dest)
    assert "/a" in result
    assert "/b" not in result


def test_load_notes_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ExportError):
        load_notes_from_csv(tmp_path / "nonexistent.csv")


def test_load_notes_missing_note_column_raises(tmp_path: Path) -> None:
    dest = tmp_path / "bad.csv"
    dest.write_text("path,size_bytes\n/a,100\n")
    with pytest.raises(ExportError):
        load_notes_from_csv(dest)


def test_load_notes_missing_path_column_raises(tmp_path: Path) -> None:
    dest = tmp_path / "bad.csv"
    dest.write_text("size_bytes,note\n100,hello\n")
    with pytest.raises(ExportError):
        load_notes_from_csv(dest)


def test_load_notes_skips_nan_note_rows(tmp_path: Path) -> None:
    dest = tmp_path / "notes.csv"
    # Write a CSV where some note values are NaN (empty cell)
    dest.write_text("path,size_bytes,size_human,note\n/a,100,100 B,keep\n/b,200,200 B,\n")
    result = load_notes_from_csv(dest)
    assert result == {"/a": "keep"}
