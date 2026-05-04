# Architecture: danalyze

## Overview
danalyze is a terminal UI application for identifying disk space usage.
It displays an interactive file tree with per-entry sizes and ASCII bar charts,
supports note-taking, and can export annotated paths to JSON.

## Design Goals
1. **Testability first** — all business logic is pure (no I/O), exercisable without
   a terminal or real filesystem.
2. **Layered architecture** — strict separation: domain → data → app state → TUI.
3. **Fail loudly** — raise typed exceptions eagerly; never silently swallow errors.
4. **Traceability** — structured logging throughout; debug mode writes full trace to file.

---

## Layer Map

```
┌─────────────────────────────────────────────────────────┐
│  TUI Layer          tui/app.py, tui/widgets.py          │
│  (Textual widgets, thin renderers, key bindings)        │
├─────────────────────────────────────────────────────────┤
│  Application State  state.py                            │
│  (AppState dataclass + pure event-handler functions)    │
├─────────────────────────────────────────────────────────┤
│  Services           scanner.py, notes.py, export.py     │
│  (I/O operations, all depend on injected protocols)     │
├─────────────────────────────────────────────────────────┤
│  Domain             models.py, formatter.py             │
│  (Pure dataclasses and pure functions — zero I/O)       │
├─────────────────────────────────────────────────────────┤
│  Infrastructure     filesystem.py, logging_config.py    │
│  (Protocols, real/fake filesystem, structured logging)  │
└─────────────────────────────────────────────────────────┘
```

---

## Module Reference

### `models.py`
Pure dataclasses. No I/O, no side effects.

```
FileNode        path, name, is_dir, is_symlink, size, children, scan_status, error
                  is_symlink: bool          — True if the entry is a symbolic link;
                                             symlinks are never stat-ed or recursed
                  size: int | None          — None until scanned; always None for symlinks
                  children: list | None     — None until listed
                  error: str | None         — human-readable error message when
                                             scan_status == ERROR; None otherwise
FileTree        root FileNode + helpers (find_by_path, ancestors)
DriveInfo       device, total, used, free, mount_point
ScanStatus      StrEnum: UNSCANNED | LISTED | SCANNING | DONE | ERROR
                  UNSCANNED: not yet listed (children = None)
                  LISTED: children known via scandir, but no sizes computed
                  SCANNING: recursive size computation in progress
                  DONE: sizes fully computed and cached
                  ERROR: an OS-level read error occurred; error field is set;
                         children and size remain None
AppMode         StrEnum: BROWSE | NOTE_INPUT | QUIT_PROMPT | SAVE_PROMPT
```

### `filesystem.py`
Dependency injection seam for all OS calls.

```
FilesystemProtocol   Protocol with: scandir, stat, disk_usage, is_mount
RealFilesystem       Wraps os.scandir, os.stat, shutil.disk_usage, os.path.ismount
InMemoryFilesystem   Dict-based fake for tests; built with FakeEntry builder DSL
```

`InMemoryFilesystem` accepts a nested dict:
```python
fs = InMemoryFilesystem({
    "/home/user": {
        "docs": {"report.pdf": 1_024_000},
        ".bashrc": 4_096,
    }
})
```

### `scanner.py`
Async directory scanner. Depends on `FilesystemProtocol`.

Two distinct operations:

```
DiskScanner(fs: FilesystemProtocol)

  .list_directory(node: FileNode) -> None
      Performs a single os.scandir() on node.path.
      Populates node.children with FileNode stubs (no sizes).
      Sets node.scan_status = LISTED on success.
      Cached — subsequent calls are no-ops unless node.scan_status == UNSCANNED.
      Called automatically when the user navigates into a directory (right arrow).
      ON ERROR: catches PermissionError and OSError, sets node.scan_status = ERROR
      and node.error to a short human-readable message, logs at ERROR level, and
      returns normally. Does NOT raise. The error is surfaced via the node itself.

  .scan_sizes(node: FileNode) -> None
      Recursively computes sizes for node and all descendants.
      Calls list_directory() on any UNSCANNED subdirectory encountered.
      Sets node.scan_status throughout: SCANNING -> DONE.
      ON ERROR per child: if stat() or list_directory() fails on a child, that
      child is marked ERROR (scan_status=ERROR, error=message) and scanning
      continues with remaining siblings. The parent's size is the sum of
      successfully-scanned children only (partial size, still displayed).
      Only triggered explicitly by the user pressing `r`.
      Emits progress via asyncio callback (used by TUI to refresh display).

  .invalidate(path: Path) -> None
      Clears path from cache, resetting it to UNSCANNED.
      Called internally before a forced re-scan triggered by `r`.
```

