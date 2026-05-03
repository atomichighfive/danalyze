"""Tests for danalyze.notes — NoteStore."""

from __future__ import annotations

from pathlib import Path

from danalyze.notes import NoteStore

_PATH = Path("/home/user/docs")
_OTHER = Path("/home/user/other")


def test_set_and_get_returns_text() -> None:
    store = NoteStore()
    store.set(_PATH, "my note")
    assert store.get(_PATH) == "my note"


def test_set_empty_removes_note() -> None:
    store = NoteStore()
    store.set(_PATH, "temporary")
    store.set(_PATH, "")
    assert store.get(_PATH) is None


def test_get_unknown_path_returns_none() -> None:
    store = NoteStore()
    assert store.get(_PATH) is None


def test_get_does_not_affect_other_paths() -> None:
    store = NoteStore()
    store.set(_PATH, "note")
    assert store.get(_OTHER) is None


def test_all_returns_copy() -> None:
    store = NoteStore()
    store.set(_PATH, "note")
    result = store.all()
    result[str(_PATH)] = "mutated"
    assert store.get(_PATH) == "note"


def test_all_contains_all_set_paths() -> None:
    store = NoteStore()
    store.set(_PATH, "a")
    store.set(_OTHER, "b")
    result = store.all()
    assert result[str(_PATH)] == "a"
    assert result[str(_OTHER)] == "b"


def test_all_excludes_removed_notes() -> None:
    store = NoteStore()
    store.set(_PATH, "gone")
    store.set(_PATH, "")
    assert str(_PATH) not in store.all()


def test_init_with_existing_dict() -> None:
    store = NoteStore({str(_PATH): "preloaded"})
    assert store.get(_PATH) == "preloaded"


def test_init_default_is_empty() -> None:
    store = NoteStore()
    assert store.all() == {}
