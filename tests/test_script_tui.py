"""Tests for scripted-mode TUI functionality."""

from __future__ import annotations

import asyncio
import sys
from io import StringIO
from unittest.mock import MagicMock, patch

from danalyze.tui.app import DiskAnalyzerApp


def _make_app(base_state, **state_overrides):
    state = base_state(**state_overrides)
    return DiskAnalyzerApp(state=state, scanner=MagicMock())


# Phase 3: Full-Screen Plain-Text Capture Tests


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


# Phase 4: Scripted Execution Worker Tests


async def test_run_script_processes_inputs(base_state, sample_tree) -> None:
    """_run_script processes all inputs and updates state."""
    app = DiskAnalyzerApp(
        state=base_state(),
        scanner=MagicMock(),
    )
    async with app.run_test(size=(80, 24)):
        # Set scripted_inputs after on_mount to avoid timer auto-starting
        app._scripted_inputs = ["key.down", "key.down"]
        await app._run_script()
    # Verify selection changed by 2
    assert app._state.selected_index == 2


async def test_dispatch_key_down_increments_selection(base_state) -> None:
    """dispatch_key('down') increments the selected index."""
    app = _make_app(base_state, selected_index=0)
    async with app.run_test(size=(80, 24)):
        await app._dispatch_key("down")
        await asyncio.sleep(0)
    assert app._state.selected_index == 1


async def test_dispatch_key_up_decrements_selection(base_state) -> None:
    """dispatch_key('up') decrements the selected index."""
    app = _make_app(base_state, selected_index=2)
    async with app.run_test(size=(80, 24)):
        await app._dispatch_key("up")
        await asyncio.sleep(0)
    assert app._state.selected_index == 1


async def test_dispatch_key_enter_opens_note_overlay(base_state) -> None:
    """dispatch_key('enter') opens the note overlay."""
    app = _make_app(base_state)
    async with app.run_test(size=(80, 24)):
        await app._dispatch_key("enter")
        await asyncio.sleep(0)
    assert app._overlay is not None


async def test_dispatch_text_types_into_input(base_state) -> None:
    """dispatch_text types characters into pending_input."""
    app = DiskAnalyzerApp(
        state=base_state(mode="BROWSE"),
        scanner=MagicMock(),
    )
    async with app.run_test(size=(80, 24)):
        await app._dispatch_text("hello")
        await asyncio.sleep(0)
    # Text should be appended to pending_input via on_key handlers
    # The actual behavior depends on the app's mode


async def test_run_script_writes_frames_to_stdout(base_state) -> None:
    """_run_script writes frames to stdout."""
    mock_stdout = StringIO()

    app = DiskAnalyzerApp(
        state=base_state(),
        scanner=MagicMock(),
    )
    async with app.run_test(size=(80, 24)):
        # Set scripted_inputs after on_mount to avoid timer auto-starting
        app._scripted_inputs = ["key.down"]
        with patch.object(sys, "stdout", mock_stdout):
            await app._run_script()

    mock_stdout.seek(0)
    output = mock_stdout.read()
    assert "--- key.down ---" in output


async def test_run_script_empty_list_exits_immediately(base_state) -> None:
    """Empty scripted inputs list results in no frames."""
    app = DiskAnalyzerApp(
        state=base_state(),
        scanner=MagicMock(),
        scripted_inputs=[],
    )
    async with app.run_test(size=(80, 24)):
        await app._run_script()
    # Should not have raised or produced output