Scan lifecycle per node:
```
UNSCANNED -> (right arrow) -> LISTED -> (r key) -> SCANNING -> DONE
                                                             -> ERROR (per-node, non-fatal)
```

Symlinks are a special case: they are listed by `list_directory` (visible in the tree)
but permanently skipped by `scan_sizes`. They stay `UNSCANNED` with `size=None` forever.
`is_symlink=True` is detected in `list_directory` via `DirEntry.is_symlink()` (no stat
required). `is_dir` for a symlink reflects the resolved type (so symlink-to-dirs can be
navigated into), but `scan_sizes` checks `is_symlink` first and skips before any stat call.

Sizes display as `---` in the size panel until a node reaches DONE.
Symlinks also display `---` (they never leave UNSCANNED).
ERROR nodes display their error message instead of a size; scanning continues for siblings.
`r` always forces a fresh scan of the current view_root (invalidates + re-scans).

### `formatter.py`
Pure functions only. Zero dependencies.

```
format_size(bytes: int) -> str
    Maps to B / KB / MB / GB / TB with 1 decimal place.
    e.g. 1_536_000 -> "1.5 MB"

render_bar(fraction: float, width: int) -> str
    Returns ASCII bar: fraction in [0,1], e.g. 0.62, width=10 -> "██████░░░░"
    Raises ValueError if fraction outside [0,1] or width < 1.

format_bar_line(size: int, total: int, bar_width: int) -> str
    Combines format_size + render_bar into a single display string.
```

### `state.py`
`AppState` dataclass + pure event-handler functions. Zero I/O.

```python
@dataclass
class AppState:
    view_root: FileNode        # Currently visible directory
    selected_index: int        # Index into view_root.children
    notes: dict[str, str]      # absolute path string -> note text
    mode: AppMode
    pending_input: str         # Text being typed in NOTE_INPUT / SAVE_PROMPT
    drive_info: DriveInfo
```

Pure functions (state in -> state out, no mutations):
```
navigate_down(state)         -> AppState
navigate_up(state)           -> AppState
navigate_into(state)         -> AppState   # step into selected dir (right arrow)
                                           # no-op if selected node is ERROR or a file
navigate_out(state)          -> AppState   # step out to parent (left arrow)
begin_note(state)            -> AppState   # mode -> NOTE_INPUT
cancel_input(state)          -> AppState   # mode -> BROWSE, clears pending_input
submit_note(state, text)     -> AppState   # saves or clears note; mode -> BROWSE
begin_quit(state)            -> AppState   # mode -> QUIT_PROMPT
begin_save(state)            -> AppState   # mode -> SAVE_PROMPT
append_input(state, char)    -> AppState
backspace_input(state)       -> AppState
selected_node(state)         -> FileNode   # helper: view_root.children[selected_index]
```

Raises `NavigationError` for invalid transitions (e.g. navigate_into a file).

### `notes.py`
`NoteStore` wraps the `notes` dict from AppState with typed validation.

```
NoteStore(notes: dict[str, str])
  .set(path: Path, text: str) -> None   # empty text removes note
  .get(path: Path) -> str | None
  .all() -> dict[str, str]
```

### `export.py`
Serialization and file writing. Uses pandas to build and write the CSV.

Output CSV columns:
```
path,size_bytes,size_human,note
/home/user/Documents,48318054400,45.0 GB,check this folder
/home/user/Downloads,13003505664,12.1 GB,
```

