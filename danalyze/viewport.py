"""Pure viewport offset helpers for scroll management.

The scroll offset lives on the DiskAnalyzerApp instance, not in AppState.
These functions compute a new offset after navigation events and are also
used by tui/widgets.py to clamp defensively before rendering.

panel_height=0 is treated as unconstrained — all functions return 0 in that
case, which causes widgets to render all children (backward-compatible with
tests that call _build() without a panel height).
"""

from __future__ import annotations


def clamp(scroll_offset: int, n_children: int, panel_height: int) -> int:
    """Clamp scroll_offset to the valid range for the current list and panel.

    Args:
        scroll_offset: Current scroll offset.
        n_children: Total number of children in the list.
        panel_height: Number of visible rows in the panel. 0 means unconstrained.

    Returns:
        Clamped offset in [0, max(0, n_children - panel_height)].
        Returns 0 when panel_height is 0 or all entries fit within the panel.
    """
    if panel_height <= 0 or n_children <= panel_height:
        return 0
    return max(0, min(scroll_offset, n_children - panel_height))


def tumble_down(
    scroll_offset: int,
    selected_index: int,
    n_children: int,
    panel_height: int,
) -> int:
    """Advance the viewport if the cursor has moved below the visible window.

    Clamps the offset first to guard against stale values caused by list changes
    (files added or deleted) between navigation events. If the selected entry is
    still below the bottom edge after clamping, advances the offset by
    max(1, panel_height // 3) and re-clamps.

    Args:
        scroll_offset: Current scroll offset.
        selected_index: Index of the selected entry in the full sorted list.
        n_children: Total number of children in the list.
        panel_height: Number of visible rows in the panel. 0 means unconstrained.

    Returns:
        New scroll offset.
    """
    offset = clamp(scroll_offset, n_children, panel_height)
    if panel_height <= 0:
        return offset
    if selected_index > offset + panel_height - 1:
        offset += max(1, panel_height // 3)
    return clamp(offset, n_children, panel_height)


def tumble_up(
    scroll_offset: int,
    selected_index: int,
    n_children: int,
    panel_height: int,
) -> int:
    """Retreat the viewport if the cursor has moved above the visible window.

    Clamps the offset first to guard against stale values caused by list changes
    (files added or deleted) between navigation events. If the selected entry is
    above the top edge after clamping, retreats the offset by
    max(1, panel_height // 3), floored at 0.

    Args:
        scroll_offset: Current scroll offset.
        selected_index: Index of the selected entry in the full sorted list.
        n_children: Total number of children in the list.
        panel_height: Number of visible rows in the panel. 0 means unconstrained.

    Returns:
        New scroll offset.
    """
    offset = clamp(scroll_offset, n_children, panel_height)
    if panel_height <= 0:
        return offset
    if selected_index < offset:
        offset -= max(1, panel_height // 3)
    return max(0, offset)


def position_at(selected_index: int, n_children: int, panel_height: int) -> int:
    """Center an entry vertically in the viewport.

    Computes the scroll offset that places selected_index in the middle row,
    clamped so the viewport never scrolls past the last item or before the
    first. When near the start or end of the list the entry will be off-center
    (as close to center as the bounds allow).

    Called by tui/app.py after navigate_out so the directory just exited
    appears near the middle of the parent listing. n_children is read from the
    live sorted children list after the state mutation, reflecting any
    additions or deletions in the parent since the last visit.

    Args:
        selected_index: Index of the entry to center.
        n_children: Total number of children in the list.
        panel_height: Number of visible rows in the panel. 0 means unconstrained.

    Returns:
        Clamped scroll offset centering selected_index in the visible window.
    """
    return clamp(selected_index - panel_height // 2, n_children, panel_height)
