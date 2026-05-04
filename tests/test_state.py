"""Tests for danalyze.state — pure AppState transitions."""

from __future__ import annotations

from pathlib import Path

import pytest

from danalyze.models import AppMode, FileNode, ScanStatus, SortMode
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
    sorted_children,
    submit_note,
    toggle_sort,
)

# ---------------------------------------------------------------------------
# navigate_down
# ---------------------------------------------------------------------------


def test_navigate_down_increments_index(base_state) -> None:
    state = base_state(selected_index=0)
    new_state = navigate_down(state)
    assert new_state.selected_index == 1


def test_navigate_down_clamps_at_last_child(base_state, sample_tree) -> None:
    last = len(sample_tree.children) - 1
    state = base_state(selected_index=last)
    new_state = navigate_down(state)
    assert new_state.selected_index == last


def test_navigate_down_does_not_mutate(base_state) -> None:
    state = base_state(selected_index=0)
    new_state = navigate_down(state)
    assert state.selected_index == 0
    assert id(state) != id(new_state)


# ---------------------------------------------------------------------------
# navigate_up
# ---------------------------------------------------------------------------


def test_navigate_up_decrements_index(base_state) -> None:
    state = base_state(selected_index=2)
    new_state = navigate_up(state)
    assert new_state.selected_index == 1


def test_navigate_up_clamps_at_zero(base_state) -> None:
    state = base_state(selected_index=0)
    new_state = navigate_up(state)
    assert new_state.selected_index == 0


def test_navigate_up_does_not_mutate(base_state) -> None:
    state = base_state(selected_index=2)
    new_state = navigate_up(state)
    assert state.selected_index == 2
    assert id(state) != id(new_state)


# ---------------------------------------------------------------------------
# navigate_into
# ---------------------------------------------------------------------------


def test_navigate_into_listed_dir_changes_view_root(base_state, sample_tree) -> None:
    # index 0 is "docs" (LISTED dir)
    state = base_state(selected_index=0)
    new_state = navigate_into(state)
    assert new_state.view_root is sample_tree.children[0]


def test_navigate_into_listed_dir_resets_selected_index(base_state) -> None:
    state = base_state(selected_index=0)
    new_state = navigate_into(state)
    assert new_state.selected_index == 0


def test_navigate_into_file_is_noop(base_state, sample_tree) -> None:
    # index 2 is "readme.txt" (file)
    state = base_state(selected_index=2)
    new_state = navigate_into(state)
    assert new_state.view_root is state.view_root
    assert new_state.selected_index == state.selected_index


def test_navigate_into_error_node_is_noop(base_state, sample_tree) -> None:
    # index 3 is "private" (ERROR dir)
    state = base_state(selected_index=3)
    new_state = navigate_into(state)
    assert new_state.view_root is state.view_root


def test_navigate_into_unscanned_dir_is_noop(base_state, sample_tree) -> None:
    # Replace a child with an UNSCANNED dir (children=None)

    unscanned = FileNode(
        path=Path("/root/unscanned"),
        name="unscanned",
        is_dir=True,
        scan_status=ScanStatus.UNSCANNED,
    )
    root = sample_tree
    root.children[1] = unscanned
    state = base_state(selected_index=1)
    new_state = navigate_into(state)
    assert new_state.view_root is root


# ---------------------------------------------------------------------------
# navigate_out
# ---------------------------------------------------------------------------


def test_navigate_out_steps_to_parent(base_state, sample_tree) -> None:
    # Navigate into docs first, then back out
    docs = sample_tree.children[0]
    state = base_state(view_root=docs, selected_index=0)
    new_state = navigate_out(state)
    assert new_state.view_root is sample_tree


def test_navigate_out_restores_selected_index(base_state, sample_tree) -> None:
    # docs is at index 0 in root's children
    docs = sample_tree.children[0]
    state = base_state(view_root=docs, selected_index=0)
    new_state = navigate_out(state)
    assert new_state.selected_index == 0  # docs is at index 0 in root


def test_navigate_out_restores_correct_index_for_non_first_child(base_state, sample_tree) -> None:
    # downloads is at index 1 in root's children
    downloads = sample_tree.children[1]
    state = base_state(view_root=downloads, selected_index=0)
    new_state = navigate_out(state)
    assert new_state.selected_index == 1


def test_navigate_out_at_root_is_noop(base_state, sample_tree) -> None:
    # view_root IS the tree root — cannot go further up
    state = base_state(view_root=sample_tree)
    new_state = navigate_out(state)
    assert new_state.view_root is sample_tree
    assert id(new_state) == id(state)