`size_bytes` is the raw integer (sortable/filterable); `size_human` is the
human-readable string from `format_size()`. `note` is empty string if no note.
Only entries that have been fully scanned (ScanStatus.DONE) or have a note are
included. Entries with notes but incomplete scans have `size_bytes` as empty.

```
build_export_df(notes: dict[str, str], nodes: dict[str, FileNode]) -> pd.DataFrame
    Builds a pandas DataFrame from notes and scanned nodes.
    Pure function — no I/O.

write_export(df: pd.DataFrame, file_path: Path) -> None
    Writes df to file_path as CSV using df.to_csv(index=False).
    Raises ExportError if file_path already exists (never overwrites).
    Raises ExportError on any I/O failure.

load_notes_from_csv(file_path: Path) -> dict[str, str]
    Reads an export CSV and returns a {path: note} dict of non-empty notes.
    Raises ExportError if the file does not exist, is unreadable, or lacks
    the expected columns (path, note).
    Pure of side effects beyond reading the file.
    Called by __main__.py at startup when -o is supplied; the resulting dict
    is passed directly into the initial AppState.notes.
```

### `logging_config.py`
All logging infrastructure lives here. Every other module imports `get_logger` from
this module instead of using `logging` directly.

#### Log entry format
Log files are CSV with a header row. The stdlib `csv` module is used for writing
(streaming, one row per event) so quoting and escaping of special characters
(newlines, commas, quotes) are handled automatically by the CSV spec.

Columns in fixed order:
```
timestamp,async_process_id,module,log_line_name,message
```

Example:
```csv
timestamp,async_process_id,module,log_line_name,message
2026-05-03T14:23:01.123456,main,danalyze.tui.app,app.worker.scan_sizes.spawn,Spawning async process scan-sizes-ab12cd34
2026-05-03T14:23:01.124001,scan-sizes-ab12cd34,danalyze.scanner,scanner.scan_sizes.start,Starting size scan for /home/user/Documents
```

Log files can be loaded directly into a pandas DataFrame for filtering and analysis:
```python
import pandas as pd
df = pd.read_csv("danalyze.log")
df[df["log_line_name"] == "scanner.scan_sizes.start"]
df[df["async_process_id"] == "scan-sizes-ab12cd34"]
```

The log file extension is `.log` but the content is valid CSV.

#### async_process_id
Each async worker runs in its own logical "process" with a unique ID. The ID is stored
in a `contextvars.ContextVar` so it propagates automatically into async tasks spawned
from that context without any explicit passing.

```python
# In logging_config.py:
_async_process_id: ContextVar[str] = ContextVar("async_process_id", default="main")
```

When a Textual worker is about to be spawned, the parent calls `begin_async_process()`
which generates the ID and logs the spawn event. The worker then calls
`set_async_process_id()` with that ID at its start.

```
get_logger(module_name: str) -> StructuredLogger
    Returns a StructuredLogger bound to the given module name.
    Use as: log = get_logger(__name__) at module level.

begin_async_process(parent_log: StructuredLogger, process_name: str) -> str
    Generates a unique async_process_id of the form "<process_name>-<hex8>".
    Emits a DEBUG entry on parent_log with log_line_name="async.process.spawn"
    recording the new ID.
    Returns the ID so the caller can pass it to the spawned worker.

set_async_process_id(process_id: str) -> None
    Sets the async_process_id context variable for the current async context.
    Call this at the start of every Textual worker function, passing the ID
    returned by begin_async_process().

find_safe_path(base: Path) -> Path
    Returns base if it does not exist, otherwise counts up:
    danalyze.log -> danalyze.1.log -> danalyze.2.log -> ...
    Used for both log file naming and (via export.py) safe export paths.

setup_logging(*, debug: bool, log_file: Path | None) -> None
    Configures the root logger.
    debug=True: level DEBUG, attaches StructuredFileHandler writing to a safe path.
    debug=False: level WARNING, stderr only.
    Installs AsyncProcessFilter on all handlers so every record carries async_process_id.
```

#### StructuredLogger
A thin wrapper around `logging.Logger` that makes `log_line_name` a required positional
argument on every call, enforcing the convention at the API level rather than by
convention:

