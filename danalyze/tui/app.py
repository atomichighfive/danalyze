"""DiskAnalyzerApp: root Textual application."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.message import Message

from danalyze.logging_config import begin_async_process, get_logger, set_async_process_id
from danalyze.models import FileNode, ScanStatus
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

log = get_logger(__name__)


class DiskAnalyzerApp(App):
    """Top-level Textual application for danalyze.

    Args:
        state: Initial application state.
        scanner: DiskScanner instance used for directory listing and size scanning.
    """

    class ScanProgress(Message):
        """Posted by the on_progress callback after each directory is scanned.

        Args:
            node: The directory node that was just scanned.
        """

        def __init__(self, node: FileNode) -> None:
            """Initialise with the scanned node.

            Args:
                node: The directory node that was just scanned.
            """
            super().__init__()
            self.node = node

    BINDINGS = [
        ("up", "nav_up", "Navigate up"),
        ("down", "nav_down", "Navigate down"),
        ("right", "nav_right", "Enter directory"),
        ("left", "nav_left", "Go back"),
        ("r", "scan", "Scan sizes"),
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

    def on_mount(self) -> None:
        """Wire the scanner's on_progress callback to post ScanProgress messages.

        Side effects:
            Assigns self._scanner._on_progress so progress events flow into
            the Textual message bus.
        """
        self._scanner._on_progress = lambda node: self.post_message(
            DiskAnalyzerApp.ScanProgress(node)
        )

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
    # Actions (bound to keys via BINDINGS)
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

    def action_scan(self) -> None:
        """Invalidate the current view root and spawn a scan worker.

        Side effects:
            Calls scanner.invalidate on the current view_root path.
            Spawns a Textual worker that calls scanner.scan_sizes.
            Logs the spawn event via begin_async_process.
        """
        self._scanner.invalidate(self._state.view_root.path)
        process_id = begin_async_process(log, "scan-sizes")
        self.run_worker(
            self._worker_scan(self._state.view_root, process_id),
            exclusive=True,
        )

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    def on_scan_progress(self, event: ScanProgress) -> None:
        """Refresh all widgets when a directory scan completes.

        Args:
            event: ScanProgress message containing the scanned node.

        Side effects:
            Calls _refresh_widgets.
        """
        self._refresh_widgets()

    # ------------------------------------------------------------------
    # Workers
    # ------------------------------------------------------------------

    async def _worker_scan(self, node: FileNode, process_id: str) -> None:
        """Background worker: scan sizes for node and all descendants.

        Args:
            node: Root of the subtree to scan.
            process_id: Async process ID from begin_async_process, used for logging.

        Side effects:
            Calls scanner.scan_sizes which updates FileNode scan_status/size/error.
            Posts ScanProgress messages via the on_progress callback.
            Does a final widget refresh after scan completes.
        """
        set_async_process_id(process_id)
        log.debug("app.worker.scan.start", "Scan worker started for %s", node.path)
        await self._scanner.scan_sizes(node)
        log.debug("app.worker.scan.done", "Scan worker done for %s", node.path)
        self._refresh_widgets()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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
