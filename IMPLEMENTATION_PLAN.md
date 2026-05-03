# Implementation Plan: Sort Toggle

## Feature Overview

A keyboard shortcut `s` toggles the file tree between two sort orders:

- **Alpha** (default): entries sorted by name, case-insensitive.
- **Size**: entries sorted by size descending; unscanned entries (size is `None`) sorted last.

Only two modes exist. Pressing `s` cycles between them. The sort order applies to
both the `FileTreePanel` and the `SizePanel` (rows stay aligned).

---

## Phase 1: SortMode model, AppState field, toggle_sort function

**Files modified:**
- `danalyze/models.py` — add `SortMode(StrEnum)` with values `ALPHA` and `SIZE`
- `danalyze/state.py` — add `sort_mode: SortMode = SortMode.ALPHA` to `AppState`;
  add `toggle_sort(state: AppState) -> AppState` pure function;
  add `sorted_children(state: AppState) -> list[FileNode]` pure helper that returns
  `view_root.children` (or `[]`) in the order dictated by `state.sort_mode`
- `tests/conftest.py` — pass `sort_mode=SortMode.ALPHA` in the `base_state` factory
- `tests/test_models.py` — verify `SortMode` string values
- `tests/test_state.py` — test `toggle_sort` and `sorted_children`

**Sort keys:**
- `ALPHA`: `key=lambda c: c.name.lower()`
- `SIZE`: `key=lambda c: (c.size is None, -(c.size or 0))` — sized entries first
  (largest first), then unsized entries

**Key tests:** `tests/test_state.py`
- `SortMode.ALPHA == "alpha"`, `SortMode.SIZE == "size"`
- `toggle_sort` on `ALPHA` state → new state with `sort_mode == SIZE`
- `toggle_sort` on `SIZE` state → new state with `sort_mode == ALPHA`
- `toggle_sort` returns a new `AppState` instance (does not mutate the original)
- `sorted_children` in `ALPHA` mode returns children sorted by name (case-insensitive)
- `sorted_children` in `SIZE` mode returns sized entries largest-first, then unsized
- `sorted_children` returns `[]` when `view_root.children` is `None`

**Mocks:** none

**Commit:** `Sort 1: SortMode model, AppState field, toggle_sort and sorted_children`

---

## Phase 2: TUI sort application and `s` key binding

**Files modified:**
- `danalyze/tui/widgets.py` — replace `state.view_root.children or []` in both
  `FileTreePanel._build()` and `SizePanel._build()` with `sorted_children(state)`;
  add `[s] sort` to the `StatusBar` hint string
- `danalyze/tui/app.py` — add `s` key handler that calls `toggle_sort` and refreshes
  all widgets
- `tests/test_tui.py` — add tests for the `s` key

**Key tests:** `tests/test_tui.py`
- Press `s`: `app._state.sort_mode` changes from `ALPHA` to `SIZE`
- Press `s` again: changes back to `ALPHA`
- In `ALPHA` mode, `FileTreePanel` renders entries in name order
- After pressing `r` then `s`, the entry with the largest size appears before
  smaller entries in the rendered text
- `SizePanel` row order matches `FileTreePanel` row order after toggling

**Mocks:** none — use real `DiskScanner` backed by `InMemoryFilesystem` for size-sort tests

**Commit:** `Sort 2: TUI sort application and s key binding`
