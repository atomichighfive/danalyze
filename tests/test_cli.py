"""Tests for danalyze.__main__ CLI entry point."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import danalyze.__main__ as cli


def test_main_valid_path_does_not_raise(tmp_path: Path) -> None:
    with (
        patch("danalyze.tui.app.DiskAnalyzerApp.run"),
        patch("danalyze.__main__.setup_logging"),
    ):
        cli.main([str(tmp_path)])


def test_main_nonexistent_path_exits(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main([str(tmp_path / "no_such_dir")])
    assert exc_info.value.code != 0


def test_main_output_csv_nonexistent_exits(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main([str(tmp_path), "-o", str(tmp_path / "missing.csv")])
    assert exc_info.value.code != 0


def test_main_output_csv_preloads_notes(tmp_path: Path) -> None:
    from danalyze.export import build_notes_df, write_export

    notes_csv = tmp_path / "notes.csv"
    write_export(build_notes_df({"/some/path": "my note"}), notes_csv)

    captured: dict = {}

    def fake_run(self) -> None:
        captured["notes"] = dict(self._state.notes)

    with (
        patch("danalyze.tui.app.DiskAnalyzerApp.run", fake_run),
        patch("danalyze.__main__.setup_logging"),
    ):
        cli.main([str(tmp_path), "-o", str(notes_csv)])

    assert captured["notes"] == {"/some/path": "my note"}


def test_main_debug_flag_calls_setup_logging_debug(tmp_path: Path) -> None:
    with (
        patch("danalyze.tui.app.DiskAnalyzerApp.run"),
        patch("danalyze.__main__.setup_logging") as mock_setup,
    ):
        cli.main([str(tmp_path), "--debug"])
    mock_setup.assert_called_once()
    assert mock_setup.call_args.kwargs["debug"] is True


def test_main_default_path_is_cwd(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    captured: dict = {}

    def fake_run(self) -> None:
        captured["path"] = self._state.view_root.path

    with (
        patch("danalyze.tui.app.DiskAnalyzerApp.run", fake_run),
        patch("danalyze.__main__.setup_logging"),
    ):
        cli.main([])

    assert captured["path"].resolve() == tmp_path.resolve()
