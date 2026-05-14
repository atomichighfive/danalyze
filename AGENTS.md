# CLAUDE.md — danalyze

## Project Overview
`danalyze` is a terminal UI tool for analyzing disk space usage.
Stack: Python 3.11+, Textual TUI, pytest for testing.
See ARCHITECTURE.md for full design documentation.

## Development Setup
```bash
uv sync --all-extras
```

## Running the App

```bash
# Start in the current directory
uv run python -m danalyze

# Start at a specific path
uv run python -m danalyze /some/path

# Enable debug logging (writes to danalyze.log)
uv run python -m danalyze --debug

# Specify a custom log file (only meaningful with --debug)
uv run python -m danalyze --debug --log-file /tmp/myrun.log

# Pre-load notes from a previous export CSV
uv run python -m danalyze -o previous_export.csv

# Combine flags
uv run python -m danalyze /some/path --debug -o notes.csv
```

## Installing Locally

```bash
make install
# Equivalent to: uv tool install --editable .
# Makes `danalyze` available as a shell command from anywhere.
# Requires ~/.local/bin on PATH.
```

## Cutting a Release

1. Bump `version` in `pyproject.toml` and `__version__` in `danalyze/__init__.py`
2. Commit: `git commit -m "chore: bump version to X.Y.Z"`
3. Run: `make release VERSION=X.Y.Z`
   - Builds the wheel (`uv build`)
   - Tags `vX.Y.Z` and pushes the tag
   - Creates a GitHub Release with the wheel attached (`gh release create`)

## Installing on Another Machine

Requires `uv` (single static binary):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then install from the private GitHub repo:
```bash
# From git (SSH access required), pinned to a tag:
uv tool install "git+ssh://git@github.com/atomichighfive/danalyze@vX.Y.Z"

# From a downloaded wheel (no git required):
uv tool install ./danalyze-X.Y.Z-py3-none-any.whl
```

## Common Development Commands

```bash
# Install all dependencies (including dev extras)
uv sync --all-extras

# Run the full test suite
uv run pytest

# Run with coverage report
uv run pytest --cov=danalyze --cov-report=term-missing

# Run only unit tests (skip TUI integration tests)
uv run pytest tests/ -k "not test_tui"

# Run TUI integration tests only
uv run pytest tests/test_tui.py

# Run a single test file
uv run pytest tests/test_scanner.py -v

# Run linter and formatter
uv run ruff check .
uv run ruff format .

# Run all pre-commit hooks against every file
uv run pre-commit run --all-files

# Run ad-hoc Python scripts
uv run python <script.py>
```

## Agent UAT (Scripted Mode)

For automated testing by agents or CI systems, use the `--script` flag to run
danalyze in headless mode with a predefined sequence of inputs:

```bash
# Basic usage: pass a JSON array of inputs
uv run python -m danalyze --script '["key.down", "key.right"]'

# With a specific path
uv run python -m danalyze /some/path --script '["key.r"]'

# With debug logging
uv run python -m danalyze --debug --script '["key.down", "key.enter"]'
```

### Script Format

The `--script` argument accepts a JSON array of strings. Each string is either:

- **Key event**: `"key.<name>"` — simulates pressing a key
  - Navigation: `"key.up"`, `"key.down"`, `"key.left"`, `"key.right"`
  - Actions: `"key.enter"` (note/edit), `"key.r"` (scan), `"key.q"` (quit)
  - Confirmation: `"key.y"` (yes), `"key.n"` (no)
- **Text input**: plain string — each character is typed sequentially
  (useful for entering note text)

### Output Format

For each input in the script, danalyze outputs:
1. A separator line: `--- <input> ---`
2. The full screen as plain text (InfoBar, FileTreePanel, SizePanel, StatusBar)

Example output:
```
--- key.down ---
.                               Total: 500.0 GB  Used: 200.0 GB  Free: 300.0 GB 
> apple/                                             --- 
  zebra/                                             --- 
[up/down] navigate  [right] enter dir  [left] back  [r] scan  [s] sort  [enter] 

--- key.right ---
.                               Total: 500.0 GB  Used: 200.0 GB  Free: 300.0 GB 
  apple/                                             --- 
> zebra/                                             --- 
[up/down] navigate  [right] enter dir  [left] back  [r] scan  [s] sort  [enter] 
```