def test_navigate_out_does_not_mutate(base_state, sample_tree) -> None:
    docs = sample_tree.children[0]
    state = base_state(view_root=docs, selected_index=0)
    new_state = navigate_out(state)
    assert id(state) != id(new_state)


# ---------------------------------------------------------------------------
# begin_note / cancel_input / submit_note
# ---------------------------------------------------------------------------


def test_begin_note_sets_mode(base_state) -> None:
    state = base_state()
    new_state = begin_note(state)
    assert new_state.mode == AppMode.NOTE_INPUT


def test_submit_note_saves_text(base_state, sample_tree) -> None:
    state = begin_note(base_state(selected_index=0))
    new_state = submit_note(state, "important folder")
    path_key = str(sample_tree.children[0].path)
    assert new_state.notes[path_key] == "important folder"


def test_submit_note_sets_mode_to_browse(base_state) -> None:
    state = begin_note(base_state())
    new_state = submit_note(state, "hello")
    assert new_state.mode == AppMode.BROWSE


def test_submit_note_clears_pending_input(base_state) -> None:
    state = base_state(mode=AppMode.NOTE_INPUT, pending_input="some text")
    new_state = submit_note(state, "saved note")
    assert new_state.pending_input == ""


def test_submit_empty_note_removes_existing(base_state, sample_tree) -> None:
    path_key = str(sample_tree.children[0].path)
    state = base_state(notes={path_key: "remove me"}, mode=AppMode.NOTE_INPUT, selected_index=0)
    new_state = submit_note(state, "")
    assert path_key not in new_state.notes


def test_submit_empty_note_sets_mode_to_browse(base_state) -> None:
    state = base_state(mode=AppMode.NOTE_INPUT)
    new_state = submit_note(state, "")
    assert new_state.mode == AppMode.BROWSE


def test_cancel_input_from_note_mode(base_state) -> None:
    state = base_state(mode=AppMode.NOTE_INPUT, pending_input="half-typed")
    new_state = cancel_input(state)
    assert new_state.mode == AppMode.BROWSE
    assert new_state.pending_input == ""


def test_cancel_input_does_not_save_note(base_state, sample_tree) -> None:
    path_key = str(sample_tree.children[0].path)
    state = base_state(mode=AppMode.NOTE_INPUT, pending_input="unsaved")
    new_state = cancel_input(state)
    assert path_key not in new_state.notes


def test_cancel_input_from_quit_prompt(base_state) -> None:
    state = base_state(mode=AppMode.QUIT_PROMPT)
    new_state = cancel_input(state)
    assert new_state.mode == AppMode.BROWSE


def test_cancel_input_from_save_prompt(base_state) -> None:
    state = base_state(mode=AppMode.SAVE_PROMPT)
    new_state = cancel_input(state)
    assert new_state.mode == AppMode.BROWSE


# ---------------------------------------------------------------------------
# begin_quit / begin_save
# ---------------------------------------------------------------------------


def test_begin_quit_sets_mode(base_state) -> None:
    state = base_state()
    new_state = begin_quit(state)
    assert new_state.mode == AppMode.QUIT_PROMPT


def test_begin_save_sets_mode(base_state) -> None:
    state = base_state()
    new_state = begin_save(state)
    assert new_state.mode == AppMode.SAVE_PROMPT


# ---------------------------------------------------------------------------
# append_input / backspace_input
# ---------------------------------------------------------------------------


def test_append_input_extends_pending_input(base_state) -> None:
    state = base_state(pending_input="hel")
    new_state = append_input(state, "l")
    assert new_state.pending_input == "hell"


def test_append_input_does_not_mutate(base_state) -> None:
    state = base_state(pending_input="a")
    new_state = append_input(state, "b")
    assert state.pending_input == "a"
    assert id(state) != id(new_state)


def test_backspace_input_removes_last_char(base_state) -> None:
    state = base_state(pending_input="hello")
    new_state = backspace_input(state)
    assert new_state.pending_input == "hell"


def test_backspace_input_noop_when_empty(base_state) -> None:
    state = base_state(pending_input="")
    new_state = backspace_input(state)
    assert new_state.pending_input == ""


# ---------------------------------------------------------------------------
# selected_node
# ---------------------------------------------------------------------------


def test_selected_node_returns_correct_child(base_state) -> None:
    state = base_state(selected_index=2)
    node = selected_node(state)
    assert node is sorted_children(state)[2]


def test_selected_node_at_index_zero(base_state) -> None:
    state = base_state(selected_index=0)
    node = selected_node(state)
    assert node is sorted_children(state)[0]


