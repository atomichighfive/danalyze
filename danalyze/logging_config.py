from __future__ import annotations

import csv
import io
import logging
import secrets
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path

_async_process_id: ContextVar[str] = ContextVar("async_process_id", default="main")

_HEADER = "timestamp,async_process_id,module,log_line_name,message"


def find_safe_path(base: Path) -> Path:
    """Return base if it does not exist; otherwise count up until a free name is found.

    Args:
        base: Desired file path.

    Returns:
        base if it does not exist, else base.stem + ".1" + base.suffix, etc.
    """
    if not base.exists():
        return base
    stem = base.stem
    suffix = base.suffix
    parent = base.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}.{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


class AsyncProcessFilter(logging.Filter):
    """Inject async_process_id and log_line_name into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Attach async_process_id to the record.

        Args:
            record: The log record to enrich.

        Returns:
            Always True (filter never discards records).
        """
        record.async_process_id = _async_process_id.get()
        if not hasattr(record, "log_line_name"):
            record.log_line_name = ""
        return True


class StructuredCsvFormatter(logging.Formatter):
    """Format log records as a single CSV row.

    Columns: timestamp, async_process_id, module, log_line_name, message.
    Uses stdlib csv.writer so newlines and commas in messages are escaped properly.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a CSV row.

        Args:
            record: The log record to format.

        Returns:
            A single CSV row string (no trailing newline).
        """
        timestamp = datetime.fromtimestamp(record.created, tz=UTC).isoformat()
        async_id = getattr(record, "async_process_id", "main")
        line_name = getattr(record, "log_line_name", "")
        message = record.getMessage()
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="")
        writer.writerow([timestamp, async_id, record.name, line_name, message])
        return buf.getvalue()


class StructuredLogger:
    """Thin wrapper around logging.Logger that requires log_line_name on every call.

    Args:
        logger: The underlying standard library logger.
    """

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def debug(self, name: str, msg: str, *args: object, **kwargs: object) -> None:
        """Log at DEBUG level.

        Args:
            name: Unique log_line_name for this call site.
            msg: Log message (may contain % format placeholders).
            *args: Positional arguments for msg formatting.
            **kwargs: Keyword arguments forwarded to the underlying logger.
        """
        extra = {**kwargs.pop("extra", {}), "log_line_name": name}
        self._logger.debug(msg, *args, extra=extra, **kwargs)

    def info(self, name: str, msg: str, *args: object, **kwargs: object) -> None:
        """Log at INFO level.

        Args:
            name: Unique log_line_name for this call site.
            msg: Log message.
            *args: Positional arguments for msg formatting.
            **kwargs: Keyword arguments forwarded to the underlying logger.
        """
        extra = {**kwargs.pop("extra", {}), "log_line_name": name}
        self._logger.info(msg, *args, extra=extra, **kwargs)

    def warning(self, name: str, msg: str, *args: object, **kwargs: object) -> None:
        """Log at WARNING level.

        Args:
            name: Unique log_line_name for this call site.
            msg: Log message.
            *args: Positional arguments for msg formatting.
            **kwargs: Keyword arguments forwarded to the underlying logger.
        """
        extra = {**kwargs.pop("extra", {}), "log_line_name": name}
        self._logger.warning(msg, *args, extra=extra, **kwargs)

    def error(
        self, name: str, msg: str, *args: object, exc_info: bool = False, **kwargs: object
    ) -> None:
        """Log at ERROR level.

        Args:
            name: Unique log_line_name for this call site.
            msg: Log message.
            *args: Positional arguments for msg formatting.
            exc_info: If True, attach current exception info to the record.
            **kwargs: Keyword arguments forwarded to the underlying logger.
        """
        extra = {**kwargs.pop("extra", {}), "log_line_name": name}
        self._logger.error(msg, *args, exc_info=exc_info, extra=extra, **kwargs)


_global_filter = AsyncProcessFilter()


def get_logger(module_name: str) -> StructuredLogger:
    """Return a StructuredLogger bound to the given module name.

    Args:
        module_name: Typically __name__ of the calling module.

    Returns:
        StructuredLogger wrapping the named standard library logger.
    """
    logger = logging.getLogger(module_name)
    if not any(isinstance(f, AsyncProcessFilter) for f in logger.filters):
        logger.addFilter(_global_filter)
    return StructuredLogger(logger)


def set_async_process_id(process_id: str) -> None:
    """Set the async_process_id context variable for the current async context.

    Args:
        process_id: The ID to set, typically from begin_async_process().

    Side effects:
        Updates the module-level ContextVar for the current context.
    """
    _async_process_id.set(process_id)


def begin_async_process(parent_log: StructuredLogger, process_name: str) -> str:
    """Generate a unique async process ID and log the spawn event.

    Args:
        parent_log: StructuredLogger of the spawning code.
        process_name: Human-readable name prefix for the process.

    Returns:
        Process ID of the form "<process_name>-<8 hex chars>".

    Side effects:
        Emits a DEBUG record on parent_log with log_line_name="async.process.spawn".
    """
    hex_suffix = secrets.token_hex(4)
    process_id = f"{process_name}-{hex_suffix}"
    parent_log.debug("async.process.spawn", "Spawning async process %s", process_id)
    return process_id


def setup_logging(*, debug: bool, log_file: Path | None = None) -> None:
    """Configure the root logger for the application.

    Args:
        debug: If True, attach a DEBUG-level CSV file handler. If False, only
               a WARNING-level stderr handler is added.
        log_file: Path for the log file (only used when debug=True). Defaults to
                  Path("danalyze.log"). A safe non-colliding path is chosen via
                  find_safe_path().

    Side effects:
        Modifies the root logging configuration. Installs AsyncProcessFilter on all
        handlers. Creates the log file and writes the CSV header row when debug=True.
    """
    root = logging.getLogger()
    root.handlers.clear()

    _filter = AsyncProcessFilter()

    if debug:
        safe_path = find_safe_path(log_file or Path("danalyze.log"))
        file_handler = logging.FileHandler(safe_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(StructuredCsvFormatter())
        file_handler.addFilter(_filter)
        root.setLevel(logging.DEBUG)
        root.addHandler(file_handler)
        # Write CSV header
        with safe_path.open("w", encoding="utf-8") as f:
            f.write(_HEADER + "\n")
        # Re-open in append mode
        file_handler.stream.close()
        file_handler.stream = open(safe_path, "a", encoding="utf-8")  # noqa: SIM115
    else:
        stderr_handler = logging.StreamHandler()
        stderr_handler.setLevel(logging.WARNING)
        stderr_handler.addFilter(_filter)
        root.setLevel(logging.WARNING)
        root.addHandler(stderr_handler)
