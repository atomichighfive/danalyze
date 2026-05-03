"""NoteStore: typed wrapper around the notes dict from AppState."""

from __future__ import annotations

from pathlib import Path


class NoteStore:
    """Manages user notes keyed by absolute path string.

    Args:
        notes: Optional initial mapping of path strings to note text.
    """

    def __init__(self, notes: dict[str, str] | None = None) -> None:
        """Initialise with an optional pre-existing notes dict.

        Args:
            notes: Mapping of absolute path string to note text. Defaults to
                an empty dict if not supplied.
        """
        self._notes: dict[str, str] = dict(notes) if notes else {}

    def set(self, path: Path, text: str) -> None:
        """Add or update a note. Removes the note if text is empty.

        Args:
            path: Absolute path of the entry being annotated.
            text: Note text. An empty string removes the existing note.
        """
        key = str(path)
        if text:
            self._notes[key] = text
        else:
            self._notes.pop(key, None)

    def get(self, path: Path) -> str | None:
        """Return the note for a path, or None if no note exists.

        Args:
            path: Absolute path of the entry.

        Returns:
            The note text, or None.
        """
        return self._notes.get(str(path))

    def all(self) -> dict[str, str]:
        """Return a copy of all notes.

        Returns:
            A new dict mapping path strings to note text. Mutating the returned
            dict does not affect this store.
        """
        return dict(self._notes)