```python
class StructuredLogger:
    def debug(self, name: str, msg: str, *args: object, **kwargs: object) -> None: ...
    def info(self, name: str, msg: str, *args: object, **kwargs: object) -> None: ...
    def warning(self, name: str, msg: str, *args: object, **kwargs: object) -> None: ...
    def error(self, name: str, msg: str, *args: object, exc_info: bool = False) -> None: ...
```

Usage at every call site:
```python
log = get_logger(__name__)

log.debug("scanner.list_dir.start", "Listing %s", path)
log.error("scanner.scan_sizes.perm_denied", "Cannot read %s: %s", path, exc, exc_info=True)
```

#### log_line_name convention
Names follow the pattern `<module_short>.<function>.<event>` and must be unique
across the entire codebase (one name per distinct call site):

```
scanner.list_dir.start          scanner.list_dir.cached
scanner.scan_sizes.start        scanner.scan_sizes.progress
scanner.scan_sizes.done         scanner.scan_sizes.perm_denied
scanner.invalidate.called
app.worker.list_dir.spawn       app.worker.scan_sizes.spawn
state.navigate_into.entered     state.navigate_out.at_root
export.write.file_exists        export.write.done
async.process.spawn             (reserved for begin_async_process())
```

#### Usage in Textual workers
```python
# In tui/app.py — before spawning:
process_id = begin_async_process(log, "scan-sizes")
self.run_worker(self._worker_scan_sizes(node, process_id))

# In the worker function:
async def _worker_scan_sizes(self, node: FileNode, process_id: str) -> None:
    set_async_process_id(process_id)
    log.debug("app.worker.scan_sizes.start", "Worker started for %s", node.path)
    await self._scanner.scan_sizes(node)
```

#### Testing logging
`StructuredLogger` delegates to the standard `logging.Logger`, so `pytest`'s built-in
`caplog` fixture captures all records. Each record has `log_line_name` and
`async_process_id` attributes added by the filter:

```python
def test_scan_emits_start_log(caplog):
    with caplog.at_level(logging.DEBUG, logger="danalyze.scanner"):
        ...  # trigger scan
    names = [r.log_line_name for r in caplog.records]
    assert "scanner.scan_sizes.start" in names

def test_async_process_id_propagates(caplog):
    set_async_process_id("test-proc-01")
    with caplog.at_level(logging.DEBUG):
        log.debug("test.event", "hello")
    assert caplog.records[-1].async_process_id == "test-proc-01"
```

### `tui/app.py`
`DiskAnalyzerApp(textual.App)`. Composes all services.

Responsibilities:
- Receive key events -> call pure state functions -> post updated state to widgets
- On right-arrow into dir: call `scanner.list_directory(node)` (fast, just lists children)
- On `r`: call `scanner.scan_sizes(node)` with invalidation (forces fresh recursive size scan)
- Both scanner calls run as Textual `workers` (async, non-blocking) and post messages to refresh widgets

### `tui/widgets.py`
```
InfoBar          Renders DriveInfo as top bar with usage percentage
FileTreePanel    Scrollable list of FileNode entries with > prefix for dirs,
                 @ prefix for symlinks, ! prefix for ERROR nodes.
                 Symlink-to-dirs show @ (not >) so the user can distinguish them.
                 The error message appears in place of the filename suffix for ERROR nodes.
SizePanel        Per-entry size + bar chart, aligned with FileTreePanel rows.
                 ERROR nodes show the short error string (e.g. "permission denied")
                 in place of a size and bar. No bar is rendered.
                 Symlinks show --- (size is always None).
StatusBar        Context-sensitive hints: [q]uit [w]rite [r]escan [enter]note
NoteOverlay      Single-line text input shown when mode == NOTE_INPUT
PromptOverlay    Yes/no or filename prompt (QUIT_PROMPT / SAVE_PROMPT)
```

All widgets are reactive to `AppState` via Textual's `reactive` + `watch_*` pattern.
Widgets do NOT hold business logic.

---

## Project Layout

