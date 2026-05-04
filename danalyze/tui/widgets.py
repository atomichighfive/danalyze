"""Textual widgets for danalyze: InfoBar, FileTreePanel, SizePanel, StatusBar."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from danalyze.formatter import format_size, render_bar
from danalyze.models import ScanStatus
from danalyze.state import AppState, sorted_children
from danalyze.viewport import clamp

_BAR_WIDTH = 12

_STATUS_HINT = (
    "[up/down] navigate  [right] enter dir  [left] back  [r] scan  [s] sort  "
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
        self._scroll_offset: int = 0
        self._panel_height: int = 0

    def on_mount(self) -> None:
        """Render initial content when mounted.

        Side effects:
            Calls update() with the rendered tree text.
        """
        self._render_state()

    def on_resize(self) -> None:
        """Re-render when the panel width changes so note truncation stays accurate.

        Uses the panel_height last set by refresh_state(); corrected on the next
        _refresh_widgets() call from the app.

        Side effects:
            Calls update() with re-rendered tree text using current width.
        """
        self._render_state()

    @staticmethod
    def _build(
        state: AppState,
        width: int = 40,
        scroll_offset: int = 0,
        panel_height: int = 0,
    ) -> Text:
        """Render the visible slice of the file tree as a Rich Text object.

        Args:
            state: Application state to render from.
            width: Panel width in characters; used to truncate long notes.
            scroll_offset: First visible row index into the sorted children list.
            panel_height: Number of rows to render. 0 means render all children.

        Returns:
            Rich Text with one entry per line for the visible slice; the selected
            row is highlighted with reverse video.
        """
        result = Text()
        all_children = sorted_children(state)
        n = len(all_children)
        offset = clamp(scroll_offset, n, panel_height)
        visible = all_children[offset : offset + panel_height] if panel_height > 0 else all_children
        for i, child in enumerate(visible):
            abs_idx = offset + i
            is_error = child.scan_status == ScanStatus.ERROR
            if is_error:
                prefix = "!"
            elif child.is_symlink:
                prefix = "@"
            elif child.is_dir:
                prefix = ">"
            else:
                prefix = " "

            name = child.name + ("/" if child.is_dir else "")
            has_note = str(child.path) in state.notes

            if has_note:
                raw = state.notes[str(child.path)]
                # Space available for the quoted note after "X name/  " and a 2-char margin.
                available = width - len(name) - 6
                full = f'"{raw}"'
                if available >= len(full):
                    tag = f"  {full}"
                elif available >= 5:
                    tag = f'  "{raw[:available - 5]}..."'
                else:
                    tag = ""
            elif is_error:
                tag = "  [error]"
            else:
                tag = ""

            line = f"{prefix} {name}{tag}"
            if i > 0:
                result.append("\n")
            style = "reverse" if abs_idx == state.selected_index else ""
            result.append(line, style=style)
        return result

    def _render_state(self) -> None:
        self.update(
            self._build(self._state, self.size.width or 40, self._scroll_offset, self._panel_height)
        )

    def refresh_state(self, state: AppState, scroll_offset: int = 0, panel_height: int = 0) -> None:
        """Update the widget with a new AppState, scroll offset, and panel height.

        Args:
            state: New application state.
            scroll_offset: First visible row index; forwarded to _build().
            panel_height: Number of rows to render; forwarded to _build().

        Side effects:
            Calls update() to repaint the widget.
        """
        self._state = state
        self._scroll_offset = scroll_offset
        self._panel_height = panel_height
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
        self._scroll_offset: int = 0
        self._panel_height: int = 0

    def on_mount(self) -> None:
        """Render initial content when mounted.

        Side effects:
            Calls update() with the rendered size text.
        """
        self._render_state()

    def on_resize(self) -> None:
        """Re-render when the panel height changes so the visible slice stays accurate.

        Uses the panel_height last set by refresh_state(); corrected on the next
        _refresh_widgets() call from the app.

        Side effects:
            Calls update() with re-rendered size text.
        """
        self._render_state()

    @staticmethod
    def _build(state: AppState, scroll_offset: int = 0, panel_height: int = 0) -> Text:
        """Render the visible slice of per-entry sizes as a Rich Text object.

        max_size is computed from the full children list (not just the visible
        slice) so bar proportions stay stable while scrolling.

        Args:
            state: Application state to render from.
            scroll_offset: First visible row index into the sorted children list.
            panel_height: Number of rows to render. 0 means render all children.

        Returns:
            Rich Text with one size entry per line for the visible slice; the
            selected row is highlighted with reverse video.
        """
        all_children = sorted_children(state)
        n = len(all_children)
        done_sizes = [
            c.size for c in all_children if c.scan_status == ScanStatus.DONE and c.size is not None
        ]
        max_size = max(done_sizes, default=0) or 1

        offset = clamp(scroll_offset, n, panel_height)
        visible = all_children[offset : offset + panel_height] if panel_height > 0 else all_children

        result = Text()
        for i, child in enumerate(visible):
            abs_idx = offset + i
            if i > 0:
                result.append("\n")
            sel_style = "reverse" if abs_idx == state.selected_index else ""

            if child.scan_status == ScanStatus.ERROR:
                result.append(child.error or "error", style=sel_style)
            elif child.scan_status == ScanStatus.DONE and child.size is not None:
                result.append(format_size(child.size).rjust(8) + "  ", style=sel_style)
                result.append(render_bar(child.size / max_size, _BAR_WIDTH))
            else:
                result.append("---", style=sel_style)

        return result

    def _render_state(self) -> None:
        self.update(self._build(self._state, self._scroll_offset, self._panel_height))

    def refresh_state(self, state: AppState, scroll_offset: int = 0, panel_height: int = 0) -> None:
        """Update the widget with a new AppState, scroll offset, and panel height.

        Args:
            state: New application state.
            scroll_offset: First visible row index; forwarded to _build().
            panel_height: Number of rows to render; forwarded to _build().

        Side effects:
            Calls update() to repaint the widget.
        """
        self._state = state
        self._scroll_offset = scroll_offset
        self._panel_height = panel_height
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
