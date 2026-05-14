"""Tests for danalyze.__main__ CLI entry point."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

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


# Phase 2: CLI --script Argument Tests


def test_script_flag_valid_json_accepted(tmp_path: Path) -> None:
    """No exit when --script is a well-formed list of strings."""
    with (
        patch("danalyze.__main__.DiskAnalyzerApp") as mock_app_class,
        patch("danalyze.__main__.setup_logging"),
        patch("danalyze.__main__.asyncio.run", side_effect=lambda c: c.close()),
    ):
        mock_app = MagicMock()
        mock_app_class.return_value = mock_app
        cli.main([str(tmp_path), "--script", '["key.down"]'])
    mock_app_class.assert_called_once()
    # Verify scripted_inputs was passed to the app
    call_kwargs = mock_app_class.call_args.kwargs
    assert "scripted_inputs" in call_kwargs
    assert call_kwargs["scripted_inputs"] == ["key.down"]


def test_script_flag_invalid_json_exits(tmp_path: Path) -> None:
    """Malformed JSON for --script exits with non-zero code."""
    with (
        patch("danalyze.tui.app.DiskAnalyzerApp.run"),
        patch("danalyze.__main__.setup_logging"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            cli.main([str(tmp_path), "--script", "not json"])
        assert exc_info.value.code != 0


def test_script_flag_non_list_exits(tmp_path: Path) -> None:
    """Valid JSON but not a list for --script exits with non-zero code."""
    with (
        patch("danalyze.tui.app.DiskAnalyzerApp.run"),
        patch("danalyze.__main__.setup_logging"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            cli.main([str(tmp_path), "--script", '"hello"'])
        assert exc_info.value.code != 0


def test_script_arg_none_by_default(tmp_path: Path) -> None:
    """No --script flag results in scripted_inputs=None on app."""
    with (
        patch("danalyze.__main__.DiskAnalyzerApp") as mock_app_class,
        patch("danalyze.__main__.setup_logging"),
        patch("danalyze.__main__.asyncio.run", side_effect=lambda c: c.close()),
    ):
        mock_app = MagicMock()
        mock_app_class.return_value = mock_app
        cli.main([str(tmp_path)])
    mock_app_class.assert_called_once()
    call_kwargs = mock_app_class.call_args.kwargs
    assert call_kwargs.get("scripted_inputs") is None


def test_script_uses_headless_run(tmp_path: Path) -> None:
    """--script flag causes app.run to be called with headless=True."""
    with (
        patch("danalyze.__main__.DiskAnalyzerApp") as mock_app_class,
        patch("danalyze.__main__.setup_logging"),
        patch("danalyze.__main__.asyncio.run", side_effect=lambda c: c.close()),
    ):
        mock_app = MagicMock()
        mock_app_class.return_value = mock_app
        cli.main([str(tmp_path), "--script", '["key.down"]'])
    mock_app.run.assert_called_once_with(headless=True, size=(120, 40))


def test_no_script_uses_normal_run(tmp_path: Path) -> None:
    """No --script flag causes app.run to be called without headless=True."""
    with (
        patch("danalyze.__main__.DiskAnalyzerApp") as mock_app_class,
        patch("danalyze.__main__.setup_logging"),
        patch("danalyze.__main__.asyncio.run", side_effect=lambda c: c.close()),
    ):
        mock_app = MagicMock()
        mock_app_class.return_value = mock_app
        cli.main([str(tmp_path)])
    # Should be called with no arguments
    mock_app.run.assert_called_once_with()