### Writing Agent Tests

Create test scripts that parse the stdout output to verify UI state:

```python
import subprocess
import json

def test_navigation():
    result = subprocess.run(
        ["danalyze", "--script", '[\"key.down\"]'],
        capture_output=True,
        text=True
    )
    output = result.stdout
    assert "--- key.down ---" in output
    # Verify selection moved to second item
    frame = output.split("--- key.down ---")[1]
    assert "zebra" in frame  # assuming zebra is the second item
```

### Tips

- Start with simple scripts (1-2 inputs) and verify output manually
- Use `"key.down"` and `"key.up"` to navigate the file list
- Use `"key.enter"` to open the note overlay, then provide text, then `"key.enter"` again to save
- Use `"key.q"` followed by `"key.y"` to quit the application
- The `> ` prefix in the file tree indicates the currently selected item

## Development Workflow

This project uses **test-driven development** within a phased implementation plan.
See `IMPLEMENTATION_PLAN.md` for the full list of phases and their scope.

Each phase follows these steps in order — do not skip or reorder them:

### 1. Confirm with user
Ask the user — via `AskUserQuestion` — whether to proceed with this phase. Do not
start any work until the user explicitly confirms.

### 2. Clarify plan for phase
Read the phase entry in `IMPLEMENTATION_PLAN.md`. Confirm the scope: which files are
created or modified, what is mocked, and what the key test cases are. Raise any
ambiguities before writing a single line of code.

Mark the phase heading in `IMPLEMENTATION_PLAN.md` with `[started]`, e.g.:
```
## Phase 2: Exceptions & Models [started]
```

### 3. Write tests & mocks
Write all tests for the phase first. They must fail (red) at this point — that is the
goal. If a dependency is not yet implemented, create the minimal stub or mock described
in the phase spec. Tests live in the file named in the phase. Use fixtures from
`tests/conftest.py` wherever possible.

### 4. Implement
Write the production code to make the tests pass (green). Do not add functionality
beyond what the tests require.

### 5. Test and fix
Run `uv run pytest` and fix failures until all tests in the current phase pass.
Tests from earlier phases must continue to pass (no regressions).

### 6. Pre-commit
Run `uv run pre-commit run --all-files`. Fix any ruff lint or formatting issues.
Do not suppress ruff errors with `# noqa` without a justifying comment.

### 7. UAT
Determine whether the phase produced behaviour the user can observe in a terminal.

- **If yes:** draft a short UAT plan (numbered steps, each a concrete action + expected
  result), then present it to the user one step at a time using the `AskUserQuestion`
  tool. Wait for the user to confirm each step passes before moving on. If a step
  fails, fix the issue and restart from step 5.
- **If no** (e.g. the phase only adds pure-logic modules or test infrastructure with no
  runnable entry point yet): state the rationale clearly and ask the user — via
  `AskUserQuestion` — whether to skip UAT for this phase. Do not proceed to step 8
  until the user approves the skip.

### 8. Commit
Mark the phase heading in `IMPLEMENTATION_PLAN.md` with `[done]`, e.g.:
```
## Phase 2: Exceptions & Models [done]
```

Before writing the commit message, always run `git diff --staged` to review the exact
changes being committed. Write the message to reflect what actually changed, not what
was planned.

```bash
git add -A
git commit -m "Phase N: <short description>"
```
Use the commit message template from the phase entry in `IMPLEMENTATION_PLAN.md` as a
starting point, but adjust it to match the real diff.

### Mocking policy
- Mocks are explicitly declared per phase in `IMPLEMENTATION_PLAN.md`.
- Prefer `InMemoryFilesystem` over `unittest.mock` for scanner tests — it exercises
  real code paths.
- Use `unittest.mock.AsyncMock` only where declared in the phase spec, and only for
  the duration of that phase. Later phases replace mocks with real implementations.

## Dependency Policy
Use `uv` for all dependency management. Allowed external runtime dependencies:
`textual` (TUI), `pandas` (CSV export and log writing).
Before adding any further external dependency, ask the user explicitly.

## Architecture Summary
See ARCHITECTURE.md. The key layers:

| Layer | Location | Rule |
|-------|----------|------|
| Domain models | `models.py` | Pure dataclasses, no I/O |
| Pure logic | `state.py`, `formatter.py` | Pure functions, no I/O |
| Services | `scanner.py`, `export.py` | I/O via injected `FilesystemProtocol` |
| TUI | `tui/` | Thin renderers only, no business logic |

## Coding Conventions

### Typing
- All function signatures must have full type annotations.
- Use `from __future__ import annotations` in every module.
- Prefer `X | None` over `Optional[X]`.

### Docstrings
Every public function, method, and class must have a Google-style docstring with:
- One-line summary
- `Args:` section (all parameters)
- `Returns:` section (if non-None)
- `Raises:` section (all raised exceptions)
- `Side effects:` section if applicable
- `Assumptions:` section if applicable

Example:
```python
def format_size(size_bytes: int) -> str:
    """Format a byte count as a human-readable string.

    Args:
        size_bytes: Non-negative byte count.

    Returns:
        Human-readable string, e.g. "1.5 GB".

    Raises:
        ValueError: If size_bytes is negative.
    """
```

### Logging
Every module uses `get_logger` from `logging_config.py` — never `logging.getLogger` directly:

```python
from danalyze.logging_config import get_logger
log = get_logger(__name__)
```

`log_line_name` is a **required** first argument on every call. It must be a unique,
human-readable dotted name for that specific call site (`<module>.<function>.<event>`),
so the line of code can be found by grepping the log file for the name:

```python
log.debug("scanner.list_dir.start", "Listing directory %s", path)
log.error("scanner.scan_sizes.perm_denied", "Cannot read %s: %s", path, exc, exc_info=True)
```

**Log entry format** — CSV, one row per entry. The stdlib `csv` module handles quoting
and escaping automatically. Header row is written once when the file is created:
```
timestamp,async_process_id,module,log_line_name,message
```

**Async processes**: before spawning a Textual worker, call `begin_async_process()` to
generate an ID and log the spawn. Pass the ID to the worker, which calls
`set_async_process_id()` at its start. This links all log lines from a worker back to
the spawn event:

```python
# Parent (tui/app.py):
process_id = begin_async_process(log, "scan-sizes")
self.run_worker(self._worker_scan_sizes(node, process_id))

# Worker:
async def _worker_scan_sizes(self, node: FileNode, process_id: str) -> None:
    set_async_process_id(process_id)
    log.debug("app.worker.scan_sizes.start", "Worker started for %s", node.path)
    ...
```

Other rules:
- Log significant operations at `DEBUG`: directory listings, state transitions, exports.
- Always call `log.error(..., exc_info=True)` before re-raising exceptions.
- Never use `print()` for diagnostic output.

### Error Handling
- Raise exceptions eagerly. Never swallow unexpected exceptions silently.
- Use typed exceptions from `exceptions.py` (`ScanError`, `ExportError`, etc.).
- Wrap OS errors with context: `raise ScanError(f"Cannot scan {path}") from exc`
- Permission errors during scan: set `node.scan_status = ScanStatus.ERROR` (do not crash).

### Testability
- Business logic must live in pure functions (no I/O). Write those first.
- Use `InMemoryFilesystem` from `danalyze.filesystem` for all scanner tests.
- Use `base_state()` fixture from `tests/conftest.py` as the starting point for state tests.
- TUI tests use `textual.testing.Pilot` — keep them thin (test key -> state, not rendering).
- Log assertions use `pytest`'s `caplog` fixture; records carry `log_line_name` and
  `async_process_id` attributes set by `AsyncProcessFilter`.

### File Output Safety (No Overwriting)
- Log files: use `find_safe_log_path()` to count up until a free filename is found
  (e.g. `danalyze.log` -> `danalyze.1.log` -> `danalyze.2.log`).
- CSV export (`w` key): if the user-entered filename already exists, show an error
  in the prompt and ask them to enter a different filename. Never overwrite silently.

### General Rules
- No `# type: ignore` without a comment explaining why.
- No bare `except:` or `except Exception:` without re-raising or explicit justification.
- No mutable default arguments.
- No global mutable state outside of the Textual App instance.
