from __future__ import annotations

_UNITS = ["B", "KB", "MB", "GB", "TB"]
_FILLED = "█"
_EMPTY = "░"


def format_size(size_bytes: int) -> str:
    """Format a byte count as a human-readable string.

    Args:
        size_bytes: Non-negative byte count.

    Returns:
        Human-readable string, e.g. "1.5 GB". Bytes are shown without decimals;
        all larger units are shown with one decimal place.

    Raises:
        ValueError: If size_bytes is negative.
    """
    if size_bytes < 0:
        raise ValueError(f"size_bytes must be non-negative, got {size_bytes}")
    value = float(size_bytes)
    for unit in _UNITS[:-1]:
        if value < 1024:
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} {_UNITS[-1]}"


def render_bar(fraction: float, width: int) -> str:
    """Render an ASCII progress bar.

    Args:
        fraction: Fill level in [0.0, 1.0].
        width: Total bar width in characters, must be >= 1.

    Returns:
        String of length `width` composed of filled (█) and empty (░) blocks.

    Raises:
        ValueError: If fraction is outside [0.0, 1.0] or width < 1.
    """
    if fraction < 0.0 or fraction > 1.0:
        raise ValueError(f"fraction must be in [0.0, 1.0], got {fraction}")
    if width < 1:
        raise ValueError(f"width must be >= 1, got {width}")
    filled = round(fraction * width)
    return _FILLED * filled + _EMPTY * (width - filled)


def format_bar_line(size: int, total: int, bar_width: int) -> str:
    """Combine a human-readable size and an ASCII bar into a single display string.

    Args:
        size: Byte count for this entry.
        total: Byte count for the parent (used to compute the bar fraction).
        bar_width: Width of the bar in characters.

    Returns:
        String of the form "<size_human>  <bar>". When total == 0 the bar is fully empty.

    Raises:
        ValueError: If size or total is negative, or bar_width < 1.
    """
    fraction = size / total if total > 0 else 0.0
    size_str = format_size(size).rjust(8)
    return f"{size_str}  {render_bar(fraction, bar_width)}"
