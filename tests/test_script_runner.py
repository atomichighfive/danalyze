"""Tests for script_runner module - Phase 1: Input Parsing Utilities."""

from __future__ import annotations

import pytest

from danalyze.script_runner import classify_input, parse_script_arg


class TestParseScriptArg:
    """Tests for parse_script_arg function."""

    def test_parse_valid_list(self) -> None:
        """Parse a valid JSON array of strings."""
        result = parse_script_arg('["key.enter", "[my note]"]')
        assert result == ["key.enter", "[my note]"]

    def test_parse_empty_list(self) -> None:
        """Parse an empty JSON array."""
        result = parse_script_arg("[]")
        assert result == []

    def test_parse_invalid_json_raises(self) -> None:
        """Invalid JSON raises ValueError."""
        with pytest.raises(ValueError):
            parse_script_arg("not json")

    def test_parse_non_list_raises(self) -> None:
        """Valid JSON but not a list raises ValueError."""
        with pytest.raises(ValueError):
            parse_script_arg('"hello"')

    def test_parse_list_with_non_string_raises(self) -> None:
        """List containing non-string elements raises ValueError."""
        with pytest.raises(ValueError):
            parse_script_arg('["ok", 42]')


class TestClassifyInput:
    """Tests for classify_input function."""

    def test_classify_key_enter(self) -> None:
        """Classify key.enter input."""
        result = classify_input("key.enter")
        assert result == ("key", "enter")

    def test_classify_key_down(self) -> None:
        """Classify key.down input."""
        result = classify_input("key.down")
        assert result == ("key", "down")

    def test_classify_key_r(self) -> None:
        """Classify key.r input."""
        result = classify_input("key.r")
        assert result == ("key", "r")

    def test_classify_text_string(self) -> None:
        """Classify a text string input."""
        result = classify_input("[my note]")
        assert result == ("text", "[my note]")

    def test_classify_single_char(self) -> None:
        """Classify a single character as text."""
        result = classify_input("a")
        assert result == ("text", "a")

    def test_classify_empty_string(self) -> None:
        """Classify empty string as text."""
        result = classify_input("")
        assert result == ("text", "")
