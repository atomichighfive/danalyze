"""TUI integration tests using Textual's Pilot."""

from __future__ import annotations

from unittest.mock import MagicMock

from danalyze.tui.app import DiskAnalyzerApp
from danalyze.tui.widgets import FileTreePanel, InfoBar, SizePanel, StatusBar

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(base_state, **state_overrides):
    state = base_state(**state_overrides)
    return DiskAnalyzerApp(state=state, scanner=MagicMock())


# ---------------------------------------------------------------------------
# Phase 9: static layout and rendering
# ---------------------------------------------------------------------------


async def test_app_mounts_without_error(base_state) -> None:
    app = _make_app(base_state)
    async with app.run_test():
        pass


async def test_infobar_shows_device_name(base_state) -> None:
    app = _make_app(base_state)
    async with app.run_test():
        text = app.query_one(InfoBar).render().plain
        assert "/dev/sda1" in text


async def test_infobar_shows_sizes(base_state) -> None:
    app = _make_app(base_state)
    async with app.run_test():
        text = app.query_one(InfoBar).render().plain
        # Should contain some size strings
        assert "GB" in text or "MB" in text


async def test_file_tree_panel_shows_child_names(base_state, sample_tree) -> None:
    app = _make_app(base_state)
    async with app.run_test():
        text = app.query_one(FileTreePanel).render().plain
        for child in sample_tree.children:
            assert child.name in text


async def test_file_tree_panel_error_has_exclamation(base_state, sample_tree) -> None:
    app = _make_app(base_state)
    async with app.run_test():
        text = app.query_one(FileTreePanel).render().plain
        # private/ is the ERROR child
        lines = text.splitlines()
        error_line = next(ln for ln in lines if "private" in ln)
        assert "!" in error_line


async def test_file_tree_panel_error_has_error_tag(base_state, sample_tree) -> None:
    app = _make_app(base_state)
    async with app.run_test():
        text = app.query_one(FileTreePanel).render().plain
        lines = text.splitlines()
        error_line = next(ln for ln in lines if "private" in ln)
        assert "[error]" in error_line


async def test_file_tree_panel_noted_entry_has_tag(base_state, sample_tree) -> None:
    # Add a note on the first child (docs)
    path_key = str(sample_tree.children[0].path)
    app = _make_app(base_state, notes={path_key: "my note"})
    async with app.run_test():
        text = app.query_one(FileTreePanel).render().plain
        lines = text.splitlines()
        noted_line = next(ln for ln in lines if "docs" in ln)
        assert "[note]" in noted_line


async def test_size_panel_error_entry_shows_error_message(base_state, sample_tree) -> None:
    app = _make_app(base_state)
    async with app.run_test():
        text = app.query_one(SizePanel).render().plain
        # private/ error is "permission denied"
        assert "permission denied" in text


async def test_size_panel_non_done_entry_shows_dash(base_state) -> None:
    app = _make_app(base_state)
    async with app.run_test():
        text = app.query_one(SizePanel).render().plain
        # docs and downloads are LISTED — should show "---"
        assert "---" in text


async def test_size_panel_done_entry_shows_bar(base_state) -> None:
    app = _make_app(base_state)
    async with app.run_test():
        text = app.query_one(SizePanel).render().plain
        # readme.txt is DONE with size 1024 — should have bar chars
        assert "█" in text or "░" in text


async def test_status_bar_mounted(base_state) -> None:
    app = _make_app(base_state)
    async with app.run_test():
        # StatusBar must be present in the DOM
        assert app.query_one(StatusBar) is not None


async def test_all_four_panels_present(base_state) -> None:
    app = _make_app(base_state)
    async with app.run_test():
        assert app.query_one(InfoBar) is not None
        assert app.query_one(FileTreePanel) is not None
        assert app.query_one(SizePanel) is not None
        assert app.query_one(StatusBar) is not None