```
danalyze/
├── __init__.py
├── __main__.py           # argparse, setup_logging, launch app
├── exceptions.py         # DiskAnalyzerError, ScanError, ExportError, NavigationError
├── models.py
├── filesystem.py
├── scanner.py
├── formatter.py
├── state.py
├── notes.py
├── export.py
├── logging_config.py
└── tui/
    ├── __init__.py
    ├── app.py
    └── widgets.py

tests/
├── __init__.py
├── conftest.py           # fixtures: sample_tree(), fake_fs(), base_state()
├── test_models.py
├── test_scanner.py
├── test_formatter.py
├── test_state.py         # heaviest test file: all navigation + mode transitions
├── test_notes.py
├── test_export.py
└── test_tui.py           # Textual Pilot integration tests

pyproject.toml
```

---

## Key Testability Pattern: State Machine Testing

The most impactful testing surface is `state.py`. Because all functions are pure,
tests require zero mocking:

```python
def test_navigate_into_directory():
    state = base_state(selected_index=0)  # selected is a dir
    new_state = navigate_into(state)
    assert new_state.view_root == state.view_root.children[0]
    assert new_state.selected_index == 0

def test_note_submit_empty_removes_note():
    state = base_state(notes={"/home/user/docs": "delete this"})
    state = begin_note(state)
    state = submit_note(state, "")
    assert "/home/user/docs" not in state.notes

def test_escape_cancels_note_input():
    state = begin_note(base_state())
    assert state.mode == AppMode.NOTE_INPUT
    state = cancel_input(state)
    assert state.mode == AppMode.BROWSE
```

Scanner tests use `InMemoryFilesystem` — no real filesystem access:
```python
async def test_list_directory_populates_children():
    fs = InMemoryFilesystem({"/root": {"a.txt": 100, "b.txt": 200}})
    scanner = DiskScanner(fs)
    node = FileNode(path=Path("/root"), scan_status=ScanStatus.UNSCANNED, ...)
    await scanner.list_directory(node)
    assert node.scan_status == ScanStatus.LISTED
    assert len(node.children) == 2
    assert all(c.size is None for c in node.children)

async def test_scan_sizes_computes_sizes():
    fs = InMemoryFilesystem({"/root": {"a.txt": 100, "b.txt": 200}})
    scanner = DiskScanner(fs)
    node = FileNode(path=Path("/root"), ...)
    await scanner.scan_sizes(node)
    assert node.scan_status == ScanStatus.DONE
    assert node.size == 300

async def test_r_forces_rescan():
    fs = InMemoryFilesystem({"/root": {"a.txt": 100}})
    scanner = DiskScanner(fs)
    node = FileNode(path=Path("/root"), ...)
    await scanner.scan_sizes(node)
    assert node.size == 100
    fs.update_file_size("/root/a.txt", 999)
    scanner.invalidate(Path("/root"))
    await scanner.scan_sizes(node)
    assert node.size == 999   # fresh scan, not cached
```

Formatter tests need no fixtures (pure functions):
```python
def test_format_size_gigabytes():
    assert format_size(1_500_000_000) == "1.5 GB"

def test_render_bar_full():
    assert render_bar(1.0, 10) == "██████████"
```

---

## TUI Layout

```
+------------------------------------------------------------------+
|  /dev/sda1   Total: 500.0 GB   Used: 312.4 GB   Free: 187.6 GB  |  InfoBar
+---------------------------------------+--------------------------+
|  /home/user/                          |                          |
| > Documents/                          |  45.2 GB  ████████░░░░  |
|   Downloads/        [note]            |  12.1 GB  ████░░░░░░░░  |
|   .cache/                             |   8.3 GB  ██░░░░░░░░░░  |
| ! private/          [error]           |  permission denied       |
| @ .venv/            [note]            |  ---                     |
|   .bashrc                             |   4.0 KB  ░░░░░░░░░░░░  |
+---------------------------------------+--------------------------+
|  [up/down] navigate  [right] enter  [left] back  [r] scan       |
|  [enter] note  [q] quit  [w] write                              |
+------------------------------------------------------------------+
```

