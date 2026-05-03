"""Textual widgets for danalyze: InfoBar, FileTreePanel, SizePanel, StatusBar."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from danalyze.formatter import format_bar_line, format_size
from danalyze.models import ScanStatus
from danalyze.state import AppState

_BAR_WIDTH = 12

_STATUS_HINT = (
    "[up/down] navigate  [right] enter dir  [left] back  [r] scan  "
    "[enter] note  [q] quit  [w] write"
)


class InfoBar(Static):
    """Top bar displaying device name and disk usage figures.

    Args:
        state: Current application state.
    """

    DEFAULT_CSS = "InfoBar { height: 1; dock: top; }"

    def __init__(self, state: AppState) -> None:
        """Initialise the info bar.

        Args:
            state: Current application state.
        """
        super().__init__(markup=False)
        self._state = state

    def on_mount(self) -> None:
        """Render the initial content when the widget is mounted.

        Side effects:
            Calls update() to populate the widget text.
        """
        self._render_state()

    def _render_state(self) -> None:
        """Recompute and push the display string.

        Side effects:
            Calls self.update() with the formatted drive info string.
        """
        di = self._state.drive_info
        text = (
            f"{di.device}"
            f"  Total: {format_size(di.total)}"
            f"  Used: {format_size(di.used)}"
            f"  Free: {format_size(di.free)}"
        )
        self.update(text)

    def refresh_state(self, state: AppState) -> None:
        """Update the widget with a new AppState.

        Args:
            state: New application state.

        Side effects:
            Calls update() to repaint the widget.
        """
        self._state = state
        self._render_state()


class FileTreePanel(Static):
    """Scrollable list of FileNode entries for the current directory.

    Dirs are prefixed with ">", ERROR nodes with "!".
    Entries with notes are suffixed with "[note]".
    ERROR entries are suffixed with "[error]".

    Args:
        state: Current application state.
    """

    DEFAULT_CSS = "FileTreePanel { width: 2fr; overflow-y: auto; }"

    def __init__(self, state: AppState) -> None:
        """Initialise the file tree panel.

        Args:
            state: Current application state.
        """
        super().__init__(markup=False)
        self._state = state

    def on_mount(self) -> None:
        """Render initial content when mounted.

        Side effects:
            Calls update() with the rendered tree text.
        """
        self._render_state()

    @staticmethod
    def _build(state: AppState) -> Text:
        """Render the file tree as a Rich Text object with selection highlight.

        Args:
            state: Application state to render from.

        Returns:
            Rich Text with one entry per line; the selected row is highlighted
            with reverse video.
        """
        result = Text()
        children = state.view_root.children or []
        for i, child in enumerate(children):
            is_error = child.scan_status == ScanStatus.ERROR
            if is_error:
                prefix = "!"
            elif child.is_dir:
                prefix = ">"
            else:
                prefix = " "

            name = child.name + ("/" if child.is_dir else "")
            has_note = str(child.path) in state.notes
            tag = "  [note]" if has_note else ("  [error]" if is_error else "")
            line = f"{prefix} {name}{tag}"

            if i > 0:
                result.append("\n")
            style = "reverse" if i == state.selected_index else ""
            result.append(line, style=style)
        return result

    def _render_state(self) -> None:
        self.update(self._build(self._state))

    def refresh_state(self, state: AppState) -> None:
        """Update the widget with a new AppState.

        Args:
            state: New application state.

        Side effects:
            Calls update() to repaint the widget.
        """
        self._state = state
        self._render_state()


class SizePanel(Static):
    """Per-entry size strings and ASCII bar charts, aligned with FileTreePanel.

    DONE entries show formatted size + proportional bar.
    ERROR entries show the error message text.
    All other entries show "---".

    Args:
        state: Current application state.
    """

    DEFAULT_CSS = "SizePanel { width: 1fr; overflow-y: auto; }"

    def __init__(self, state: AppState) -> None:
        """Initialise the size panel.

        Args:
            state: Current application state.
        """
        super().__init__(markup=False)
        self._state = state

    def on_mount(self) -> None:
        """Render initial content when mounted.

        Side effects:
            Calls update() with the rendered size text.
        """
        self._render_state()

    @staticmethod
    def _build(state: AppState) -> str:
        """Render per-entry size information as a plain-text string.

        Args:
            state: Application state to render from.

        Returns:
            Multi-line string with one size entry per line, aligned with
            FileTreePanel row order.
        """
        children = state.view_root.children or []
        done_sizes = [
            c.size for c in children if c.scan_status == ScanStatus.DONE and c.size is not None
        ]
        max_size = max(done_sizes, default=0) or 1

        lines: list[str] = []
        for child in children:
            if child.scan_status == ScanStatus.ERROR:
                line = child.error or "error"
            elif child.scan_status == ScanStatus.DONE and child.size is not None:
                line = format_bar_line(child.size, max_size, _BAR_WIDTH)
            else:
                line = "---"
            lines.append(line)
        return "\n".join(lines)

    def _render_state(self) -> None:
        self.update(self._build(self._state))

    def refresh_state(self, state: AppState) -> None:
        """Update the widget with a new AppState.

        Args:
            state: New application state.

        Side effects:
            Calls update() to repaint the widget.
        """
        self._state = state
        self._render_state()


class StatusBar(Static):
    """Bottom bar showing context-sensitive key hints.

    Args:
        state: Current application state (reserved for future context-sensitivity).
    """

    DEFAULT_CSS = "StatusBar { height: 1; dock: bottom; }"

    def __init__(self, state: AppState) -> None:
        """Initialise the status bar.

        Args:
            state: Current application state.
        """
        super().__init__(_STATUS_HINT, markup=False)
        self._state = state

    def refresh_state(self, state: AppState) -> None:
        """Accept a state update (no-op in Phase 9 — hint text is static).

        Args:
            state: New application state.
        """
        self._state = state


class NoteOverlay(Static):
    """Bottom overlay for entering or editing a note on the selected entry.

    Displays the current pending_input from AppState with a trailing cursor.

    Args:
        state: Current application state (pending_input is used as initial text).
    """

    DEFAULT_CSS = "NoteOverlay { height: 3; dock: bottom; border: solid $accent; padding: 0 1; }"

    def __init__(self, state: AppState) -> None:
        """Initialise the note overlay.

        Args:
            state: Current application state.
        """
        super().__init__(markup=False)
        self._state = state

    def on_mount(self) -> None:
        """Render initial content when mounted.

        Side effects:
            Calls update() with the formatted note prompt.
        """
        self._render_state()

    def refresh_state(self, state: AppState) -> None:
        """Update the overlay with new state (e.g. after each keystroke).

        Args:
            state: New application state.

        Side effects:
            Calls update() to repaint the widget.
        """
        self._state = state
        self._render_state()

    def _render_state(self) -> None:
        self.update(f"Note: {self._state.pending_input}_")


class PromptOverlay(Static):
    """Bottom overlay for quit confirm or file-save prompts.

    When show_input is True, displays pending_input from AppState.
    When show_input is False (quit prompt), displays only the prompt text.
    An optional error line is shown below the prompt.

    Args:
        state: Current application state.
        prompt: Label text shown before the input field.
        show_input: If True, show pending_input and cursor. Default True.
    """

    DEFAULT_CSS = "PromptOverlay { height: 3; dock: bottom; border: solid $accent; padding: 0 1; }"

    def __init__(self, state: AppState, prompt: str, show_input: bool = True) -> None:
        """Initialise the prompt overlay.

        Args:
            state: Current application state.
            prompt: Label shown to the user.
            show_input: Whether to display an editable input field.
        """
        super().__init__(markup=False)
        self._state = state
        self._prompt = prompt
        self._show_input = show_input
        self._error = ""

    def on_mount(self) -> None:
        """Render initial content when mounted.

        Side effects:
            Calls update() with the formatted prompt.
        """
        self._render_state()

    def set_error(self, error: str) -> None:
        """Display an error message below the prompt.

        Args:
            error: Error text to display.

        Side effects:
            Calls update() to repaint the widget.
        """
        self._error = error
        self._render_state()

    def refresh_state(self, state: AppState) -> None:
        """Update the overlay with new state (e.g. after each keystroke).

        Args:
            state: New application state.

        Side effects:
            Calls update() to repaint the widget.
        """
        self._state = state
        self._render_state()

    def _render_state(self) -> None:
        text = f"{self._prompt}: {self._state.pending_input}_" if self._show_input else self._prompt
        if self._error:
            text += f"\n{self._error}"
        self.update(text)