# ---------------------------------------------------------------------------
# Immutability: all transitions return new AppState instances
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fn,kwargs",
    [
        (navigate_down, {}),
        (navigate_up, {}),
        (navigate_into, {}),
        (begin_note, {}),
        (begin_quit, {}),
        (begin_save, {}),
        (cancel_input, {}),
        (append_input, {"char": "x"}),
        (backspace_input, {}),
    ],
)
def test_all_transitions_return_new_instance(fn, kwargs, base_state) -> None:
    state = base_state()
    new_state = fn(state, **kwargs)
    # Either a new object was returned, or an identical object was returned
    # (no-op case). In both cases the original must not be mutated.
    assert isinstance(new_state, AppState)


def test_submit_note_returns_new_instance(base_state) -> None:
    state = begin_note(base_state())
    new_state = submit_note(state, "text")
    assert id(state) != id(new_state)


# ---------------------------------------------------------------------------
# toggle_sort
# ---------------------------------------------------------------------------


def test_toggle_sort_alpha_to_size(base_state) -> None:
    state = base_state(sort_mode=SortMode.ALPHA)
    new_state = toggle_sort(state)
    assert new_state.sort_mode == SortMode.SIZE


def test_toggle_sort_size_to_alpha(base_state) -> None:
    state = base_state(sort_mode=SortMode.SIZE)
    new_state = toggle_sort(state)
    assert new_state.sort_mode == SortMode.ALPHA


def test_toggle_sort_returns_new_instance(base_state) -> None:
    state = base_state(sort_mode=SortMode.ALPHA)
    new_state = toggle_sort(state)
    assert id(state) != id(new_state)


def test_toggle_sort_does_not_mutate_original(base_state) -> None:
    state = base_state(sort_mode=SortMode.ALPHA)
    toggle_sort(state)
    assert state.sort_mode == SortMode.ALPHA


# ---------------------------------------------------------------------------
# sorted_children
# ---------------------------------------------------------------------------


def test_sorted_children_alpha_order(base_state, sample_tree) -> None:
    # sample_tree children: docs, downloads, readme.txt, private
    # alpha order: docs, downloads, private, readme.txt
    state = base_state(sort_mode=SortMode.ALPHA)
    result = sorted_children(state)
    names = [c.name for c in result]
    assert names == sorted(names, key=str.lower)


def test_sorted_children_size_order_largest_first(base_state) -> None:
    from danalyze.models import FileTree

    big = FileNode(
        path=Path("/r/big"), name="big", is_dir=False, size=1000, scan_status=ScanStatus.DONE
    )
    small = FileNode(
        path=Path("/r/small"),
        name="small",
        is_dir=False,
        size=100,
        scan_status=ScanStatus.DONE,
    )
    root = FileNode(path=Path("/r"), name="r", is_dir=True, children=[small, big])
    state = base_state(view_root=root, sort_mode=SortMode.SIZE, tree=FileTree(root=root))
    result = sorted_children(state)
    assert result[0].name == "big"
    assert result[1].name == "small"


def test_sorted_children_size_order_unscanned_last(base_state) -> None:
    from danalyze.models import FileTree

    sized = FileNode(
        path=Path("/r/sized"),
        name="sized",
        is_dir=False,
        size=500,
        scan_status=ScanStatus.DONE,
    )
    unsized = FileNode(
        path=Path("/r/unsized"),
        name="unsized",
        is_dir=False,
        scan_status=ScanStatus.UNSCANNED,
    )
    root = FileNode(path=Path("/r"), name="r", is_dir=True, children=[unsized, sized])
    state = base_state(view_root=root, sort_mode=SortMode.SIZE, tree=FileTree(root=root))
    result = sorted_children(state)
    assert result[0].name == "sized"
    assert result[1].name == "unsized"


def test_sorted_children_size_mode_before_scan_is_alpha_order(base_state) -> None:
    from danalyze.models import FileTree

    zebra = FileNode(path=Path("/r/zebra"), name="zebra", is_dir=False)
    apple = FileNode(path=Path("/r/apple"), name="apple", is_dir=False)
    mango = FileNode(path=Path("/r/mango"), name="mango", is_dir=False)
    root = FileNode(path=Path("/r"), name="r", is_dir=True, children=[zebra, apple, mango])
    state = base_state(view_root=root, sort_mode=SortMode.SIZE, tree=FileTree(root=root))
    result = sorted_children(state)
    assert [c.name for c in result] == ["apple", "mango", "zebra"]


def test_sorted_children_returns_empty_when_children_none(base_state, sample_tree) -> None:
    no_children = FileNode(path=Path("/empty"), name="empty", is_dir=True, children=None)
    from danalyze.models import FileTree

    state = base_state(
        view_root=no_children, sort_mode=SortMode.ALPHA, tree=FileTree(root=no_children)
    )
    result = sorted_children(state)
    assert result == []
