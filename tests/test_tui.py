"""TUI integration tests using Textual's Pilot."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from danalyze.filesystem import InMemoryFilesystem
from danalyze.models import AppMode, DriveInfo, FileNode, FileTree, ScanStatus, SortMode
from danalyze.scanner import DiskScanner
from danalyze.state import AppState
from danalyze.tui.app import DiskAnalyzerApp
from danalyze.tui.widgets import (
    FileTreePanel,
    InfoBar,
    NoteOverlay,
    PromptOverlay,
    SizePanel,
    StatusBar,
)

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


async def test_infobar_shows_view_root_path(base_state) -> None:
    app = _make_app(base_state)
    async with app.run_test():
        text = app.query_one(InfoBar).render().plain
        # InfoBar shows current view_root path relative to tree root; at root shows "."
        # Path is left-aligned, stats are right-aligned with padding in between
        assert text.startswith(".")
        assert "Total:" in text
        assert "Used:" in text
        assert "Free:" in text


async def test_infobar_truncates_long_path() -> None:
    from pathlib import Path

    from danalyze.models import DriveInfo, FileNode, FileTree
    from danalyze.state import AppState
    from danalyze.tui.app import DiskAnalyzerApp

    # Create tree root at /home
    root_path = Path("/home")
    tree_root = FileNode(path=root_path, name="home", is_dir=True)

    # Create a deeply nested view_root
    deep_path = Path("/home/user/very/long/path/with/many/segments/to/test/truncation/behavior")
    deep_root = FileNode(path=deep_path, name="behavior", is_dir=True)
    drive_info = DriveInfo("/dev/sda1", 500 * 1024**3, 200 * 1024**3, 300 * 1024**3, Path("/"))
    state = AppState(
        view_root=deep_root,
        selected_index=0,
        notes={},
        mode=AppMode.BROWSE,
        pending_input="",
        drive_info=drive_info,
        tree=FileTree(root=tree_root),
    )
    app = DiskAnalyzerApp(state=state, scanner=MagicMock())
    async with app.run_test():
        text = app.query_one(InfoBar).render().plain
        # Long path should be truncated from the left with "./..." indicator
        assert "./..." in text
        # Should still show the stats
        assert "Total:" in text
        assert "Used:" in text
        assert "Free:" in text


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
        assert "my note" in noted_line


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


# ---------------------------------------------------------------------------
# Phase 11: r-key scan integration
# ---------------------------------------------------------------------------


def _scan_app(fs, tree_dict):
    """Build a listed-but-unscanned app from an InMemoryFilesystem spec."""
    root_path_str = next(iter(tree_dict))
    root = FileNode(path=Path(root_path_str), name=root_path_str.lstrip("/"), is_dir=True)
    scanner = DiskScanner(fs)
    return root, scanner


async def _make_scan_app(tree_dict):
    """Create a DiskAnalyzerApp with real scanner, root already listed."""
    fs = InMemoryFilesystem(tree_dict)
    root_path_str = next(iter(tree_dict))
    root = FileNode(path=Path(root_path_str), name=root_path_str.lstrip("/"), is_dir=True)
    scanner = DiskScanner(fs)
    await scanner.list_directory(root)
    state = AppState(
        view_root=root,
        selected_index=0,
        notes={},
        mode=AppMode.BROWSE,
        pending_input="",
        drive_info=DriveInfo("/dev/sda1", 500 * 1024**3, 200 * 1024**3, 300 * 1024**3, Path("/")),
        tree=FileTree(root=root),
    )
    return DiskAnalyzerApp(state=state, scanner=scanner), fs


async def test_r_key_scan_shows_sizes() -> None:
    """After pressing r, SizePanel should show bar chars instead of '---'."""
    app, _ = await _make_scan_app({"/root": {"docs": {"a.txt": 100, "b.txt": 200}}})
    async with app.run_test() as pilot:
        await pilot.press("r")
        await app.workers.wait_for_complete()
        text = app.query_one(SizePanel).render().plain
        assert "---" not in text
        assert "█" in text or "░" in text


async def test_r_key_scan_error_dir_shows_exclamation() -> None:
    """After pressing r, a permission-denied directory gets '!' prefix."""
    app, fs = await _make_scan_app({"/root": {"private": {}, "file.txt": 512}})
    fs.set_permission_denied("/root/private")
    async with app.run_test() as pilot:
        await pilot.press("r")
        await app.workers.wait_for_complete()
        text = app.query_one(FileTreePanel).render().plain
        lines = text.splitlines()
        private_line = next(ln for ln in lines if "private" in ln)
        assert "!" in private_line


async def test_r_key_scan_error_dir_shows_error_in_size_panel() -> None:
    """After pressing r, a permission-denied directory shows error text in SizePanel."""
    app, fs = await _make_scan_app({"/root": {"private": {}, "file.txt": 512}})
    fs.set_permission_denied("/root/private")
    async with app.run_test() as pilot:
        await pilot.press("r")
        await app.workers.wait_for_complete()
        text = app.query_one(SizePanel).render().plain
        assert "permission denied" in text.lower() or "error" in text.lower()


async def test_r_key_rescan_reflects_updated_size() -> None:
    """Pressing r twice after update_file_size shows the new size."""
    app, fs = await _make_scan_app({"/root": {"file.txt": 100}})
    async with app.run_test() as pilot:
        await pilot.press("r")
        await app.workers.wait_for_complete()
        text_before = app.query_one(SizePanel).render().plain

        fs.update_file_size("/root/file.txt", 999_999)

        await pilot.press("r")
        await app.workers.wait_for_complete()
        text_after = app.query_one(SizePanel).render().plain

        assert text_before != text_after


async def test_r_key_widgets_update_without_restart() -> None:
    """Widget content changes after scan — no full app restart required."""
    app, _ = await _make_scan_app({"/root": {"data.bin": 4096}})
    async with app.run_test() as pilot:
        text_before = app.query_one(SizePanel).render().plain
        await pilot.press("r")
        await app.workers.wait_for_complete()
        text_after = app.query_one(SizePanel).render().plain
        assert text_before != text_after


# ---------------------------------------------------------------------------
# Phase 12: TUI overlays
# ---------------------------------------------------------------------------


async def test_enter_mounts_note_overlay(base_state) -> None:
    """Pressing enter in BROWSE mode mounts a NoteOverlay."""
    app = _make_app(base_state)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        assert app.query(NoteOverlay)


async def test_type_note_and_submit_saves_note(base_state, sample_tree) -> None:
    """Typing a note and pressing enter saves it and shows [note] tag."""
    app = _make_app(base_state)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        for char in "hello":
            await pilot.press(char)
        await pilot.press("enter")
        assert not app.query(NoteOverlay)
        text = app.query_one(FileTreePanel).render().plain
        assert "hello" in text


async def test_enter_on_noted_entry_prefills_overlay(base_state, sample_tree) -> None:
    """Opening note overlay on an already-noted entry pre-fills with existing text."""
    path_key = str(sample_tree.children[0].path)
    app = _make_app(base_state, notes={path_key: "existing"})
    async with app.run_test() as pilot:
        await pilot.press("enter")
        text = app.query_one(NoteOverlay).render().plain
        assert "existing" in text


async def test_empty_submit_removes_note(base_state, sample_tree) -> None:
    """Submitting an empty note removes it and hides the [note] tag."""
    path_key = str(sample_tree.children[0].path)
    app = _make_app(base_state, notes={path_key: "to remove"})
    async with app.run_test() as pilot:
        await pilot.press("enter")
        for _ in "to remove":
            await pilot.press("backspace")
        await pilot.press("enter")
        text = app.query_one(FileTreePanel).render().plain
        assert "to remove" not in text


async def test_escape_cancels_note_without_saving(base_state) -> None:
    """Escape inside NoteOverlay dismisses it without saving."""
    app = _make_app(base_state)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        for char in "typed":
            await pilot.press(char)
        await pilot.press("escape")
        assert not app.query(NoteOverlay)
        text = app.query_one(FileTreePanel).render().plain
        assert "typed" not in text


async def test_q_mounts_quit_prompt(base_state) -> None:
    """Pressing q in BROWSE mode mounts a PromptOverlay for quit."""
    app = _make_app(base_state)
    async with app.run_test() as pilot:
        await pilot.press("q")
        assert app.query(PromptOverlay)


async def test_y_in_quit_prompt_exits_app(base_state) -> None:
    """Pressing y inside the quit PromptOverlay exits the app cleanly."""
    app = _make_app(base_state)
    async with app.run_test() as pilot:
        await pilot.press("q")
        await pilot.press("y")
    # reaching here means the app exited without error


async def test_n_in_quit_prompt_dismisses_overlay(base_state) -> None:
    """Pressing n inside the quit PromptOverlay dismisses it."""
    app = _make_app(base_state)
    async with app.run_test() as pilot:
        await pilot.press("q")
        await pilot.press("n")
        assert not app.query(PromptOverlay)


async def test_escape_in_quit_prompt_dismisses_overlay(base_state) -> None:
    """Pressing escape inside the quit PromptOverlay dismisses it."""
    app = _make_app(base_state)
    async with app.run_test() as pilot:
        await pilot.press("q")
        await pilot.press("escape")
        assert not app.query(PromptOverlay)


async def test_w_mounts_save_prompt(base_state) -> None:
    """Pressing w in BROWSE mode mounts a PromptOverlay for file save."""
    app = _make_app(base_state)
    async with app.run_test() as pilot:
        await pilot.press("w")
        assert app.query(PromptOverlay)


async def test_save_new_file_creates_file(base_state, tmp_path) -> None:
    """Typing a new filename and pressing enter creates the file and dismisses the overlay."""
    app = _make_app(base_state)
    filepath = tmp_path / "out.csv"
    async with app.run_test() as pilot:
        await pilot.press("w")
        for char in str(filepath):
            await pilot.press(char)
        await pilot.press("enter")
        assert not app.query(PromptOverlay)
        assert filepath.exists()


async def test_save_existing_file_shows_error_and_stays_open(base_state, tmp_path) -> None:
    """Typing an existing filename shows an error and keeps the overlay open."""
    app = _make_app(base_state)
    filepath = tmp_path / "existing.csv"
    filepath.write_text("already here")
    async with app.run_test() as pilot:
        await pilot.press("w")
        for char in str(filepath):
            await pilot.press(char)
        await pilot.press("enter")
        assert app.query(PromptOverlay)
        text = app.query_one(PromptOverlay).render().plain
        assert "exist" in text.lower() or "error" in text.lower()


async def test_escape_in_save_prompt_dismisses_without_writing(base_state, tmp_path) -> None:
    """Escape inside the save PromptOverlay dismisses it without writing any file."""
    app = _make_app(base_state)
    filepath = tmp_path / "never.csv"
    async with app.run_test() as pilot:
        await pilot.press("w")
        for char in str(filepath):
            await pilot.press(char)
        await pilot.press("escape")
        assert not app.query(PromptOverlay)
        assert not filepath.exists()


# ---------------------------------------------------------------------------
# Phase 12C: full-row cursor highlight
# ---------------------------------------------------------------------------


def test_size_panel_selected_row_has_reverse_style(base_state) -> None:
    """SizePanel._build() applies reverse-video to the selected row."""
    from rich.text import Text

    state = base_state(selected_index=2)  # readme.txt is DONE — has a real size
    result = SizePanel._build(state)
    assert isinstance(result, Text)
    reverse_spans = [s for s in result._spans if str(s.style) == "reverse"]
    assert len(reverse_spans) == 1


def test_size_panel_non_selected_rows_have_no_reverse_style(base_state) -> None:
    """Only the selected row carries reverse-video; all others are unstyled."""
    state = base_state(selected_index=0)  # docs/ selected; 4 children total
    result = SizePanel._build(state)
    reverse_spans = [s for s in result._spans if str(s.style) == "reverse"]
    assert len(reverse_spans) == 1


# ---------------------------------------------------------------------------
# Phase 12D: inline note text display
# ---------------------------------------------------------------------------


async def test_file_tree_shows_note_text_inline(base_state, sample_tree) -> None:
    """Noted entry shows the actual note text wrapped in double quotes."""
    path_key = str(sample_tree.children[0].path)
    app = _make_app(base_state, notes={path_key: "important archive"})
    async with app.run_test():
        text = app.query_one(FileTreePanel).render().plain
        lines = text.splitlines()
        noted_line = next(ln for ln in lines if "docs" in ln)
        assert '"important archive"' in noted_line


def test_file_tree_long_note_truncated(base_state, sample_tree) -> None:
    """Long notes are truncated to fit the panel width and end with '...\\"'."""
    path_key = str(sample_tree.children[0].path)
    state = base_state(notes={path_key: "x" * 100})
    # width=30, name="docs/" (5): available = 30-5-6 = 19
    # full '"xxx...xxx"' = 102 > 19 → truncate; N = 19-5 = 14
    result = FileTreePanel._build(state, width=30)
    noted_line = next(ln for ln in result.plain.splitlines() if "docs" in ln)
    assert noted_line.endswith('..."')


async def test_file_tree_no_note_token(base_state, sample_tree) -> None:
    """The literal string '[note]' never appears in the rendered tree."""
    path_key = str(sample_tree.children[0].path)
    app = _make_app(base_state, notes={path_key: "any note"})
    async with app.run_test():
        text = app.query_one(FileTreePanel).render().plain
        assert "[note]" not in text


# ---------------------------------------------------------------------------
# Phase: sort toggle
# ---------------------------------------------------------------------------


async def test_s_key_changes_sort_mode_to_size(base_state) -> None:
    """Pressing s in BROWSE mode switches sort_mode to SIZE."""
    app = _make_app(base_state)
    async with app.run_test() as pilot:
        await pilot.press("s")
        assert app._state.sort_mode == SortMode.SIZE


async def test_s_key_twice_returns_to_alpha(base_state) -> None:
    """Pressing s twice returns sort_mode to ALPHA."""
    app = _make_app(base_state)
    async with app.run_test() as pilot:
        await pilot.press("s")
        await pilot.press("s")
        assert app._state.sort_mode == SortMode.ALPHA


async def test_alpha_mode_file_tree_renders_in_name_order() -> None:
    """In ALPHA mode the file tree renders entries sorted by name."""
    fs = InMemoryFilesystem({"/root": {"zebra": {}, "apple": {}, "mango": {}}})
    root = FileNode(path=Path("/root"), name="root", is_dir=True)
    scanner = DiskScanner(fs)
    await scanner.list_directory(root)
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
    async with app.run_test():
        text = app.query_one(FileTreePanel).render().plain
        names = [ln.strip().lstrip(">! ").rstrip("/") for ln in text.splitlines() if ln.strip()]
        assert names == sorted(names, key=str.lower)


async def test_size_mode_file_tree_shows_largest_first() -> None:
    """After scanning and pressing s, the largest entry appears first."""
    app, _ = await _make_scan_app({"/root": {"small.txt": 100, "big.txt": 5000, "mid.txt": 1000}})
    async with app.run_test() as pilot:
        await pilot.press("r")
        await app.workers.wait_for_complete()
        await pilot.press("s")
        text = app.query_one(FileTreePanel).render().plain
        first_line = [ln for ln in text.splitlines() if ln.strip()][0]
        assert "big" in first_line


async def test_size_panel_matches_file_tree_order_after_sort() -> None:
    """SizePanel row count matches FileTreePanel row count after sort toggle."""
    app, _ = await _make_scan_app({"/root": {"small.txt": 100, "big.txt": 5000}})
    async with app.run_test() as pilot:
        await pilot.press("r")
        await app.workers.wait_for_complete()
        await pilot.press("s")
        tree_lines = [
            ln for ln in app.query_one(FileTreePanel).render().plain.splitlines() if ln.strip()
        ]
        size_lines = [
            ln for ln in app.query_one(SizePanel).render().plain.splitlines() if ln.strip()
        ]
        assert len(tree_lines) == len(size_lines)
        assert "big" in tree_lines[0]


async def test_status_bar_shows_sort_hint(base_state) -> None:
    """StatusBar hint text includes the [s] sort shortcut."""
    app = _make_app(base_state)
    async with app.run_test():
        text = app.query_one(StatusBar).render().plain
        assert "sort" in text.lower()


# ---------------------------------------------------------------------------
# Phase 15: symlink icon
# ---------------------------------------------------------------------------


def test_file_tree_symlink_shows_at_icon(base_state) -> None:
    """Symlink entries use '@' as prefix, not '>' or ' '."""
    symlink_node = FileNode(
        path=Path("/root/link"),
        name="link",
        is_dir=True,
        is_symlink=True,
        scan_status=ScanStatus.UNSCANNED,
    )
    root = FileNode(
        path=Path("/root"),
        name="root",
        is_dir=True,
        children=[symlink_node],
        scan_status=ScanStatus.LISTED,
    )
    state = base_state(view_root=root)
    text = FileTreePanel._build(state).plain
    lines = text.splitlines()
    link_line = next(ln for ln in lines if "link" in ln)
    assert "@" in link_line
    assert link_line.strip().startswith("@")


def test_file_tree_symlink_to_file_shows_at_icon(base_state) -> None:
    """Symlink-to-file also uses '@' prefix."""
    symlink_node = FileNode(
        path=Path("/root/lnk"),
        name="lnk",
        is_dir=False,
        is_symlink=True,
        scan_status=ScanStatus.UNSCANNED,
    )
    root = FileNode(
        path=Path("/root"),
        name="root",
        is_dir=True,
        children=[symlink_node],
        scan_status=ScanStatus.LISTED,
    )
    state = base_state(view_root=root)
    text = FileTreePanel._build(state).plain
    lines = text.splitlines()
    link_line = next(ln for ln in lines if "lnk" in ln)
    assert link_line.strip().startswith("@")
