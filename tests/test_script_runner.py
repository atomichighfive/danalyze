"""Tests for script_runner module."""

from __future__ import annotations

import pytest

from danalyze.script_runner import classify_input, parse_script_arg


def test_parse_valid_list() -> None:
    result = parse_script_arg('["key.enter", "[my note]"]')
    assert result == ["key.enter", "[my note]"]


def test_parse_empty_list() -> None:
    result = parse_script_arg("[]")
    assert result == []


def test_parse_invalid_json_raises() -> None:
    with pytest.raises(ValueError):
        parse_script_arg("not json")


def test_parse_non_list_raises() -> None:
    with pytest.raises(ValueError):
        parse_script_arg('"hello"')


def test_parse_list_with_non_string_raises() -> None:
    with pytest.raises(ValueError):
        parse_script_arg('["ok", 42]')


def test_classify_key_enter() -> None:
    result = classify_input("key.enter")
    assert result == ("key", "enter")


def test_classify_key_down() -> None:
    result = classify_input("key.down")
    assert result == ("key", "down")


def test_classify_key_r() -> None:
    result = classify_input("key.r")
    assert result == ("key", "r")


def test_classify_text_string() -> None:
    result = classify_input("[my note]")
    assert result == ("text", "[my note]")


def test_classify_single_char() -> None:
    result = classify_input("a")
    assert result == ("text", "a")


def test_classify_empty_string() -> None:
    result = classify_input("")
    assert result == ("text", "")
