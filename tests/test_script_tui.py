"""Tests for scripted-mode TUI functionality."""

from __future__ import annotations

from unittest.mock import MagicMock

from danalyze.tui.app import DiskAnalyzerApp


def _make_app(base_state, **state_overrides):
    state = base_state(**state_overrides)
    return DiskAnalyzerApp(state=state, scanner=MagicMock())


async def test_capture_contains_infobar_stats(base_state) -> None:
    """Screen capture text contains InfoBar drive stats."""
    app = _make_app(base_state)
    async with app.run_test(size=(80, 24)):
        text = app._capture_screen_as_text()
        assert "Total:" in text
        assert "Free:" in text


async def test_capture_contains_child_names(base_state) -> None:
    """Screen capture text contains all child filenames from the tree."""
    app = _make_app(base_state)
    async with app.run_test(size=(80, 24)):
        text = app._capture_screen_as_text()
        # sample_tree has: docs/, downloads/, readme.txt, private/
        assert "docs/" in text or "docs" in text
        assert "downloads/" in text or "downloads" in text
        assert "readme.txt" in text
        assert "private/" in text or "private" in text


async def test_capture_with_note_overlay_open(base_state) -> None:
    """Screen capture with note overlay contains overlay content."""
    app = _make_app(base_state)
    async with app.run_test(size=(80, 24)) as pilot:
        # Open note overlay by pressing enter
        await pilot.press("enter")
        text = app._capture_screen_as_text()
        # NoteOverlay should show the prompt
        assert "Enter note" in text or "note" in text.lower()


async def test_capture_with_quit_overlay_open(base_state) -> None:
    """Screen capture with quit overlay contains quit prompt text."""
    app = _make_app(base_state)
    async with app.run_test(size=(80, 24)) as pilot:
        # Open quit overlay by pressing q
        await pilot.press("q")
        text = app._capture_screen_as_text()
        # PromptOverlay for quit should show confirmation
        assert "Quit" in text or "quit" in text.lower() or "Exit" in text


async def test_capture_lines_fit_width(base_state) -> None:
    """Every line in captured text fits within the terminal width."""
    width = 80
    app = _make_app(base_state)
    async with app.run_test(size=(width, 24)):
        text = app._capture_screen_as_text()
        for line in text.splitlines():
            assert len(line) <= width, f"Line exceeds width {width}: {line!r} (len={len(line)})"
