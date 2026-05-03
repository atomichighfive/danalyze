from __future__ import annotations

import csv
import io
import logging
from pathlib import Path

import pytest

from danalyze.logging_config import (
    StructuredCsvFormatter,
    begin_async_process,
    find_safe_path,
    get_logger,
    set_async_process_id,
    setup_logging,
)


class TestFindSafePath:
    def test_returns_base_when_absent(self, tmp_path: Path):
        target = tmp_path / "x.log"
        assert find_safe_path(target) == target

    def test_counts_up_when_base_exists(self, tmp_path: Path):
        base = tmp_path / "x.log"
        base.touch()
        result = find_safe_path(base)
        assert result == tmp_path / "x.1.log"

    def test_counts_up_past_one(self, tmp_path: Path):
        base = tmp_path / "x.log"
        base.touch()
        (tmp_path / "x.1.log").touch()
        result = find_safe_path(base)
        assert result == tmp_path / "x.2.log"


class TestStructuredLogger:
    def test_debug_sets_log_line_name(self, caplog):
        log = get_logger("test.module")
        with caplog.at_level(logging.DEBUG, logger="test.module"):
            log.debug("a.b.c", "hello")
        assert any(getattr(r, "log_line_name", None) == "a.b.c" for r in caplog.records)

    def test_missing_name_raises_type_error(self):
        log = get_logger("test.module2")
        with pytest.raises(TypeError):
            log.debug("hello")  # type: ignore[call-arg]

    def test_error_with_exc_info(self, caplog):
        log = get_logger("test.exc_module")
        with caplog.at_level(logging.ERROR, logger="test.exc_module"):
            try:
                raise ValueError("boom")
            except ValueError:
                log.error("a.b.err", "oops", exc_info=True)
        record = caplog.records[-1]
        assert record.exc_info is not None
        assert record.exc_info[0] is ValueError


class TestAsyncProcessId:
    def test_default_async_process_id_is_main(self, caplog):
        log = get_logger("test.default_proc")
        with caplog.at_level(logging.DEBUG, logger="test.default_proc"):
            log.debug("test.default", "hello")
        assert caplog.records[-1].async_process_id == "main"

    def test_set_async_process_id(self, caplog):
        set_async_process_id("proc-1")
        log = get_logger("test.proc_module")
        with caplog.at_level(logging.DEBUG, logger="test.proc_module"):
            log.debug("test.proc", "msg")
        assert caplog.records[-1].async_process_id == "proc-1"

    def test_begin_async_process_returns_prefixed_id(self, caplog):
        log = get_logger("test.begin_proc")
        with caplog.at_level(logging.DEBUG, logger="test.begin_proc"):
            proc_id = begin_async_process(log, "scan")
        assert proc_id.startswith("scan-")
        assert len(proc_id) == len("scan-") + 8

    def test_begin_async_process_emits_spawn_record(self, caplog):
        log = get_logger("test.spawn_proc")
        with caplog.at_level(logging.DEBUG, logger="test.spawn_proc"):
            begin_async_process(log, "scan")
        names = [getattr(r, "log_line_name", None) for r in caplog.records]
        assert "async.process.spawn" in names


class TestStructuredCsvFormatter:
    def test_single_line_with_special_chars(self):
        formatter = StructuredCsvFormatter()
        record = logging.LogRecord(
            name="danalyze.test",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="line1\nline2, and more",
            args=(),
            exc_info=None,
        )
        record.log_line_name = "test.event"
        record.async_process_id = "proc-abc"
        output = formatter.format(record)
        rows = list(csv.reader(io.StringIO(output)))
        assert len(rows) == 1
        assert len(rows[0]) == 5

    def test_fields_order(self):
        formatter = StructuredCsvFormatter()
        record = logging.LogRecord(
            name="danalyze.test",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="test message",
            args=(),
            exc_info=None,
        )
        record.log_line_name = "test.order"
        record.async_process_id = "main"
        output = formatter.format(record)
        row = list(csv.reader(io.StringIO(output)))[0]
        # columns: timestamp, async_process_id, module, log_line_name, message
        assert row[1] == "main"
        assert row[3] == "test.order"
        assert row[4] == "test message"


class TestSetupLogging:
    def test_debug_creates_log_file_with_header(self, tmp_path: Path):
        log_file = tmp_path / "test.log"
        setup_logging(debug=True, log_file=log_file)
        log = get_logger("test.setup")
        log.debug("test.setup.event", "first message")
        # Flush handlers
        for handler in logging.getLogger().handlers:
            handler.flush()
        content = log_file.read_text()
        lines = content.strip().splitlines()
        assert lines[0] == "timestamp,async_process_id,module,log_line_name,message"
        assert len(lines) >= 2
