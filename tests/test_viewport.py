"""Tests for danalyze.viewport — pure scroll offset helpers."""

from __future__ import annotations

import pytest

from danalyze.viewport import clamp, position_at, tumble_down, tumble_up

# ---------------------------------------------------------------------------
# clamp
# ---------------------------------------------------------------------------


def test_clamp_within_range() -> None:
    assert clamp(5, 20, 10) == 5


def test_clamp_above_max() -> None:
    # max valid offset = 20 - 10 = 10
    assert clamp(15, 20, 10) == 10


def test_clamp_at_max() -> None:
    assert clamp(10, 20, 10) == 10


def test_clamp_below_zero() -> None:
    assert clamp(-3, 20, 10) == 0


def test_clamp_zero_panel_height() -> None:
    # panel_height=0 means unconstrained — always 0
    assert clamp(5, 20, 0) == 0


def test_clamp_list_fits_panel() -> None:
    # all 5 entries fit in a 10-row panel → no scroll possible
    assert clamp(5, 5, 10) == 0


def test_clamp_exact_fit() -> None:
    assert clamp(5, 10, 10) == 0


def test_clamp_empty_list() -> None:
    assert clamp(5, 0, 10) == 0


def test_clamp_one_row_panel() -> None:
    # panel_height=1, n=5 → max offset = 4
    assert clamp(3, 5, 1) == 3
    assert clamp(6, 5, 1) == 4


# ---------------------------------------------------------------------------
# tumble_down
# ---------------------------------------------------------------------------


def test_tumble_down_cursor_within_viewport() -> None:
    # cursor at 5, offset 0, height 10 → visible [0,9], no scroll
    assert tumble_down(0, 5, 20, 10) == 0


def test_tumble_down_cursor_at_bottom_edge() -> None:
    # cursor at 9 = offset(0) + height(10) - 1 → still visible
    assert tumble_down(0, 9, 20, 10) == 0


def test_tumble_down_cursor_just_past_bottom_edge() -> None:
    # cursor at 10 > 0+10-1=9 → advance by max(1, 10//3)=3 → offset=3
    assert tumble_down(0, 10, 20, 10) == 3


def test_tumble_down_advances_by_third_of_height() -> None:
    # height=12 → step = 12//3 = 4
    assert tumble_down(0, 12, 30, 12) == 4


def test_tumble_down_minimum_step_is_one() -> None:
    # height=1 → step = max(1, 0) = 1; cursor at 1 > 0+1-1=0 → offset=1
    assert tumble_down(0, 1, 30, 1) == 1


def test_tumble_down_clamps_at_list_end() -> None:
    # offset=8, cursor=18, n=20, height=10 → max offset=10
    # cursor 18 > 8+10-1=17 → advance by 3 → 11 → clamped to 10
    assert tumble_down(8, 18, 20, 10) == 10


def test_tumble_down_already_at_max_offset() -> None:
    # offset=10 already at max (n=20, h=10), cursor=19 (last) → still at 10
    assert tumble_down(10, 19, 20, 10) == 10


def test_tumble_down_stale_offset_clamped_before_check() -> None:
    # offset=15 is stale (max valid=10 for n=20,h=10) → clamped to 10 first
    # cursor=12 is within [10,19] → no tumble → return 10
    assert tumble_down(15, 12, 20, 10) == 10


def test_tumble_down_stale_offset_then_tumbles() -> None:
    # n=20 → max offset=10; offset=15 stale → clamped to 10
    # cursor=20 past [10,19] → advance by 3 → 13, re-clamped to 10
    assert tumble_down(15, 20, 20, 10) == 10


def test_tumble_down_panel_height_zero() -> None:
    assert tumble_down(0, 5, 20, 0) == 0


def test_tumble_down_list_fits_panel() -> None:
    # 5 entries, height 10 → always 0
    assert tumble_down(0, 4, 5, 10) == 0


def test_tumble_down_many_files_deleted() -> None:
    # offset=5 from before; n was 20 but now 6, height=10
    # 6 <= 10, all fit → offset=0
    assert tumble_down(5, 4, 6, 10) == 0


def test_tumble_down_many_files_added() -> None:
    # offset=0, n was 5 but now 50, height=10
    # cursor at 10 just past [0,9] → advance by 3
    assert tumble_down(0, 10, 50, 10) == 3


# ---------------------------------------------------------------------------
# tumble_up
# ---------------------------------------------------------------------------


def test_tumble_up_cursor_within_viewport() -> None:
    assert tumble_up(5, 7, 20, 10) == 5


def test_tumble_up_cursor_at_top_edge() -> None:
    # cursor at 5 == offset(5) → still visible (top edge is inclusive)
    assert tumble_up(5, 5, 20, 10) == 5


def test_tumble_up_cursor_just_above_top_edge() -> None:
    # cursor at 4 < offset(5) → retreat by max(1, 10//3)=3 → offset=2
    assert tumble_up(5, 4, 20, 10) == 2


