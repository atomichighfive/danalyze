"""DiskAnalyzerApp: root Textual application."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.message import Message

from danalyze.exceptions import ExportError
from danalyze.export import build_export_df, write_export
from danalyze.logging_config import begin_async_process, get_logger, set_async_process_id
from danalyze.models import AppMode, FileNode, ScanStatus
from danalyze.scanner import DiskScanner
from danalyze.state import (
    AppState,
    append_input,
    backspace_input,
    begin_note,
    begin_quit,
    begin_save,
    cancel_input,
    navigate_down,
    navigate_into,
    navigate_out,
    navigate_up,
    selected_node,
    submit_note,
)
from danalyze.tui.widgets import (
    FileTreePanel,
    InfoBar,
    NoteOverlay,
    PromptOverlay,
    SizePanel,
    StatusBar,
)

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
        self._overlay: NoteOverlay | PromptOverlay | None = None

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
    # Key routing
    # ------------------------------------------------------------------

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        """Block navigation/scan bindings when an overlay is open.

        Args:
            action: Name of the action being checked.
            parameters: Tuple of action parameters (unused).

        Returns:
            False to block the action when not in BROWSE mode; True otherwise.
        """
        if self._state.mode != AppMode.BROWSE and action in (
            "nav_up",
            "nav_down",
            "nav_right",
            "nav_left",
            "scan",
        ):
            return False
        return True

    async def on_key(self, event: events.Key) -> None:
        """Handle overlay input and BROWSE-mode shortcut keys.

        Arrow keys and r are handled via BINDINGS. This handler manages
        overlay text input, overlay dismissal, and the q/w/enter shortcuts.

        Args:
            event: The key event from Textual.

        Side effects:
            May open or dismiss overlays, update pending_input, save notes,
            write CSV exports, or exit the app.
        """
        key = event.key
        char = event.character
        mode = self._state.mode

        if mode == AppMode.BROWSE:
            if key == "enter":
                self._open_note_overlay()
            elif key == "q":
                self._open_quit_overlay()
            elif key == "w":
                self._open_save_overlay()

        elif mode == AppMode.NOTE_INPUT:
            if key == "escape":
                self._close_overlay()
            elif key == "enter":
                self._submit_note()
            elif key == "backspace":
                self._state = backspace_input(self._state)
                self._refresh_overlay()
            elif char is not None:
                self._state = append_input(self._state, char)
                self._refresh_overlay()

        elif mode == AppMode.QUIT_PROMPT:
            if char in ("y", "Y"):
                self.exit()
            elif char in ("n", "N") or key == "escape":
                self._close_overlay()

        elif mode == AppMode.SAVE_PROMPT:
            if key == "escape":
                self._close_overlay()
            elif key == "enter":
                await self._submit_save()
            elif key == "backspace":
                self._state = backspace_input(self._state)
                self._refresh_overlay()
            elif char is not None:
                self._state = append_input(self._state, char)
                self._refresh_overlay()

    # ------------------------------------------------------------------
    # Actions (bound to arrow keys and r via BINDINGS)
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
    # Overlay management
    # ------------------------------------------------------------------

    def _open_note_overlay(self) -> None:
        """Open NoteOverlay pre-filled with any existing note for the selected entry.

        Side effects:
            Changes mode to NOTE_INPUT, sets pending_input to the existing note,
            mounts NoteOverlay.
        """
        node = selected_node(self._state)
        existing = self._state.notes.get(str(node.path), "")
        self._state = dataclasses.replace(begin_note(self._state), pending_input=existing)
        self._overlay = NoteOverlay(self._state)
        self.mount(self._overlay)

    def _open_quit_overlay(self) -> None:
        """Open a PromptOverlay asking the user to confirm quit.

        Side effects:
            Changes mode to QUIT_PROMPT, mounts PromptOverlay.
        """
        self._state = begin_quit(self._state)
        self._overlay = PromptOverlay(self._state, "Quit? [y/n]", show_input=False)
        self.mount(self._overlay)

    def _open_save_overlay(self) -> None:
        """Open a PromptOverlay for entering the export CSV filename.

        Side effects:
            Changes mode to SAVE_PROMPT, mounts PromptOverlay.
        """
        self._state = begin_save(self._state)
        self._overlay = PromptOverlay(self._state, "Save to")
        self.mount(self._overlay)

    def _close_overlay(self) -> None:
        """Dismiss the current overlay and return to BROWSE mode.

        Side effects:
            Removes the overlay widget, resets mode and pending_input,
            refreshes main widgets.
        """
        if self._overlay is not None:
            self._overlay.remove()
            self._overlay = None
        self._state = cancel_input(self._state)
        self._refresh_widgets()

    def _refresh_overlay(self) -> None:
        """Repaint the current overlay with the latest state.

        Side effects:
            Calls refresh_state on the overlay widget if one is mounted.
        """
        if self._overlay is not None:
            self._overlay.refresh_state(self._state)

    def _submit_note(self) -> None:
        """Save or delete the note for the selected entry and close the overlay.

        An empty pending_input removes the existing note.

        Side effects:
            Updates self._state.notes via submit_note, removes overlay widget,
            refreshes widgets.
        """
        self._state = submit_note(self._state, self._state.pending_input)
        if self._overlay is not None:
            self._overlay.remove()
            self._overlay = None
        self._refresh_widgets()

    async def _submit_save(self) -> None:
        """Write the export CSV to the filename in pending_input.

        On success, dismisses the overlay. If the file already exists or any
        other I/O error occurs, shows the error in the overlay and stays open.

        Side effects:
            May create a file on disk.
            May call overlay.set_error() to display an error message.
        """
        filename = self._state.pending_input.strip()
        if not filename:
            return
        file_path = Path(filename)
        raw = getattr(self._scanner, "_registry", None)
        nodes = {str(k): v for k, v in raw.items()} if isinstance(raw, dict) else {}
        df = build_export_df(self._state.notes, nodes)
        try:
            write_export(df, file_path)
            self._close_overlay()
        except ExportError as exc:
            if self._overlay is not None and isinstance(self._overlay, PromptOverlay):
                self._overlay.set_error(str(exc))

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
            Calls refresh_state() on every panel widget and the current overlay.
        """
        self.query_one(InfoBar).refresh_state(self._state)
        self.query_one(FileTreePanel).refresh_state(self._state)
        self.query_one(SizePanel).refresh_state(self._state)
        self.query_one(StatusBar).refresh_state(self._state)
