### Note 1
Multiple of the implementations of state mutations are implemented twice. Once in `state.py`, and again in `app.py`. The mistake is there for the following methods in `state.py`.

```python
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
```

Instead, `tui/app.py` re-implements them with mutation of private state.

```python
async def on_key(self, event: events.Key) -> None:
        """Handle overlay input and BROWSE-mode shortcut keys.

        Arrow keys and r are handled via BINDINGS. This handler manages
        overlay text input, overlay dismissal, and the q/w/enter shortcuts.

        Args:
            event: The key event from Textual.

        Side effects:
            May open or dismiss overlays, update pending_input, save notes,
            write CSV exports, or exit the app.
        """
        key = event.key
        char = event.character
        mode = self._state.mode

        if mode == AppMode.BROWSE:
            if key == "enter":
                self._open_note_overlay()
            elif key == "q":
                self._open_quit_overlay()
            elif key == "w":
                self._open_save_overlay()

        elif mode == AppMode.NOTE_INPUT:
            if key == "escape":
                self._close_overlay()
            elif key == "enter":
                self._submit_note()
            elif key == "backspace":
                self._update_pending(self._state.pending_input[:-1])
            elif char is not None:
                self._update_pending(self._state.pending_input + char)

        elif mode == AppMode.QUIT_PROMPT:
            if char in ("y", "Y"):
                self.exit()
            elif char in ("n", "N") or key == "escape":
                self._close_overlay()

        elif mode == AppMode.SAVE_PROMPT:
            if key == "escape":
                self._close_overlay()
            elif key == "enter":
                await self._submit_save()
            elif key == "backspace":
                self._update_pending(self._state.pending_input[:-1])
            elif char is not None:
                self._update_pending(self._state.pending_input + char)
```

Review app.py and adhere to the original pattern of delegating app state transitions to `state.py`. I expect this to make `app.py` considerably smaller.

### Note 2
The `test_filesystem.py` smoke tests using a real (temporary) file system are a good start

```python
# ---------------------------------------------------------------------------
# RealFilesystem — smoke test (hits real filesystem)
# ---------------------------------------------------------------------------


def test_real_filesystem_scandir_returns_entries(tmp_path: Path) -> None:
    (tmp_path / "file.txt").write_text("hello")
    fs = RealFilesystem()
    entries = list(fs.scandir(tmp_path))
    assert any(e.name == "file.txt" for e in entries)


def test_real_filesystem_stat_returns_size(tmp_path: Path) -> None:
    p = tmp_path / "file.txt"
    p.write_bytes(b"x" * 128)
    fs = RealFilesystem()
    assert fs.stat(p).st_size == 128


def test_real_filesystem_disk_usage_returns_namedtuple(tmp_path: Path) -> None:
    fs = RealFilesystem()
    usage = fs.disk_usage(tmp_path)
    assert usage.total > 0
    assert usage.used >= 0
    assert usage.free >= 0


def test_real_filesystem_is_mount_returns_bool(tmp_path: Path) -> None:
    fs = RealFilesystem()
    result = fs.is_mount(tmp_path)
    assert isinstance(result, bool)
```

However I would like to see two additional types of tests using real file systems.

1) A parity test, asserting that the `InMemoryFilesystem` actually is a faithful recreation of a real file system. Make a test that constructs a temporary version of the `sample_tree` in `conftest.py` and then runs a `RealFilesystem` and a `InMemoryFilesystem` side by side, verifying that they always behave the same, including for `scandir`.

2) Tests on the real file system using scandir. Make sure the results are as expected from the `sample_tree` in `conftest.py`.

### Note 3
The UI should highlight the entire row for indicating the cursor. Right now it is hard to visually distingush which row on the left side corresponds to which row on the right side. Propose a few variations that do not increase the complexity too much. Then ask me for which one to use.

### Note 4
The visual for notes currently hides the note behind a [note] token. I want to actually see the text. Instead, show it as "actual note text". If the text doesn't fit, instead whow "actual no...".

### Note 5
When saving output, there is no need to save all the sizes. We can re-scan those. Only save paths that actually have a note into a short output file with only the notes. Should only have two columns. Path and note. Remember to review the note loading funcationality as well to avoid bugs.