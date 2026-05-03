"""Tests for danalyze.export — build_notes_df, write_export, load_notes_from_csv."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from danalyze.exceptions import ExportError
from danalyze.export import build_notes_df, load_notes_from_csv, write_export

# ---------------------------------------------------------------------------
# build_notes_df
# ---------------------------------------------------------------------------


def test_build_notes_df_has_correct_columns() -> None:
    df = build_notes_df({"/a": "note"})
    assert list(df.columns) == ["path", "note"]


def test_build_notes_df_only_includes_noted_paths() -> None:
    df = build_notes_df({"/a": "keep", "/b": ""})
    assert "/a" in df["path"].values
    assert "/b" not in df["path"].values


def test_build_notes_df_empty_notes_returns_empty_df() -> None:
    df = build_notes_df({})
    assert len(df) == 0
    assert list(df.columns) == ["path", "note"]


def test_build_notes_df_note_value_is_correct() -> None:
    df = build_notes_df({"/home/user/docs": "important"})
    row = df[df["path"] == "/home/user/docs"].iloc[0]
    assert row["note"] == "important"


# ---------------------------------------------------------------------------
# write_export
# ---------------------------------------------------------------------------


def test_write_export_creates_file(tmp_path: Path) -> None:
    dest = tmp_path / "out.csv"
    df = build_notes_df({"/home/user/docs": "saved"})
    write_export(df, dest)
    assert dest.exists()


def test_write_export_roundtrip(tmp_path: Path) -> None:
    dest = tmp_path / "out.csv"
    df = build_notes_df({"/home/user/docs": "saved"})
    write_export(df, dest)
    read_back = pd.read_csv(dest)
    assert read_back.iloc[0]["path"] == "/home/user/docs"
    assert read_back.iloc[0]["note"] == "saved"


def test_write_export_raises_if_file_exists(tmp_path: Path) -> None:
    dest = tmp_path / "out.csv"
    dest.write_text("existing")
    with pytest.raises(ExportError):
        write_export(pd.DataFrame(), dest)


# ---------------------------------------------------------------------------
# load_notes_from_csv
# ---------------------------------------------------------------------------


def test_roundtrip_write_and_load(tmp_path: Path) -> None:
    dest = tmp_path / "notes.csv"
    original = {"/home/user/docs": "my note", "/home/user/pics": "another note"}
    df = build_notes_df(original)
    write_export(df, dest)
    result = load_notes_from_csv(dest)
    assert result == original


def test_load_notes_skips_empty_note_rows(tmp_path: Path) -> None:
    dest = tmp_path / "notes.csv"
    df = build_notes_df({"/a": "keep"})
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
    dest.write_text("path,note\n/a,keep\n/b,\n")
    result = load_notes_from_csv(dest)
    assert result == {"/a": "keep"}
