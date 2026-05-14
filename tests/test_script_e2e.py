"""End-to-end tests for scripted-mode CLI wiring."""

from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import danalyze.__main__ as cli


class TestMainScriptFlagWiring:
    """Tests for --script flag wiring through main()."""

    def test_main_script_flag_wires_inputs_to_app(self, tmp_path: Path) -> None:
        """--script flag passes parsed inputs to DiskAnalyzerApp."""
        with (
            patch("danalyze.__main__.DiskAnalyzerApp") as mock_app_class,
            patch("danalyze.__main__.setup_logging"),
            patch("danalyze.__main__.asyncio.run", side_effect=lambda c: c.close()),
        ):
            mock_app = MagicMock()
            mock_app_class.return_value = mock_app
            cli.main([str(tmp_path), "--script", '["key.down"]'])
        mock_app_class.assert_called_once()
        call_kwargs = mock_app_class.call_args.kwargs
        assert "scripted_inputs" in call_kwargs
        assert call_kwargs["scripted_inputs"] == ["key.down"]

    def test_main_script_invalid_json_exits(self, tmp_path: Path) -> None:
        """Invalid JSON for --script exits with non-zero code."""
        with (
            patch("danalyze.tui.app.DiskAnalyzerApp.run"),
            patch("danalyze.__main__.setup_logging"),
            patch("danalyze.__main__.asyncio.run"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                cli.main([str(tmp_path), "--script", "bad-json"])
            assert exc_info.value.code != 0

    def test_main_without_script_scripted_inputs_is_none(self, tmp_path: Path) -> None:
        """No --script flag results in scripted_inputs=None."""
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

    def test_main_script_runs_headless(self, tmp_path: Path) -> None:
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


class TestScriptedModeIntegration:
    """Integration tests for full scripted-mode runs."""

    def test_main_script_full_run_wires_correctly(self, tmp_path: Path, monkeypatch) -> None:
        """Full run with --script wires app correctly for headless execution."""
        # Create a test directory structure
        test_dir = tmp_path / "test_root"
        test_dir.mkdir()
        (test_dir / "apple").mkdir()
        (test_dir / "zebra").mkdir()

        mock_stdout = StringIO()
        monkeypatch.setattr(sys, "stdout", mock_stdout)

        # Track whether app.run was called with headless=True
        run_calls = []

        def track_run(self, *args, **kwargs):
            run_calls.append((args, kwargs))

        with (
            patch("danalyze.__main__.asyncio.run", side_effect=lambda c: c.close()),
            patch("danalyze.__main__.setup_logging"),
            patch("danalyze.__main__.DiskAnalyzerApp.run", track_run),
        ):
            cli.main([str(test_dir), "--script", '["key.down"]'])

        # Verify app.run was called with headless=True
        assert len(run_calls) == 1
        assert run_calls[0][1].get("headless") is True
        assert run_calls[0][1].get("size") == (120, 40)