def test_tumble_up_retreats_by_third_of_height() -> None:
    # height=12 → step=4; cursor=7, offset=12 → 12-4=8
    assert tumble_up(12, 7, 30, 12) == 8


def test_tumble_up_minimum_step_is_one() -> None:
    # height=1 → step=max(1,0)=1; cursor=2, offset=3 → 3-1=2
    assert tumble_up(3, 2, 30, 1) == 2


def test_tumble_up_clamps_at_zero() -> None:
    # cursor=0, offset=2, height=10 → 2-3=-1 → clamped to 0
    assert tumble_up(2, 0, 20, 10) == 0


def test_tumble_up_already_at_zero() -> None:
    assert tumble_up(0, 0, 20, 10) == 0


def test_tumble_up_stale_offset_clamped_before_check() -> None:
    # offset=15 stale (max=10 for n=20,h=10) → clamped to 10
    # cursor=12 >= 10 → no tumble → return 10
    assert tumble_up(15, 12, 20, 10) == 10


def test_tumble_up_stale_offset_then_tumbles() -> None:
    # offset=15 → clamped to 10; cursor=9 < 10 → retreat by 3 → 7
    assert tumble_up(15, 9, 20, 10) == 7


def test_tumble_up_panel_height_zero() -> None:
    assert tumble_up(5, 3, 20, 0) == 0


def test_tumble_up_list_fits_panel() -> None:
    # 5 entries, height 10 → always 0
    assert tumble_up(0, 0, 5, 10) == 0


def test_tumble_up_many_files_deleted() -> None:
    # offset=8; n was 20 but now 6, height=10 → 6<=10, all fit → offset=0
    assert tumble_up(8, 0, 6, 10) == 0


def test_tumble_up_many_files_added() -> None:
    # offset=0, n was 5 but now 50; cursor at 0 → no tumble needed
    assert tumble_up(0, 0, 50, 10) == 0


# ---------------------------------------------------------------------------
# position_at — centers the selected entry vertically
# ---------------------------------------------------------------------------


def test_position_at_middle_of_list() -> None:
    # selected_index=5, h=10 → offset = clamp(5 - 5, 20, 10) = clamp(0, 20, 10) = 0
    assert position_at(5, 20, 10) == 0


def test_position_at_well_into_list() -> None:
    # selected_index=15, h=10 → offset = clamp(15 - 5, 20, 10) = clamp(10, 20, 10) = 10
    assert position_at(15, 20, 10) == 10


def test_position_at_near_end_clamped() -> None:
    # selected_index=18, h=10 → clamp(18-5, 20, 10) = clamp(13, 20, 10) = 10
    assert position_at(18, 20, 10) == 10


def test_position_at_near_start_clamped_to_zero() -> None:
    # selected_index=2, h=10 → clamp(2-5, 20, 10) = clamp(-3, 20, 10) = 0
    assert position_at(2, 20, 10) == 0


def test_position_at_zero() -> None:
    # selected_index=0 → clamp(-5, 20, 10) = 0
    assert position_at(0, 20, 10) == 0


def test_position_at_list_fits_panel() -> None:
    # all 8 entries fit in 10 rows → always 0 regardless of index
    assert position_at(6, 8, 10) == 0


def test_position_at_panel_height_zero() -> None:
    assert position_at(5, 20, 0) == 0


def test_position_at_entry_deleted_fallback_to_zero() -> None:
    # navigate_out falls back to selected_index=0 when dir was removed
    assert position_at(0, 20, 10) == 0


def test_position_at_fewer_entries_than_panel() -> None:
    # parent now has only 3 entries after deletions
    assert position_at(2, 3, 10) == 0


# ---------------------------------------------------------------------------
# Scroll increment parametrization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "panel_height,expected_step",
    [
        (1, 1),  # max(1, 0)
        (2, 1),  # max(1, 0)
        (3, 1),  # max(1, 1)
        (6, 2),  # 6//3
        (9, 3),  # 9//3
        (10, 3),  # 10//3
        (12, 4),  # 12//3
        (30, 10),  # 30//3
    ],
)
def test_tumble_down_step_size(panel_height: int, expected_step: int) -> None:
    # cursor one past the bottom edge with plenty of list remaining
    n = panel_height * 3
    cursor = panel_height  # just past visible [0, panel_height-1]
    result = tumble_down(0, cursor, n, panel_height)
    assert result == expected_step


@pytest.mark.parametrize(
    "panel_height,expected_step",
    [
        (1, 1),
        (2, 1),
        (3, 1),
        (6, 2),
        (9, 3),
        (10, 3),
        (12, 4),
        (30, 10),
    ],
)
def test_tumble_up_step_size(panel_height: int, expected_step: int) -> None:
    # cursor one above the top edge; offset starts at expected_step so result lands at 0
    n = panel_height * 3
    offset = expected_step
    cursor = offset - 1  # just above visible [offset, offset+panel_height-1]
    result = tumble_up(offset, cursor, n, panel_height)
    assert result == 0