- Entries with notes show `[note]` tag.
- ERROR entries show `!` sigil, `[error]` tag in the tree, and the error message in the size panel.
- Symlinks show `@` sigil and always display `---` in the size panel (never scanned).
- Sizes show `---` until `r` has been pressed for that branch.
- Bar widths are relative to successfully-scanned siblings; ERROR and symlink entries have no bar.

---

## CLI Interface

```
danalyze [PATH] [--debug] [--log-file FILE] [-o OUTPUT_CSV]

Arguments:
  PATH          Starting directory (default: current working directory)

Options:
  --debug       Enable debug logging (written to log file)
  --log-file    Log file path (default: danalyze.log, only used with --debug)
  -o OUTPUT_CSV Path to an existing export CSV file. Notes from the file are
                pre-filled into the app at startup. Paths in the CSV that do not
                exist under PATH are loaded but shown as absent (greyed out) if
                encountered during navigation, and included in any subsequent export.
```

---

## Packaging & Installation

danalyze is packaged as a Python wheel using `hatchling`. The `[project.scripts]`
entry point in `pyproject.toml` exposes a `danalyze` shell command:

```toml
[project.scripts]
danalyze = "danalyze.__main__:cli"
```

`cli()` is a zero-argument wrapper in `__main__.py` that calls `main(sys.argv[1:])`.
Console script entry points must be zero-argument callables; this wrapper keeps
`main(argv)` testable with an explicit argument list.

### Local installation
```bash
make install
# equivalent to: uv tool install --editable .
```
`uv tool install` places `danalyze` in a dedicated isolated virtualenv and symlinks
the command into `~/.local/bin` (which must be on `PATH`). The `--editable` flag
means source changes take effect immediately without reinstalling.

### Installing on another machine
```bash
# From the private GitHub repo (requires SSH access):
uv tool install "git+ssh://git@github.com/atomichighfive/danalyze@v0.1.0"

# From a downloaded wheel (no git required):
uv tool install ./danalyze-0.1.0-py3-none-any.whl
```

### Cutting a release
```bash
# 1. Bump version in pyproject.toml and danalyze/__init__.py
# 2. Commit the bump
# 3. Run:
make release VERSION=0.2.0
```
`make release` builds the wheel, creates and pushes a git tag, and publishes a
GitHub Release with the wheel attached (uses `gh` CLI).

---

## Error Handling Convention

Three distinct error classes with different handling:

### 1. Per-node read errors (non-fatal, inline)
`PermissionError` and `OSError` raised by `scandir()` or `stat()` during navigation
or scanning are caught inside `DiskScanner`. The affected `FileNode` is marked:
```
node.scan_status = ScanStatus.ERROR
node.error = "permission denied"   # or other short OS error message
```
The error is logged at ERROR level with `exc_info=True`. Scanning continues for all
siblings. The error is visible inline in the TUI — never shown as a popup or crash.

Invariant: `node.scan_status == ERROR` implies `node.error is not None`.

`navigate_into()` on an ERROR node is a no-op — the node cannot be entered.

### 2. Fatal startup errors (clean exit before UI)
Errors that prevent the app from starting at all (e.g. `-o` file not found, CSV
malformed, starting PATH not a directory) are caught in `__main__.py` before the
Textual app is launched. They are printed as a clear one-line message to stderr and
exit with a non-zero code. No TUI is shown.

```python
# __main__.py
try:
    notes = load_notes_from_csv(args.output)
except ExportError as exc:
    sys.exit(f"Error loading {args.output}: {exc}")
```

### 3. Unexpected application errors (error overlay)
Any unhandled exception that escapes a Textual worker or event handler is caught by
`DiskAnalyzerApp`'s global error handler. It logs the full traceback at ERROR level
and shows an error overlay with a summary message and "press any key to exit". The
app exits cleanly rather than crashing with a traceback on the terminal.

`log.error(..., exc_info=True)` is always called before any re-raise or surface,
ensuring the full traceback is in the log file.

---

## Dependencies

```toml
[project]
requires-python = ">=3.11"
dependencies = ["textual>=0.47", "pandas>=2.0"]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23"]
```

Managed with `uv`. Allowed external runtime dependencies: `textual`, `pandas`.
Before adding any further external dependency, ask the user explicitly.
