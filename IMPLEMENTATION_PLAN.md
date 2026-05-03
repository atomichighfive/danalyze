# Implementation Plan: danalyze

## What We Are Building

`danalyze` is a terminal UI application for identifying what is taking up disk
space. It addresses the core challenge that disk usage can be dominated either by a
small number of large files or by a large number of small files — making a naive
size-sorted list insufficient.

### User experience
The app opens in a terminal and shows three regions:

- **Top bar (InfoBar):** device name, total size, used space, free space for the
  current drive.
- **Left panel (FileTreePanel):** the directory tree, navigable with arrow keys.
  Up/down selects an entry. Right arrow enters a directory (and lists its contents).
  Left arrow steps back out to the parent. Entries that failed to read (e.g. permission
  denied) are shown inline with a `!` marker and an error label — they do not crash
  the app.
- **Right panel (SizePanel):** human-readable size (B / KB / MB / GB / TB) and an
  ASCII bar chart showing each entry's share of its parent directory. Sizes show `---`
  until the user presses `r` to trigger scanning.

### Scanning model
The app starts immediately with no sizes computed. Navigation (right arrow) performs a
fast directory listing (`scandir`) to reveal children. Pressing `r` triggers a full
recursive size scan of the current directory. Results are cached; pressing `r` again
forces a fresh scan. Read errors during scanning are shown inline per-entry; the rest
of the tree continues scanning normally.

### Notes and export
Pressing `enter` on any entry opens a single-line note input. An empty submission
removes any existing note. Notes are shown with a `[note]` tag in the tree.

Pressing `w` prompts for a filename and writes a CSV file with columns:
`path, size_bytes, size_human, note`. The file is never overwritten — if the name
already exists the prompt shows an error and asks for a different name.

Pressing `q` opens a y/n quit confirmation. `escape` cancels any open prompt or note
input.

### Resuming work with `-o`
The app accepts `-o path/to/file.csv` to pre-load notes from a previous session's
export file. Paths from the CSV that are not found under the current `PATH` are still
retained and included in any subsequent export.

### Logging
`--debug` enables structured CSV logging to a file (never overwriting — counts up from
`danalyze.log` → `danalyze.1.log` etc.). Each log row contains:
`timestamp, async_process_id, module, log_line_name, message`. Async workers each get
a unique `async_process_id` so concurrent scan operations can be disentangled in the
log.

