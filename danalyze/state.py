"""Pure application state machine: AppState dataclass and event-handler functions."""

from __future__ import annotations

from dataclasses import dataclass, replace

from danalyze.models import AppMode, DriveInfo, FileNode, FileTree, ScanStatus, SortMode


@dataclass
class AppState:
    """Complete UI state for one frame of the application.

    All fields are immutable by convention — use dataclasses.replace() to derive
    new states rather than mutating in place.

    Args:
        view_root: The directory currently displayed in the file tree panel.
        selected_index: Index of the highlighted row within view_root.children.
        notes: Mapping of absolute path string to note text.
        mode: Current interaction mode (browsing, typing a note, etc.).
        pending_input: Text accumulated while the user is typing.
        drive_info: Disk usage figures for the top info bar.
        tree: Full FileTree needed for upward navigation (navigate_out).
        sort_mode: Current sort order applied to the file tree panel.
    """

    view_root: FileNode
    selected_index: int
    notes: dict[str, str]
    mode: AppMode
    pending_input: str
    drive_info: DriveInfo
    tree: FileTree
    sort_mode: SortMode = SortMode.ALPHA


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def selected_node(state: AppState) -> FileNode:
    """Return the currently highlighted FileNode.

    Args:
        state: Current application state.

    Returns:
        The FileNode at sorted_children(state)[state.selected_index].
    """
    return sorted_children(state)[state.selected_index]


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


def navigate_down(state: AppState) -> AppState:
    """Move the selection one row down, clamping at the last child.

    Args:
        state: Current application state.

    Returns:
        New AppState with selected_index incremented (or unchanged at bottom).
    """
    children = state.view_root.children
    if not children:
        return state
    new_idx = min(state.selected_index + 1, len(children) - 1)
    return replace(state, selected_index=new_idx)


def navigate_up(state: AppState) -> AppState:
    """Move the selection one row up, clamping at zero.

    Args:
        state: Current application state.

    Returns:
        New AppState with selected_index decremented (or unchanged at top).
    """
    new_idx = max(state.selected_index - 1, 0)
    return replace(state, selected_index=new_idx)


def navigate_into(state: AppState) -> AppState:
    """Enter the selected directory (right-arrow action).

    No-op if the selected node is a file, an ERROR node, or has no children
    listed yet (scan_status == UNSCANNED, meaning children is None).

    Args:
        state: Current application state.

    Returns:
        New AppState with view_root set to the selected directory and
        selected_index reset to 0, or the original state unchanged.
    """
    node = selected_node(state)
    if not node.is_dir or node.scan_status == ScanStatus.ERROR or node.children is None:
        return state
    return replace(state, view_root=node, selected_index=0)


def navigate_out(state: AppState) -> AppState:
    """Step out to the parent directory (left-arrow action).

    No-op when view_root is already the tree root.

    Args:
        state: Current application state.

    Returns:
        New AppState with view_root set to the parent directory and
        selected_index set to the former view_root's index in the parent.
        Returns the same state object unchanged when already at the root.
    """
    ancestors = state.tree.ancestors(state.view_root)
    if not ancestors:
        return state
    parent = ancestors[-1]
    if parent.children is None:
        return state
    parent_state = replace(state, view_root=parent)
    idx = next(
        (i for i, child in enumerate(sorted_children(parent_state)) if child is state.view_root),
        0,
    )
    return replace(state, view_root=parent, selected_index=idx)


# ---------------------------------------------------------------------------
# Note input
# ---------------------------------------------------------------------------


def begin_note(state: AppState) -> AppState:
    """Enter note-input mode for the selected entry.

    Args:
        state: Current application state.

    Returns:
        New AppState with mode set to NOTE_INPUT.
    """
    return replace(state, mode=AppMode.NOTE_INPUT)


def submit_note(state: AppState, text: str) -> AppState:
    """Save or remove a note for the selected entry.

    An empty text string removes any existing note. Saves the note keyed by
    the selected node's absolute path string.

    Args:
        state: Current application state.
        text: Note text to save. Empty string removes the note.

    Returns:
        New AppState with the note dict updated, mode set to BROWSE, and
        pending_input cleared.
    """
    path_key = str(selected_node(state).path)
    notes = dict(state.notes)
    if text:
        notes[path_key] = text
    else:
        notes.pop(path_key, None)
    return replace(state, notes=notes, mode=AppMode.BROWSE, pending_input="")


def cancel_input(state: AppState) -> AppState:
    """Cancel the current input mode without saving, returning to BROWSE.

    Args:
        state: Current application state.

    Returns:
        New AppState with mode set to BROWSE and pending_input cleared.
    """
    return replace(state, mode=AppMode.BROWSE, pending_input="")


# ---------------------------------------------------------------------------
# Prompt modes
# ---------------------------------------------------------------------------


def begin_quit(state: AppState) -> AppState:
    """Enter quit-confirmation prompt mode.

    Args:
        state: Current application state.

    Returns:
        New AppState with mode set to QUIT_PROMPT.
    """
    return replace(state, mode=AppMode.QUIT_PROMPT)


def begin_save(state: AppState) -> AppState:
    """Enter save-filename prompt mode.

    Args:
        state: Current application state.

    Returns:
        New AppState with mode set to SAVE_PROMPT.
    """
    return replace(state, mode=AppMode.SAVE_PROMPT)


# ---------------------------------------------------------------------------
# Text input helpers
# ---------------------------------------------------------------------------


def append_input(state: AppState, char: str) -> AppState:
    """Append a character to the pending input buffer.

    Args:
        state: Current application state.
        char: Single character to append.

    Returns:
        New AppState with the character appended to pending_input.
    """
    return replace(state, pending_input=state.pending_input + char)


def backspace_input(state: AppState) -> AppState:
    """Remove the last character from the pending input buffer.

    No-op if pending_input is already empty.

    Args:
        state: Current application state.

    Returns:
        New AppState with the last character removed from pending_input.
    """
    return replace(state, pending_input=state.pending_input[:-1])


# ---------------------------------------------------------------------------
# Sort
# ---------------------------------------------------------------------------


def toggle_sort(state: AppState) -> AppState:
    """Cycle the sort mode between ALPHA and SIZE.

    Args:
        state: Current application state.

    Returns:
        New AppState with sort_mode toggled between SortMode.ALPHA and SortMode.SIZE.
    """
    new_mode = SortMode.SIZE if state.sort_mode == SortMode.ALPHA else SortMode.ALPHA
    return replace(state, sort_mode=new_mode)


def sorted_children(state: AppState) -> list[FileNode]:
    """Return view_root.children in the order dictated by state.sort_mode.

    Args:
        state: Current application state.

    Returns:
        Sorted list of FileNode children. In ALPHA mode, sorted by name
        case-insensitively. In SIZE mode, sorted by size descending with
        unscanned entries (size is None) placed last.
        Returns an empty list when view_root.children is None.
    """
    children = state.view_root.children or []
    if state.sort_mode == SortMode.ALPHA:
        return sorted(children, key=lambda c: c.name.lower())
    return sorted(children, key=lambda c: (c.size is None, -(c.size or 0), c.name.lower()))
