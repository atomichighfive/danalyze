"""DiskAnalyzerApp: root Textual application."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal

from danalyze.models import ScanStatus
from danalyze.scanner import DiskScanner
from danalyze.state import (
    AppState,
    navigate_down,
    navigate_into,
    navigate_out,
    navigate_up,
    selected_node,
)
from danalyze.tui.widgets import FileTreePanel, InfoBar, SizePanel, StatusBar


class DiskAnalyzerApp(App):
    """Top-level Textual application for danalyze.

    Args:
        state: Initial application state.
        scanner: DiskScanner instance used for directory listing and size scanning.
    """

    BINDINGS = [
        ("up", "nav_up", "Navigate up"),
        ("down", "nav_down", "Navigate down"),
        ("right", "nav_right", "Enter directory"),
        ("left", "nav_left", "Go back"),
    ]

    CSS = """
    Screen {
        layout: vertical;
    }
    Horizontal {
        height: 1fr;
    }
    """

    def __init__(self, state: AppState, scanner: DiskScanner) -> None:
        """Initialise the app with an initial state and scanner.

        Args:
            state: Initial application state.
            scanner: DiskScanner for filesystem operations.
        """
        super().__init__()
        self._state = state
        self._scanner = scanner

    def compose(self) -> ComposeResult:
        """Build the widget tree.

        Returns:
            Iterator of widgets: InfoBar, Horizontal(FileTreePanel, SizePanel),
            StatusBar.

        Side effects:
            None — compose only creates widget instances.
        """
        yield InfoBar(self._state)
        with Horizontal():
            yield FileTreePanel(self._state)
            yield SizePanel(self._state)
        yield StatusBar(self._state)

    # ------------------------------------------------------------------
    # Actions (bound to arrow keys via BINDINGS)
    # ------------------------------------------------------------------

    def action_nav_up(self) -> None:
        """Move selection up one entry.

        Side effects:
            Updates self._state and refreshes all widgets.
        """
        self._state = navigate_up(self._state)
        self._refresh_widgets()

    def action_nav_down(self) -> None:
        """Move selection down one entry.

        Side effects:
            Updates self._state and refreshes all widgets.
        """
        self._state = navigate_down(self._state)
        self._refresh_widgets()

    async def action_nav_right(self) -> None:
        """Enter the selected directory.

        Side effects:
            May mutate the selected FileNode via list_directory.
            Updates self._state and refreshes all widgets.
        """
        await self._navigate_right()

    def action_nav_left(self) -> None:
        """Go back to the parent directory.

        Side effects:
            Updates self._state and refreshes all widgets.
        """
        self._state = navigate_out(self._state)
        self._refresh_widgets()

    async def _navigate_right(self) -> None:
        """List directory then navigate into it.

        Calls scanner.list_directory on the selected dir (skips ERROR nodes),
        then applies navigate_into to update the view root.

        Side effects:
            May mutate the selected FileNode via list_directory.
            Updates self._state and refreshes all widgets.
        """
        node = selected_node(self._state)
        if node.is_dir and node.scan_status != ScanStatus.ERROR:
            await self._scanner.list_directory(node)
        self._state = navigate_into(self._state)
        self._refresh_widgets()

    def _refresh_widgets(self) -> None:
        """Push the current state to all widgets.

        Side effects:
            Calls refresh_state() on every panel widget.
        """
        self.query_one(InfoBar).refresh_state(self._state)
        self.query_one(FileTreePanel).refresh_state(self._state)
        self.query_one(SizePanel).refresh_state(self._state)
        self.query_one(StatusBar).refresh_state(self._state)