### Technical stack
- Python 3.11+
- [Textual](https://github.com/Textualize/textual) for the TUI
- [pandas](https://pandas.pydata.org/) for CSV export/import
- `uv` for dependency management
- `pytest` + `pytest-asyncio` for testing
- `ruff` for linting and formatting
- `pre-commit` for enforcing quality before every commit

---

## Phased Implementation

Each phase is a single git commit. Follow the workflow in CLAUDE.md exactly:
clarify → tests (red) → implement (green) → fix → pre-commit → commit.

Phases are topologically ordered by dependency. The full DAG:

```
exceptions, models, formatter, logging_config   <- no project deps
        |
filesystem, state, notes                        <- depend on level above
        |
scanner, export                                 <- depend on level above
        |
tui/widgets                                     <- depends on state, formatter
        |
tui/app [layout] -> [navigation] -> [overlays]  <- depends on everything
        |
__main__                                        <- entry point
```

---

## Phase 1: Project scaffold [done]

**Repository:** `git@github.com:atomichighfive/danalyze.git`
Clone the repo, then set up the project inside it.

**Files created:**
- `pyproject.toml`
- `.pre-commit-config.yaml`
- `.gitignore`
- `danalyze/__init__.py`
- `tests/__init__.py`
- `tests/conftest.py` (empty, populated in later phases)

**Setup steps (run these before writing any tests):**
```bash
uv init --no-workspace
uv add textual pandas
uv add --dev pytest pytest-asyncio pre-commit
uv run pre-commit install
```

**`pyproject.toml` must configure:**
- `[project]`: name = "danalyze", version = "0.1.0", requires-python = ">=3.11",
  dependencies = ["textual>=0.47", "pandas>=2.0"]
- `[project.optional-dependencies]`: dev = ["pytest>=8", "pytest-asyncio>=0.23", "pre-commit"]
- `[tool.pytest.ini_options]`: asyncio_mode = "auto"
- `[tool.ruff]`: line-length = 100, target-version = "py311"
- `[tool.ruff.lint]`: select = ["E", "F", "I", "UP", "B", "SIM"]

**`.pre-commit-config.yaml` must configure:**
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.4
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

**Mocks:** none

**Tests:** `tests/test_scaffold.py`
- `import danalyze` succeeds
- `danalyze.__version__ == "0.1.0"`

**Commit:** `Phase 1: Project scaffold and tooling`

---

## Phase 2: Exceptions & Models [done]

**Files created:**
- `danalyze/exceptions.py`
- `danalyze/models.py`

**`exceptions.py` exports:**
- `DiskAnalyzerError(Exception)` — base
- `ScanError(DiskAnalyzerError)`
- `ExportError(DiskAnalyzerError)`
- `NavigationError(DiskAnalyzerError)`

**`models.py` exports:**
- `ScanStatus(StrEnum)` — UNSCANNED, LISTED, SCANNING, DONE, ERROR
- `AppMode(StrEnum)` — BROWSE, NOTE_INPUT, QUIT_PROMPT, SAVE_PROMPT
- `FileNode` — dataclass: path: Path, name: str, is_dir: bool,
  size: int | None = None, children: list[FileNode] | None = None,
  scan_status: ScanStatus = ScanStatus.UNSCANNED, error: str | None = None
- `DriveInfo` — dataclass: device: str, total: int, used: int, free: int, mount_point: Path
- `FileTree` — dataclass wrapping root: FileNode, with methods:
  `find_by_path(path: Path) -> FileNode | None` and
  `ancestors(node: FileNode) -> list[FileNode]` (root first, node excluded)

**Mocks:** none

**Key tests:** `tests/test_models.py`
- `FileNode` default scan_status is UNSCANNED, size and children are None
- `FileNode` with `scan_status=ERROR` and `error="permission denied"` stores both correctly
- `FileTree.find_by_path` returns correct node from a hand-built two-level tree
- `FileTree.find_by_path` returns None for a path not in the tree
- `FileTree.ancestors` returns the path from root to the given node, excluding the node itself
- `DriveInfo.free + DriveInfo.used <= DriveInfo.total` holds for a valid instance
- All `ScanStatus` and `AppMode` values are lowercase strings

**Commit:** `Phase 2: Exceptions and domain models`

---

## Phase 3: Formatter [done]

**Files created:**
- `danalyze/formatter.py`

**Exports:**
- `format_size(size_bytes: int) -> str` — B, KB, MB, GB, TB (1024-based); 1 decimal
  place for KB and above; raises ValueError if negative
- `render_bar(fraction: float, width: int) -> str` — `█` for filled, `░` for empty;
  raises ValueError if fraction not in [0.0, 1.0] or width < 1
- `format_bar_line(size: int, total: int, bar_width: int) -> str` — combines the two;
  when total == 0 renders a fully empty bar

**Mocks:** none

**Key tests:** `tests/test_formatter.py`
- `format_size(0)` → `"0 B"`
- `format_size(1023)` → `"1023 B"`
- `format_size(1024)` → `"1.0 KB"`
- `format_size(1_048_576)` → `"1.0 MB"`
- `format_size(1_073_741_824)` → `"1.0 GB"`
- `format_size(1_099_511_627_776)` → `"1.0 TB"`
- `format_size(-1)` raises `ValueError`
- `render_bar(0.0, 10)` → `"░░░░░░░░░░"`
- `render_bar(1.0, 10)` → `"██████████"`
- `render_bar(0.5, 10)` → `"█████░░░░░"`
- `render_bar(1.1, 10)` raises `ValueError`
- `render_bar(-0.1, 10)` raises `ValueError`
- `render_bar(0.5, 0)` raises `ValueError`
- `format_bar_line(0, 0, 10)` returns a string ending with `"░░░░░░░░░░"` without error
- `format_bar_line(500, 1000, 10)` contains both a size string and a half-filled bar

**Commit:** `Phase 3: Size formatter and bar renderer`

---

## Phase 4: Logging infrastructure

**Files created:**
- `danalyze/logging_config.py`

**Exports:**
- `find_safe_path(base: Path) -> Path` — returns base if absent; else appends `.1`,
  `.2`, ... to the stem until a free name is found
- `StructuredLogger` — wraps `logging.Logger`; every method takes `name: str` as its
  first positional argument before `msg`; internally sets `log_line_name` on the record
- `get_logger(module_name: str) -> StructuredLogger`
- `AsyncProcessFilter(logging.Filter)` — injects `async_process_id` (from ContextVar)
  and `log_line_name` into every record
- `StructuredCsvFormatter(logging.Formatter)` — formats records as a single CSV row
  using stdlib `csv.writer` so quoting/escaping of newlines and commas is automatic;
  columns: timestamp (ISO 8601), async_process_id, module, log_line_name, message
- `setup_logging(*, debug: bool, log_file: Path | None = None) -> None` — in debug
  mode attaches a `FileHandler` with `StructuredCsvFormatter` writing to
  `find_safe_path(log_file or Path("danalyze.log"))`; writes the CSV header row
  once on file creation; in non-debug mode only a WARNING-level stderr handler is added
- `begin_async_process(parent_log: StructuredLogger, process_name: str) -> str` —
  generates ID as `"<process_name>-<8 hex chars>"`, emits a record on `parent_log`
  with `log_line_name="async.process.spawn"`, returns the ID
- `set_async_process_id(process_id: str) -> None` — sets the module-level `ContextVar`

**Mocks:** none

**Key tests:** `tests/test_logging_config.py`
- `find_safe_path(tmp_path / "x.log")` returns that path when it does not exist
- `find_safe_path` when base exists returns `base.stem + ".1" + suffix`
- `find_safe_path` when base and `.1` both exist returns `.2`
- `get_logger(__name__).debug("a.b.c", "hello")` emits a record with `log_line_name == "a.b.c"`
- `get_logger(__name__).debug("msg")` (no name) raises `TypeError`
- `get_logger(__name__).error("a.b", "oops", exc_info=True)` includes exception info
- After `set_async_process_id("proc-1")`, a log record has `async_process_id == "proc-1"`
- Default async_process_id (no set call) is `"main"`
- `begin_async_process(log, "scan")` returns a string starting with `"scan-"` and emits
  a record with `log_line_name == "async.process.spawn"`
- `StructuredCsvFormatter` output for a message containing `\n` and `,` is a single line
  parseable by `csv.reader` as exactly five fields
- `setup_logging(debug=True, log_file=tmp_path/"test.log")` creates the file with a
  CSV header as line 1 and at least one data row after emitting a log message

**Commit:** `Phase 4: Structured CSV logging with async process tracking`

---

## Phase 5: Filesystem abstraction

**Files created:**
- `danalyze/filesystem.py`

**Exports:**
- `FilesystemProtocol(Protocol)` — `scandir(path: Path) -> Iterator[os.DirEntry]`,
  `stat(path: Path) -> os.stat_result`, `disk_usage(path: Path) -> Any` (duck-typed
  to match `shutil.disk_usage` namedtuple: total, used, free), `is_mount(path: Path) -> bool`
- `RealFilesystem` — delegates to `os.scandir`, `os.stat`, `shutil.disk_usage`,
  `os.path.ismount`
- `InMemoryFilesystem` — dict-based fake (see below)

`InMemoryFilesystem` constructor accepts a nested dict `{path_str: {name: size_or_subdict}}`.
Directories are nested dicts; files are `int` byte sizes. Additional test-control methods:
- `update_file_size(path_str: str, new_size: int) -> None`
- `set_permission_denied(path_str: str) -> None` — `scandir` and `stat` on that path raise `PermissionError`
- `scandir_call_count: int` — total `scandir` calls made

**Mocks:** none

**Key tests:** `tests/test_filesystem.py`
- `scandir("/root")` on `InMemoryFilesystem({"/root": {"a.txt": 100}})` returns one entry
- That entry has `is_dir() == False` and `stat().st_size == 100`
- A nested dict entry has `is_dir() == True`
- `disk_usage` total equals the sum of all file sizes (recursively)
- `is_mount` returns True for the top-level path, False for a subdirectory
- `set_permission_denied` causes `scandir` to raise `PermissionError`
- `update_file_size` is reflected in the next `stat` call
- `scandir_call_count` increments on each call

**Commit:** `Phase 5: Filesystem protocol and InMemoryFilesystem`

---

## Phase 6: Application state machine

**Files created:**
- `danalyze/state.py`

**Files modified:**
- `tests/conftest.py` — add `sample_tree` and `base_state` fixtures

**Exports from `state.py`:**
```
AppState  dataclass: view_root, selected_index, notes, mode, pending_input, drive_info
navigate_down(state: AppState) -> AppState
navigate_up(state: AppState) -> AppState
navigate_into(state: AppState) -> AppState
navigate_out(state: AppState) -> AppState
begin_note(state: AppState) -> AppState
cancel_input(state: AppState) -> AppState
submit_note(state: AppState, text: str) -> AppState
begin_quit(state: AppState) -> AppState
begin_save(state: AppState) -> AppState
append_input(state: AppState, char: str) -> AppState
backspace_input(state: AppState) -> AppState
selected_node(state: AppState) -> FileNode
```

**`conftest.py` fixtures:**
- `sample_tree()` — returns a `FileNode` tree: root dir with 4 children: 2 LISTED dirs
  (one with 2 file children), 1 file, 1 ERROR dir. At least one child has a non-zero size.
- `base_state(**overrides)` — returns `AppState` using `sample_tree()` as `view_root`,
  `selected_index=0`, `mode=AppMode.BROWSE`, `notes={}`, `pending_input=""`, and a
  dummy `DriveInfo`. Accepts keyword overrides for any field.

**Mocks:** none (state.py has no I/O)

**Key tests:** `tests/test_state.py`
- `navigate_down` increments `selected_index`; clamps at last child (no wraparound)
- `navigate_up` decrements `selected_index`; clamps at 0 (no wraparound)
- `navigate_into` with a LISTED dir selected: `view_root` becomes that dir, `selected_index` resets to 0
- `navigate_into` with a file selected: state unchanged
- `navigate_into` with an ERROR node selected: state unchanged
- `navigate_out` steps `view_root` to parent, `selected_index` set to the previous
  `view_root`'s index within the parent's children
- `navigate_out` when `view_root` has no parent (it is the root): state unchanged
- `begin_note` sets `mode` to `NOTE_INPUT`
- `submit_note(state, "hello")` saves note keyed by `selected_node(state).path`,
  sets mode to `BROWSE`, clears `pending_input`
- `submit_note(state, "")` removes any existing note for the selected path, sets mode to `BROWSE`
- `cancel_input` from `NOTE_INPUT`: mode → `BROWSE`, `pending_input` cleared, note NOT saved
- `cancel_input` from `QUIT_PROMPT` and `SAVE_PROMPT`: mode → `BROWSE`
- `begin_quit` sets mode to `QUIT_PROMPT`
- `begin_save` sets mode to `SAVE_PROMPT`
- `append_input(state, "x")` appends `"x"` to `pending_input`
- `backspace_input` removes last character; no-op when `pending_input` is empty
- `selected_node` returns `view_root.children[selected_index]`
- All functions return **new** `AppState` instances; the original is unchanged
  (verify by checking `id(original) != id(result)`)

**Commit:** `Phase 6: Pure application state machine`

---

## Phase 7: Notes and export

**Files created:**
- `danalyze/notes.py`
- `danalyze/export.py`

**`notes.py` exports:**
- `NoteStore` — `__init__(notes: dict[str, str] | None = None)`;
  `set(path: Path, text: str) -> None` (removes entry if text is empty);
  `get(path: Path) -> str | None`;
  `all() -> dict[str, str]` (returns a copy)

**`export.py` exports:**
- `build_export_df(notes: dict[str, str], nodes: dict[str, FileNode]) -> pd.DataFrame`
  Columns: `path` (str), `size_bytes` (int or `pd.NA`), `size_human` (str), `note` (str).
  Includes a row for every path that either has a note or has `scan_status == DONE`.
  Nodes with `scan_status == DONE` supply `size_bytes`; others get `pd.NA` and `size_human=""`.
  Notes missing from `notes` dict get `note=""`.
- `write_export(df: pd.DataFrame, file_path: Path) -> None`
  Raises `ExportError` if `file_path` already exists.
  Raises `ExportError` on any I/O failure.
- `load_notes_from_csv(file_path: Path) -> dict[str, str]`
  Raises `ExportError` if file missing or unreadable.
  Raises `ExportError` if CSV lacks `path` or `note` columns.
  Returns only rows where `note` is a non-empty string.

**Mocks:** none

**Key tests:** `tests/test_notes.py`
- `set(path, "text")` followed by `get(path)` returns `"text"`
- `set(path, "")` followed by `get(path)` returns `None`
- `get` on unknown path returns `None`
- `all()` returns a copy: mutating the returned dict does not affect the store

**Key tests:** `tests/test_export.py`
- `build_export_df` with one DONE node with a note: row has correct `path`, `size_bytes`, `size_human`, `note`
- `build_export_df` with an ERROR node that has a note: row included, `size_bytes` is `pd.NA`
- `build_export_df` with a DONE node without a note: row included, `note == ""`
- `build_export_df` with an UNSCANNED node without a note: row excluded
- `write_export` creates a file; reading it back with `pd.read_csv` yields the expected DataFrame
- `write_export` raises `ExportError` if the file already exists
- `load_notes_from_csv` round-trip: write then load returns the same `{path: note}` dict (non-empty notes only)
- `load_notes_from_csv` with missing file raises `ExportError`
- `load_notes_from_csv` with CSV missing `"note"` column raises `ExportError`
- `load_notes_from_csv` skips rows where `note` is empty or NaN

**Commit:** `Phase 7: NoteStore and CSV export/import`

---

## Phase 8: Scanner

**Files created:**
- `danalyze/scanner.py`

**Exports:**
- `DiskScanner(fs: FilesystemProtocol, on_progress: Callable[[FileNode], None] | None = None)`
  - `async list_directory(node: FileNode) -> None`
  - `async scan_sizes(node: FileNode) -> None`
  - `invalidate(path: Path) -> None`

**Mocks:** none — all tests use `InMemoryFilesystem`

**Key tests:** `tests/test_scanner.py`
- `list_directory` on an UNSCANNED dir: children populated, status → LISTED, all child sizes None
- `list_directory` on a LISTED dir: no-op (`scandir_call_count` unchanged)
- `list_directory` on a dir with `set_permission_denied`: status → ERROR, `error` field set, no exception raised
- `scan_sizes` on a flat dir with two files: both file sizes correct, dir size = sum, status → DONE
- `scan_sizes` on nested dirs: parent size equals sum of all descendant file sizes
- `scan_sizes` on an already-DONE node: no-op (`scandir_call_count` unchanged)
- `scan_sizes` when one child dir has `set_permission_denied`: that child → ERROR, parent size = sum of others, parent → DONE
- `invalidate(path)` then `scan_sizes`: fresh scan reflects `update_file_size` change
- `on_progress` callback is called at least once per directory visited during `scan_sizes`
- `scan_sizes` on a LISTED node (children known, no sizes): computes sizes without re-running `scandir`
  (`scandir_call_count` after listing + scanning equals count after listing alone)

**Commit:** `Phase 8: Async directory scanner with caching and error isolation`

---

## Phase 9: TUI layout

**Files created:**
- `danalyze/tui/__init__.py`
- `danalyze/tui/widgets.py`
- `danalyze/tui/app.py` (compose only — no key bindings)

**Scope:** Static rendering from an initial `AppState`. No key handling, no scanner calls.

**`widgets.py` exports:**
- `InfoBar(Widget)` — renders `DriveInfo`: device, total, used, free
- `FileTreePanel(Widget)` — renders `view_root.children` as a scrollable list;
  selected row highlighted; dirs prefixed `">"`, ERROR nodes prefixed `"!"`;
  noted entries suffixed `"[note]"`, ERROR entries suffixed `"[error]"`
- `SizePanel(Widget)` — per-entry: size string + bar for DONE; `"---"` for unscanned;
  error message string for ERROR; aligned row-for-row with FileTreePanel
- `StatusBar(Widget)` — static hint line showing available keys

**`app.py` exports:**
- `DiskAnalyzerApp(App)` — constructor takes `state: AppState` and `scanner: DiskScanner`;
  `compose()` mounts `InfoBar`, `FileTreePanel` and `SizePanel` side-by-side, `StatusBar`

**Mocks:** `scanner` argument to `DiskAnalyzerApp` is a `unittest.mock.MagicMock()`
in all Phase 9 tests (scanner is never called in this phase).

**Key tests:** `tests/test_tui.py`
- App mounts without error (`async with app.run_test() as pilot: pass`)
- InfoBar rendered text contains the device name from `DriveInfo`
- FileTreePanel rendered text contains the names of `view_root.children`
- The ERROR child entry contains `"!"` and `"[error]"` in its rendered row
- The noted child entry contains `"[note]"` in its rendered row
- SizePanel row for the ERROR entry contains the `node.error` string
- SizePanel row for an UNSCANNED entry contains `"---"`
- SizePanel row for a DONE entry contains `"█"` or `"░"` (bar characters)

**Commit:** `Phase 9: TUI layout and static rendering`

---

## Phase 10: TUI navigation

**Files modified:**
- `danalyze/tui/app.py` — add key bindings: up, down, left, right

**Scope:** Arrow keys update `AppState` via pure state functions and trigger widget
refresh. Right arrow into a dir calls `scanner.list_directory` before navigating.

**Mocks:** `scanner.list_directory` is an `AsyncMock` that immediately sets
`node.scan_status = ScanStatus.LISTED` and `node.children = []` so navigation tests
do not depend on async scan timing. For the one test that verifies children appear
in the panel after navigating right, use a real `DiskScanner` backed by `InMemoryFilesystem`.

**Key tests:** `tests/test_tui.py`
- Press `"down"`: `selected_index` increments, new row is highlighted
- Press `"down"` at the last entry: no change
- Press `"up"`: `selected_index` decrements
- Press `"up"` at the first entry: no change
- Press `"right"` on a LISTED dir: `list_directory` called, `view_root` changes to that dir
- Press `"right"` on a file: `view_root` unchanged
- Press `"right"` on an ERROR node: `view_root` unchanged, `list_directory` not called
- Press `"left"` when not at root: `view_root` steps to parent
- Press `"left"` at root: `view_root` unchanged

**Commit:** `Phase 10: TUI arrow-key navigation`

---

## Phase 11: TUI scan integration

**Files modified:**
- `danalyze/tui/app.py` — add `r` key binding; wire `on_progress` callback to
  widget refresh; wire `begin_async_process` / `set_async_process_id` for logging

**Scope:** Pressing `r` invalidates the current `view_root` and spawns a Textual worker
that calls `scanner.scan_sizes`. The `on_progress` callback posts a message causing
widgets to re-render. ERROR nodes from permission-denied paths appear inline.

**Mocks:** none — use real `DiskScanner` backed by `InMemoryFilesystem`.

**Key tests:** `tests/test_tui.py`
- Press `"r"`: after the worker completes, SizePanel shows real sizes (not `"---"`)
- Press `"r"` on a tree with a `set_permission_denied` dir: that entry shows `"!"` and
  error text in the SizePanel
- Press `"r"` twice (with `update_file_size` called between): second press reflects
  the updated size (force-rescan, cache invalidated)
- Widget content updates after scan without a full app restart

**Commit:** `Phase 11: TUI scan integration with r-key and async workers`

---

## Phase 12: TUI overlays

**Files modified:**
- `danalyze/tui/widgets.py` — add `NoteOverlay`, `PromptOverlay`
- `danalyze/tui/app.py` — add `enter`, `q`, `w`, `escape` key bindings and
  overlay mount/dismiss logic

**Scope:**
- `enter`: mounts `NoteOverlay` pre-filled with existing note (if any); submit saves;
  empty submit removes; escape cancels without saving
- `q`: mounts `PromptOverlay("Quit? [y/n]")`; `y` exits; `n` or escape dismisses
- `w`: mounts `PromptOverlay` asking for filename; submit calls `write_export`; if
  file already exists, shows error message in the prompt and stays open; escape cancels
- No overlay is mounted while already in a non-BROWSE mode

**Mocks:** none

**Key tests:** `tests/test_tui.py`
- Press `"enter"`: `NoteOverlay` is visible in the DOM
- Type `"hello"` then `"enter"`: overlay dismissed, `"[note]"` tag visible on that entry
- Press `"enter"` on an already-noted entry: `NoteOverlay` pre-filled with existing text
- Type `""` then `"enter"` (backspace all): note removed, `"[note]"` tag gone
- Press `"escape"` inside `NoteOverlay`: dismissed, note unchanged
- Press `"q"`: `PromptOverlay` with quit text is visible
- Press `"y"` in quit prompt: app exits (Pilot catches `SystemExit` or app stops)
- Press `"n"` in quit prompt: overlay dismissed, app continues
- Press `"escape"` in quit prompt: overlay dismissed
- Press `"w"`: `PromptOverlay` for filename is visible
- Type a new filename then `"enter"`: file created on disk, overlay dismissed
- Type an existing filename then `"enter"`: overlay still open, error text visible
- Press `"escape"` in save prompt: overlay dismissed, no file written

**Commit:** `Phase 12: TUI overlays for notes, quit confirm, and file save`

---

## Phase 13: CLI entry point

**Files created:**
- `danalyze/__main__.py`

**Scope:** `argparse` wiring, `setup_logging`, optional `-o` pre-load, initial
`AppState` and `DiskScanner` construction, then `DiskAnalyzerApp(...).run()`.

**Arguments:**
- `PATH` — positional, optional, default: `Path.cwd()`
- `--debug` — flag, enables debug logging
- `--log-file FILE` — optional path, only meaningful with `--debug`
- `-o OUTPUT_CSV` — optional path to an existing export CSV

**Startup validation (before launching TUI):**
- `PATH` must be an existing directory → `sys.exit` with a one-line stderr message
- `-o` file, if given, must exist and be readable → `sys.exit` with a one-line stderr message

**Mocks:** `DiskAnalyzerApp.run` mocked to avoid spawning a live TUI in CLI tests.

**Key tests:** `tests/test_cli.py`
- Calling `__main__.main(["valid/path"])` with mocked `run` does not raise
- Non-existent PATH → `SystemExit` with non-zero code, message printed to stderr
- `-o` with non-existent file → `SystemExit`, message on stderr
- `-o` with a valid export CSV → `AppState.notes` pre-populated from the file
- `--debug` → `setup_logging` called with `debug=True`
- Default PATH when no argument given is `Path.cwd()`

**Commit:** `Phase 13: CLI entry point with argparse and -o flag`
