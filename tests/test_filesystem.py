"""Tests for danalyze.filesystem — InMemoryFilesystem and RealFilesystem."""

from __future__ import annotations

from pathlib import Path

import pytest

from danalyze.filesystem import InMemoryFilesystem, RealFilesystem

# ---------------------------------------------------------------------------
# InMemoryFilesystem — scandir
# ---------------------------------------------------------------------------


def test_scandir_returns_single_file_entry() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100}})
    entries = list(fs.scandir(Path("/root")))
    assert len(entries) == 1
    assert entries[0].name == "a.txt"


def test_scandir_file_entry_is_not_dir() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100}})
    entries = list(fs.scandir(Path("/root")))
    assert entries[0].is_dir() is False


def test_scandir_file_entry_stat_size() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100}})
    entries = list(fs.scandir(Path("/root")))
    assert entries[0].stat().st_size == 100


def test_scandir_dir_entry_is_dir() -> None:
    fs = InMemoryFilesystem({"/root": {"subdir": {"child.txt": 50}}})
    entries = list(fs.scandir(Path("/root")))
    assert len(entries) == 1
    assert entries[0].name == "subdir"
    assert entries[0].is_dir() is True


def test_scandir_multiple_children() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 10, "b.txt": 20, "c.txt": 30}})
    entries = list(fs.scandir(Path("/root")))
    names = {e.name for e in entries}
    assert names == {"a.txt", "b.txt", "c.txt"}


# ---------------------------------------------------------------------------
# InMemoryFilesystem — stat
# ---------------------------------------------------------------------------


def test_stat_file_returns_correct_size() -> None:
    fs = InMemoryFilesystem({"/root": {"file.txt": 512}})
    result = fs.stat(Path("/root/file.txt"))
    assert result.st_size == 512


def test_stat_dir_returns_zero_size() -> None:
    fs = InMemoryFilesystem({"/root": {"subdir": {}}})
    result = fs.stat(Path("/root/subdir"))
    assert result.st_size == 0


# ---------------------------------------------------------------------------
# InMemoryFilesystem — disk_usage
# ---------------------------------------------------------------------------


def test_disk_usage_flat_dir() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100, "b.txt": 200}})
    usage = fs.disk_usage(Path("/root"))
    assert usage.total == 300


def test_disk_usage_nested_dirs() -> None:
    fs = InMemoryFilesystem(
        {
            "/root": {
                "docs": {"report.pdf": 1000, "notes.txt": 500},
                "readme.txt": 200,
            }
        }
    )
    usage = fs.disk_usage(Path("/root"))
    assert usage.total == 1700


def test_disk_usage_used_equals_total() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 400}})
    usage = fs.disk_usage(Path("/root"))
    assert usage.used == usage.total


def test_disk_usage_free_is_zero() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 400}})
    usage = fs.disk_usage(Path("/root"))
    assert usage.free == 0


# ---------------------------------------------------------------------------
# InMemoryFilesystem — is_mount
# ---------------------------------------------------------------------------


def test_is_mount_true_for_top_level() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100}})
    assert fs.is_mount(Path("/root")) is True


def test_is_mount_false_for_subdirectory() -> None:
    fs = InMemoryFilesystem({"/root": {"subdir": {"file.txt": 10}}})
    assert fs.is_mount(Path("/root/subdir")) is False


def test_is_mount_false_for_file() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100}})
    assert fs.is_mount(Path("/root/a.txt")) is False


# ---------------------------------------------------------------------------
# InMemoryFilesystem — permission denied
# ---------------------------------------------------------------------------


def test_set_permission_denied_scandir_raises() -> None:
    fs = InMemoryFilesystem({"/root": {"secret": {"file.txt": 10}}})
    fs.set_permission_denied("/root/secret")
    with pytest.raises(PermissionError):
        list(fs.scandir(Path("/root/secret")))


def test_set_permission_denied_stat_raises() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100}})
    fs.set_permission_denied("/root/a.txt")
    with pytest.raises(PermissionError):
        fs.stat(Path("/root/a.txt"))


def test_permission_denied_does_not_affect_siblings() -> None:
    fs = InMemoryFilesystem({"/root": {"secret": {}, "open.txt": 50}})
    fs.set_permission_denied("/root/secret")
    entries = list(fs.scandir(Path("/root")))
    names = {e.name for e in entries}
    assert "open.txt" in names


# ---------------------------------------------------------------------------
# InMemoryFilesystem — update_file_size
# ---------------------------------------------------------------------------


def test_update_file_size_reflected_in_stat() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100}})
    fs.update_file_size("/root/a.txt", 999)
    result = fs.stat(Path("/root/a.txt"))
    assert result.st_size == 999


def test_update_file_size_reflected_in_scandir_stat() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100}})
    fs.update_file_size("/root/a.txt", 777)
    entries = list(fs.scandir(Path("/root")))
    assert entries[0].stat().st_size == 777


# ---------------------------------------------------------------------------
# InMemoryFilesystem — scandir_call_count
# ---------------------------------------------------------------------------


def test_scandir_call_count_starts_at_zero() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 10}})
    assert fs.scandir_call_count == 0


def test_scandir_call_count_increments() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 10}})
    list(fs.scandir(Path("/root")))
    assert fs.scandir_call_count == 1
    list(fs.scandir(Path("/root")))
    assert fs.scandir_call_count == 2


# ---------------------------------------------------------------------------
# RealFilesystem — smoke test (hits real filesystem)
# ---------------------------------------------------------------------------


def test_real_filesystem_scandir_returns_entries(tmp_path: Path) -> None:
    (tmp_path / "file.txt").write_text("hello")
    fs = RealFilesystem()
    entries = list(fs.scandir(tmp_path))
    assert any(e.name == "file.txt" for e in entries)


def test_real_filesystem_stat_returns_size(tmp_path: Path) -> None:
    p = tmp_path / "file.txt"
    p.write_bytes(b"x" * 128)
    fs = RealFilesystem()
    assert fs.stat(p).st_size == 128


def test_real_filesystem_disk_usage_returns_namedtuple(tmp_path: Path) -> None:
    fs = RealFilesystem()
    usage = fs.disk_usage(tmp_path)
    assert usage.total > 0
    assert usage.used >= 0
    assert usage.free >= 0


def test_real_filesystem_is_mount_returns_bool(tmp_path: Path) -> None:
    fs = RealFilesystem()
    result = fs.is_mount(tmp_path)
    assert isinstance(result, bool)
