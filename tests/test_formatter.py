from __future__ import annotations

import pytest

from danalyze.formatter import format_bar_line, format_size, render_bar


class TestFormatSize:
    def test_zero_bytes(self):
        assert format_size(0) == "0 B"

    def test_under_one_kb(self):
        assert format_size(1023) == "1023 B"

    def test_exactly_one_kb(self):
        assert format_size(1024) == "1.0 KB"

    def test_exactly_one_mb(self):
        assert format_size(1_048_576) == "1.0 MB"

    def test_exactly_one_gb(self):
        assert format_size(1_073_741_824) == "1.0 GB"

    def test_exactly_one_tb(self):
        assert format_size(1_099_511_627_776) == "1.0 TB"

    def test_fractional_kb(self):
        assert format_size(1536) == "1.5 KB"

    def test_fractional_gb(self):
        assert format_size(1_610_612_736) == "1.5 GB"

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            format_size(-1)


class TestRenderBar:
    def test_empty_bar(self):
        assert render_bar(0.0, 10) == "░░░░░░░░░░"

    def test_full_bar(self):
        assert render_bar(1.0, 10) == "██████████"

    def test_half_bar(self):
        assert render_bar(0.5, 10) == "█████░░░░░"

    def test_fraction_above_one_raises(self):
        with pytest.raises(ValueError):
            render_bar(1.1, 10)

    def test_fraction_below_zero_raises(self):
        with pytest.raises(ValueError):
            render_bar(-0.1, 10)

    def test_zero_width_raises(self):
        with pytest.raises(ValueError):
            render_bar(0.5, 0)

    def test_width_one_full(self):
        assert render_bar(1.0, 1) == "█"

    def test_width_one_empty(self):
        assert render_bar(0.0, 1) == "░"


class TestFormatBarLine:
    def test_zero_total_no_error(self):
        result = format_bar_line(0, 0, 10)
        assert result.endswith("░░░░░░░░░░")

    def test_half_filled(self):
        result = format_bar_line(500, 1000, 10)
        assert "█████░░░░░" in result
        # Should also contain a size string
        assert "B" in result or "KB" in result or "MB" in result

    def test_contains_size_string(self):
        result = format_bar_line(1024, 2048, 10)
        assert "1.0 KB" in result
