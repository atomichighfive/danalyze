"""TUI integration tests using Textual's Pilot."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from danalyze.filesystem import InMemoryFilesystem
from danalyze.models import AppMode, DriveInfo, FileNode, FileTree
from danalyze.scanner import DiskScanner
from danalyze.state import AppState
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


# ---------------------------------------------------------------------------
# Phase 10: arrow-key navigation
# ---------------------------------------------------------------------------


def _nav_app(base_state, **overrides) -> DiskAnalyzerApp:
    """Create an app with an AsyncMock scanner for navigation tests."""
    scanner = MagicMock()
    scanner.list_directory = AsyncMock()
    return DiskAnalyzerApp(state=base_state(**overrides), scanner=scanner)


async def test_down_increments_selected_index(base_state) -> None:
    app = _nav_app(base_state, selected_index=0)
    async with app.run_test() as pilot:
        await pilot.press("down")
        assert app._state.selected_index == 1


async def test_down_at_last_entry_no_change(base_state, sample_tree) -> None:
    last = len(sample_tree.children) - 1
    app = _nav_app(base_state, selected_index=last)
    async with app.run_test() as pilot:
        await pilot.press("down")
        assert app._state.selected_index == last


async def test_up_decrements_selected_index(base_state) -> None:
    app = _nav_app(base_state, selected_index=2)
    async with app.run_test() as pilot:
        await pilot.press("up")
        assert app._state.selected_index == 1


async def test_up_at_first_entry_no_change(base_state) -> None:
    app = _nav_app(base_state, selected_index=0)
    async with app.run_test() as pilot:
        await pilot.press("up")
        assert app._state.selected_index == 0


async def test_right_on_listed_dir_calls_list_directory(base_state, sample_tree) -> None:
    # index 0 is "docs" (LISTED dir)
    scanner = MagicMock()
    scanner.list_directory = AsyncMock()
    app = DiskAnalyzerApp(state=base_state(selected_index=0), scanner=scanner)
    async with app.run_test() as pilot:
        await pilot.press("right")
        scanner.list_directory.assert_called_once_with(sample_tree.children[0])


async def test_right_on_listed_dir_changes_view_root(base_state, sample_tree) -> None:
    app = _nav_app(base_state, selected_index=0)
    async with app.run_test() as pilot:
        await pilot.press("right")
        assert app._state.view_root is sample_tree.children[0]


async def test_right_on_file_view_root_unchanged(base_state, sample_tree) -> None:
    # index 2 is "readme.txt" (file)
    app = _nav_app(base_state, selected_index=2)
    async with app.run_test() as pilot:
        await pilot.press("right")
        assert app._state.view_root is sample_tree


async def test_right_on_error_node_view_root_unchanged(base_state, sample_tree) -> None:
    # index 3 is "private" (ERROR dir)
    app = _nav_app(base_state, selected_index=3)
    async with app.run_test() as pilot:
        await pilot.press("right")
        assert app._state.view_root is sample_tree


async def test_right_on_error_node_list_directory_not_called(base_state) -> None:
    scanner = MagicMock()
    scanner.list_directory = AsyncMock()
    app = DiskAnalyzerApp(state=base_state(selected_index=3), scanner=scanner)
    async with app.run_test() as pilot:
        await pilot.press("right")
        scanner.list_directory.assert_not_called()


async def test_left_steps_to_parent(base_state, sample_tree) -> None:
    docs = sample_tree.children[0]
    app = _nav_app(base_state, view_root=docs, selected_index=0)
    async with app.run_test() as pilot:
        await pilot.press("left")
        assert app._state.view_root is sample_tree


async def test_left_at_root_no_change(base_state, sample_tree) -> None:
    app = _nav_app(base_state, view_root=sample_tree)
    async with app.run_test() as pilot:
        await pilot.press("left")
        assert app._state.view_root is sample_tree


async def test_right_with_real_scanner_shows_children() -> None:
    """Navigate right into an UNSCANNED dir; verify children appear in the tree panel."""
    fs = InMemoryFilesystem({"/root": {"docs": {"a.txt": 100, "b.txt": 200}}})
    root = FileNode(path=Path("/root"), name="root", is_dir=True)
    scanner = DiskScanner(fs)
    await scanner.list_directory(root)  # root LISTED; docs child is still UNSCANNED

    state = AppState(
        view_root=root,
        selected_index=0,
        notes={},
        mode=AppMode.BROWSE,
        pending_input="",
        drive_info=DriveInfo("/dev/sda1", 500 * 1024**3, 200 * 1024**3, 300 * 1024**3, Path("/")),
        tree=FileTree(root=root),
    )
    app = DiskAnalyzerApp(state=state, scanner=scanner)
    async with app.run_test() as pilot:
        await pilot.press("right")
        text = app.query_one(FileTreePanel).render().plain
        assert "a.txt" in text or "b.txt" in text
