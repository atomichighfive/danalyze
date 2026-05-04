# Implementation Plan

## Phase 16: Viewport scrolling [done]

**Commit message:** `Phase 16: Viewport scrolling — tumbling scroll with offset`

### Scope

New module `danalyze/viewport.py` with pure offset helpers. Scroll offset lives on the
`DiskAnalyzerApp` instance. Widgets render only the visible slice of children.

**Files created:** `danalyze/viewport.py`, `tests/test_viewport.py`
**Files modified:** `danalyze/tui/widgets.py`, `danalyze/tui/app.py`, `ARCHITECTURE.md`,
`IMPLEMENTATION_PLAN.md`

### Key design decisions

- `AppState` unchanged — no scroll field added.
- `state.py` navigation functions unchanged — no panel_height parameter.
- `self._scroll_offset: int = 0` on `DiskAnalyzerApp`.
- After navigate_out, offset is computed from the live (post-mutation) sorted children list
  so any additions/deletions in the parent since last visit are reflected.
- `panel_height=0` in `_build()` means unconstrained — show all children (backward-compatible
  with direct `_build()` calls in existing tests).

### viewport.py

```
clamp(scroll_offset, n_children, panel_height) -> int
tumble_down(scroll_offset, selected_index, n_children, panel_height) -> int
tumble_up(scroll_offset, selected_index, n_children, panel_height) -> int
position_at(selected_index, n_children, panel_height) -> int
```

### widgets.py changes

- `FileTreePanel.refresh_state(state, scroll_offset=0)`
- `FileTreePanel._build(state, width=40, scroll_offset=0, panel_height=0)`
- `SizePanel.refresh_state(state, scroll_offset=0)`
- `SizePanel._build(state, scroll_offset=0, panel_height=0)` — max_size from full list
- `SizePanel.on_resize()` added (matches FileTreePanel)

### app.py changes

- `self._scroll_offset: int = 0` in `__init__`
- `action_nav_down` → `tumble_down` after state mutation
- `action_nav_up` → `tumble_up` after state mutation
- `_navigate_right` → reset offset to 0 after navigate_into
- `action_nav_left` → `position_at` after navigate_out using live n
- `_refresh_widgets` → `clamp` before passing offset to widgets

### test_viewport.py test cases

clamp: basic, above max, below zero, panel_height=0, list fits panel, empty list.
tumble_down: within viewport, at bottom edge, just past edge, clamps at list end, stale
  offset clamped before tumble, panel_height=0, list fits panel, increment sizes.
tumble_up: within viewport, at top edge, just above edge, clamps at 0, stale offset,
  panel_height=0, list fits panel, increment sizes.
position_at: basic, clamped at end, all-fit, index=0, entry deleted (fallback to 0).
Edge cases: many files deleted (n shrinks), many files added (n grows), navigate-out
  fallback to index=0 when directory was removed from parent.
