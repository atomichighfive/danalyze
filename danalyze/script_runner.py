"""Script runner utilities for scripted-mode input parsing.

Phase 1: Input Parsing Utilities.
Pure functions with no I/O.
"""

from __future__ import annotations

import json
from typing import Literal


def parse_script_arg(json_str: str) -> list[str]:
    """Parse a JSON array of strings for scripted-mode inputs.

    Args:
        json_str: A JSON string representing an array of strings.

    Returns:
        A list of strings from the parsed JSON array.

    Raises:
        ValueError: If the JSON is invalid, the top-level value is not a list,
            or any element in the list is not a string.
    """
    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    if not isinstance(parsed, list):
        raise ValueError(f"Expected a JSON array, got {type(parsed).__name__}")

    for i, item in enumerate(parsed):
        if not isinstance(item, str):
            raise ValueError(f"Element at index {i} is not a string: {type(item).__name__}")

    return parsed


def classify_input(s: str) -> tuple[Literal["key", "text"], str]:
    """Classify a scripted input string as either a key or text input.

    Key inputs follow the format "key.<name>" (e.g. "key.enter", "key.down").
    All other strings are treated as text input.

    Args:
        s: The input string to classify.

    Returns:
        A tuple of (category, value) where category is either "key" or "text",
        and value is the extracted name for keys or the original string for text.
    """
    if s.startswith("key."):
        return ("key", s[4:])  # Remove "key." prefix
    return ("text", s)
