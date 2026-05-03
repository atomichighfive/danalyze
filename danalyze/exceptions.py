from __future__ import annotations


class DiskAnalyzerError(Exception):
    """Base exception for all danalyze errors."""


class ScanError(DiskAnalyzerError):
    """Raised when a filesystem scan operation fails fatally."""


class ExportError(DiskAnalyzerError):
    """Raised when a CSV export or import operation fails."""


class NavigationError(DiskAnalyzerError):
    """Raised when an invalid state navigation is attempted."""
