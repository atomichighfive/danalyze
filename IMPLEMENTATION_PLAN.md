# Implementation Plan: CLI Packaging

## Feature Overview

Package `danalyze` as a proper installable CLI tool so it can be invoked as `danalyze`
from anywhere in the terminal, and installed on other machines from the private GitHub
repository without publishing to PyPI.

---

## Phase 1: Console script entry point + Makefile [done]

**Files modified / created:**
- `pyproject.toml` — add `[project.scripts]` section
- `danalyze/__main__.py` — add `cli()` zero-argument wrapper
- `Makefile` — new file with `install`, `build`, `release` targets

**`pyproject.toml` addition:**
```toml
[project.scripts]
danalyze = "danalyze.__main__:cli"
```

**`danalyze/__main__.py` addition** (new function after `main()`):
```python
def cli() -> None:
    """Console script entry point."""
    main(sys.argv[1:])
```
No changes to `main()`, its signature, or any tests.

**`Makefile`:**
```makefile
VERSION ?= $(shell python -c "from danalyze import __version__; print(__version__)")

.PHONY: install build release

install:
	uv tool install --editable .

build:
	uv build

release: build
	git tag v$(VERSION)
	git push origin v$(VERSION)
	gh release create v$(VERSION) dist/danalyze-$(VERSION)-*.whl \
		--title "danalyze v$(VERSION)" --notes ""
```

**Tests:** No new tests required. The `cli()` wrapper is a one-liner that delegates
to `main()`, which is already covered by existing tests.

**Mocks:** none

**Commit:** `Phase 14: CLI packaging — console script entry point and Makefile`

---

## Phase 15: Symlink handling [done]

**Problem:** `scan_sizes` calls `os.stat()` (via `FilesystemProtocol.stat`) on every
child, following symlinks. This crashes on broken symlinks (`FileNotFoundError`) and
circular symlinks (`OSError: [Errno 40] Too many levels of symbolic links`).

**Desired behaviour:**
- Symlinks appear in the tree with `@` as the prefix icon (not `>` or space).
- Symlinks to directories can be navigated into (right-arrow) but are never scanned
  for size — they remain `size=None` and `scan_status=UNSCANNED` forever.
- Symlinks to files and broken symlinks are treated as leaves with no size.
- No size and no bar is shown for any symlink; `---` is displayed in the size panel.

**Files modified / created:**
- `danalyze/models.py`
- `danalyze/filesystem.py`
- `danalyze/scanner.py`
- `danalyze/tui/widgets.py`
- `tests/test_scanner.py`
- `tests/test_tui.py`

---

### `danalyze/models.py`

Add `is_symlink: bool = False` to `FileNode` after `is_dir`:

```python
@dataclass
class FileNode:
    path: Path
    name: str
    is_dir: bool
    is_symlink: bool = False   # ← new field
    size: int | None = None
    ...
```

Update the class docstring to document `is_symlink`.

---

### `danalyze/filesystem.py`

**`_FakeDirEntry`**: add `_is_symlink: bool = False` constructor parameter and
`is_symlink()` method:

```python
def __init__(self, ..., _is_symlink: bool = False) -> None: ...

def is_symlink(self) -> bool:
    return self._is_symlink
```

**`InMemoryFilesystem`**: add `_symlinks: set[str]` (paths that are symlinks) to
`__init__`, and a new public method:

```python
def add_symlink(
    self,
    path_str: str,
    *,
    target_is_dir: bool = False,
) -> None:
    """Register a symlink under an existing directory in the fake filesystem.

    The immediate parent directory must already exist. The symlink is inserted
    into the parent's contents dict as a sentinel so scandir yields it.

    Args:
        path_str: Absolute path string for the symlink.
        target_is_dir: True if the symlink points to a directory.

    Raises:
        ValueError: If the parent directory is not a known directory.
    """
```

`add_symlink` inserts a `("symlink", target_is_dir)` entry into `_nodes` and injects
the name into the parent dir's live contents dict so `scandir` discovers it.

**`InMemoryFilesystem.scandir`**: when building `_FakeDirEntry` for a child, check
`_nodes[child_path][0] == "symlink"` and pass `_is_symlink=True` and
`_is_dir=<target_is_dir>` accordingly.

---

### `danalyze/scanner.py`

**`list_directory`** — detect symlinks without following them:

```python
is_sym = entry.is_symlink()
try:
    is_dir_val = entry.is_dir()  # follows link; False for broken/circular
except OSError:
    is_dir_val = False
child = FileNode(
    path=Path(entry.path),
    name=entry.name,
    is_dir=is_dir_val,
    is_symlink=is_sym,
    scan_status=ScanStatus.UNSCANNED,
)
```

**`_scan_dir`** — skip symlinks entirely (no stat, no recursion):

```python
for child in node.children or []:
    if child.is_symlink:
        continue          # never scan symlinks
    elif child.is_dir:
        await self._scan_dir(child)
        ...
    else:
        await self._scan_file(child)
        ...
```

Log the skip at DEBUG level: `"scanner.scan_sizes.symlink_skipped"`.

---

### `danalyze/tui/widgets.py`

**`FileTreePanel._build`** — add symlink prefix before the dir check:

```python
if is_error:
    prefix = "!"
elif child.is_symlink:
    prefix = "@"     # symlink (may or may not point to a dir)
elif child.is_dir:
    prefix = ">"
else:
    prefix = " "
```

No change to `SizePanel` — symlinks show `---` naturally (UNSCANNED status).

---

### Key tests — `tests/test_scanner.py`

```
test_list_directory_detects_symlink
    InMemoryFilesystem + add_symlink → child.is_symlink is True

test_list_directory_symlink_to_dir_has_is_dir_true
    add_symlink(..., target_is_dir=True) → child.is_dir is True

test_scan_sizes_skips_symlink_to_dir
    add_symlink(..., target_is_dir=True); scan_sizes → symlink child stays UNSCANNED

test_scan_sizes_skips_broken_symlink
    add_symlink(..., target_is_dir=False); scan_sizes → symlink child stays UNSCANNED

test_scan_sizes_symlink_does_not_contribute_to_parent_size
    dir with file (100 bytes) + symlink; scan_sizes → parent.size == 100

test_scan_sizes_circular_symlink_does_not_crash
    add_symlink pointing to parent path (circular); scan_sizes completes without exception
```

### Key tests — `tests/test_tui.py`

```
test_symlink_shown_with_at_icon
    InMemoryFilesystem + add_symlink; list_directory; assert "@" in FileTreePanel text
```

**Mocks:** none

**Commit:** `Phase 15: Symlink handling — detect, skip scanning, show @ icon`
