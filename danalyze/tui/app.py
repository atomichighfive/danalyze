"""DiskAnalyzerApp: root Textual application."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal

from danalyze.scanner import DiskScanner
from danalyze.state import AppState
from danalyze.tui.widgets import FileTreePanel, InfoBar, SizePanel, StatusBar


class DiskAnalyzerApp(App):
    """Top-level Textual application for danalyze.

    Composes InfoBar, FileTreePanel, SizePanel, and StatusBar.
    Key bindings and scanner integration are added in later phases.

    Args:
        state: Initial application state.
        scanner: DiskScanner instance used for directory listing and size scanning.
    """

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
