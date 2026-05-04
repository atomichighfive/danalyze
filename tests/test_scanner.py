"""Tests for danalyze.scanner — DiskScanner using InMemoryFilesystem."""

from __future__ import annotations

from pathlib import Path

from danalyze.filesystem import InMemoryFilesystem
from danalyze.models import FileNode, ScanStatus
from danalyze.scanner import DiskScanner


def _root_node(path: str = "/root") -> FileNode:
    return FileNode(path=Path(path), name=Path(path).name, is_dir=True)


# ---------------------------------------------------------------------------
# list_directory
# ---------------------------------------------------------------------------


async def test_list_directory_populates_children() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100, "b.txt": 200}})
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.list_directory(node)
    assert node.scan_status == ScanStatus.LISTED
    assert node.children is not None
    assert len(node.children) == 2


async def test_list_directory_child_sizes_are_none() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100}})
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.list_directory(node)
    assert all(c.size is None for c in node.children)


async def test_list_directory_child_names_correct() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100, "subdir": {}}})
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.list_directory(node)
    names = {c.name for c in node.children}
    assert names == {"a.txt", "subdir"}


async def test_list_directory_dir_child_is_dir() -> None:
    fs = InMemoryFilesystem({"/root": {"subdir": {"child.txt": 10}}})
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.list_directory(node)
    subdir = next(c for c in node.children if c.name == "subdir")
    assert subdir.is_dir is True


async def test_list_directory_file_child_is_not_dir() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100}})
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.list_directory(node)
    assert node.children[0].is_dir is False


async def test_list_directory_cached_on_listed_node() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100}})
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.list_directory(node)
    count_after_first = fs.scandir_call_count
    await scanner.list_directory(node)
    assert fs.scandir_call_count == count_after_first


async def test_list_directory_cached_on_done_node() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100}})
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.scan_sizes(node)  # moves to DONE
    count_after_scan = fs.scandir_call_count
    await scanner.list_directory(node)
    assert fs.scandir_call_count == count_after_scan


async def test_list_directory_permission_denied_sets_error() -> None:
    fs = InMemoryFilesystem({"/root": {"secret": {}}})
    fs.set_permission_denied("/root")
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.list_directory(node)  # must not raise
    assert node.scan_status == ScanStatus.ERROR
    assert node.error is not None
    assert len(node.error) > 0


async def test_list_directory_permission_denied_no_exception_raised() -> None:
    fs = InMemoryFilesystem({"/root": {}})
    fs.set_permission_denied("/root")
    scanner = DiskScanner(fs)
    node = _root_node()
    # This must complete without raising
    await scanner.list_directory(node)


# ---------------------------------------------------------------------------
# scan_sizes
# ---------------------------------------------------------------------------


async def test_scan_sizes_flat_dir_file_sizes_correct() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100, "b.txt": 200}})
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.scan_sizes(node)
    children = {c.name: c for c in node.children}
    assert children["a.txt"].size == 100
    assert children["b.txt"].size == 200


async def test_scan_sizes_flat_dir_total_correct() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100, "b.txt": 200}})
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.scan_sizes(node)
    assert node.size == 300
    assert node.scan_status == ScanStatus.DONE


async def test_scan_sizes_nested_dirs_total_correct() -> None:
    fs = InMemoryFilesystem(
        {
            "/root": {
                "docs": {"report.pdf": 1000, "notes.txt": 500},
                "readme.txt": 200,
            }
        }
    )
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.scan_sizes(node)
    assert node.size == 1700
    assert node.scan_status == ScanStatus.DONE


async def test_scan_sizes_nested_subdir_also_done() -> None:
    fs = InMemoryFilesystem({"/root": {"docs": {"a.txt": 50}}})
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.scan_sizes(node)
    docs = next(c for c in node.children if c.name == "docs")
    assert docs.scan_status == ScanStatus.DONE
    assert docs.size == 50


async def test_scan_sizes_cached_on_done_node() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100}})
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.scan_sizes(node)
    count = fs.scandir_call_count
    await scanner.scan_sizes(node)
    assert fs.scandir_call_count == count


async def test_scan_sizes_on_listed_node_no_extra_scandir() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100, "b.txt": 200}})
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.list_directory(node)
    count_after_list = fs.scandir_call_count
    await scanner.scan_sizes(node)
    assert fs.scandir_call_count == count_after_list


async def test_scan_sizes_permission_denied_child_marked_error() -> None:
    fs = InMemoryFilesystem({"/root": {"open.txt": 100, "secret": {"hidden.txt": 999}}})
    fs.set_permission_denied("/root/secret")
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.scan_sizes(node)
    secret = next(c for c in node.children if c.name == "secret")
    assert secret.scan_status == ScanStatus.ERROR
    assert secret.error is not None


async def test_scan_sizes_permission_denied_parent_sums_others() -> None:
    fs = InMemoryFilesystem({"/root": {"open.txt": 100, "secret": {"hidden.txt": 999}}})
    fs.set_permission_denied("/root/secret")
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.scan_sizes(node)
    assert node.size == 100
    assert node.scan_status == ScanStatus.DONE


async def test_scan_sizes_permission_denied_no_exception_raised() -> None:
    fs = InMemoryFilesystem({"/root": {"secret": {}}})
    fs.set_permission_denied("/root/secret")
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.scan_sizes(node)  # must not raise


# ---------------------------------------------------------------------------
# invalidate
# ---------------------------------------------------------------------------


async def test_invalidate_then_scan_reflects_updated_size() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100}})
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.scan_sizes(node)
    assert node.size == 100

    fs.update_file_size("/root/a.txt", 999)
    scanner.invalidate(Path("/root"))
    await scanner.scan_sizes(node)
    assert node.size == 999


async def test_invalidate_resets_scan_status() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100}})
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.scan_sizes(node)
    assert node.scan_status == ScanStatus.DONE
    scanner.invalidate(Path("/root"))
    assert node.scan_status == ScanStatus.UNSCANNED


async def test_invalidate_unknown_path_is_noop() -> None:
    fs = InMemoryFilesystem({"/root": {}})
    scanner = DiskScanner(fs)
    # Must not raise
    scanner.invalidate(Path("/nonexistent"))


# ---------------------------------------------------------------------------
# on_progress callback
# ---------------------------------------------------------------------------


async def test_on_progress_called_for_each_directory() -> None:
    fs = InMemoryFilesystem(
        {
            "/root": {
                "docs": {"a.txt": 10},
                "downloads": {"b.txt": 20},
            }
        }
    )
    visited: list[str] = []
    scanner = DiskScanner(fs, on_progress=lambda n: visited.append(n.name))
    node = _root_node()
    await scanner.scan_sizes(node)
    # root, docs, and downloads are all dirs that get processed
    assert len(visited) >= 3


async def test_on_progress_called_at_least_once() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100}})
    calls: list[FileNode] = []
    scanner = DiskScanner(fs, on_progress=calls.append)
    node = _root_node()
    await scanner.scan_sizes(node)
    assert len(calls) >= 1


async def test_no_progress_callback_does_not_raise() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100}})
    scanner = DiskScanner(fs)  # no on_progress
    node = _root_node()
    await scanner.scan_sizes(node)  # must not raise


# ---------------------------------------------------------------------------
# Phase 15: symlink handling
# ---------------------------------------------------------------------------


async def test_list_directory_detects_symlink() -> None:
    fs = InMemoryFilesystem({"/root": {}})
    fs.add_symlink("/root/link", target_is_dir=False)
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.list_directory(node)
    link = next(c for c in node.children if c.name == "link")
    assert link.is_symlink is True


async def test_list_directory_symlink_to_dir_has_is_dir_true() -> None:
    fs = InMemoryFilesystem({"/root": {}})
    fs.add_symlink("/root/link", target_is_dir=True)
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.list_directory(node)
    link = next(c for c in node.children if c.name == "link")
    assert link.is_dir is True


async def test_list_directory_symlink_to_file_has_is_dir_false() -> None:
    fs = InMemoryFilesystem({"/root": {}})
    fs.add_symlink("/root/link", target_is_dir=False)
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.list_directory(node)
    link = next(c for c in node.children if c.name == "link")
    assert link.is_dir is False


async def test_list_directory_regular_file_is_not_symlink() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100}})
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.list_directory(node)
    assert node.children[0].is_symlink is False


async def test_scan_sizes_skips_symlink_to_dir() -> None:
    fs = InMemoryFilesystem({"/root": {}})
    fs.add_symlink("/root/link", target_is_dir=True)
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.scan_sizes(node)
    link = next(c for c in node.children if c.name == "link")
    assert link.scan_status == ScanStatus.UNSCANNED


async def test_scan_sizes_skips_broken_symlink() -> None:
    fs = InMemoryFilesystem({"/root": {}})
    fs.add_symlink("/root/link", target_is_dir=False)
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.scan_sizes(node)
    link = next(c for c in node.children if c.name == "link")
    assert link.scan_status == ScanStatus.UNSCANNED


async def test_scan_sizes_symlink_does_not_contribute_to_parent_size() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 100}})
    fs.add_symlink("/root/link", target_is_dir=True)
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.scan_sizes(node)
    assert node.size == 100


async def test_scan_sizes_does_not_crash_on_symlinks() -> None:
    fs = InMemoryFilesystem({"/root": {}})
    fs.add_symlink("/root/link", target_is_dir=True)
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.scan_sizes(node)  # must not raise


async def test_scan_sizes_mixed_files_and_symlinks_sums_only_files() -> None:
    fs = InMemoryFilesystem({"/root": {"a.txt": 300, "b.txt": 200}})
    fs.add_symlink("/root/lnk", target_is_dir=False)
    scanner = DiskScanner(fs)
    node = _root_node()
    await scanner.scan_sizes(node)
    assert node.size == 500


async def test_scan_sizes_on_symlink_root_does_not_set_size() -> None:
    # Simulates pressing r while view_root is a symlink (navigated into it).
    symlink_node = FileNode(
        path=Path("/root/link"),
        name="link",
        is_dir=True,
        is_symlink=True,
        scan_status=ScanStatus.LISTED,
        children=[],
    )
    fs = InMemoryFilesystem({"/root": {}})
    scanner = DiskScanner(fs)
    await scanner.scan_sizes(symlink_node)
    assert symlink_node.size is None
    assert symlink_node.scan_status != ScanStatus.DONE


async def test_scan_sizes_on_symlink_root_after_invalidate_relists() -> None:
    # Simulates invalidate() → scan_sizes() flow when view_root is a symlink.
    # invalidate resets children to None + UNSCANNED; scan_sizes should relist.
    symlink_node = FileNode(
        path=Path("/root"),
        name="root",
        is_dir=True,
        is_symlink=True,
        scan_status=ScanStatus.UNSCANNED,
        children=None,
    )
    fs = InMemoryFilesystem({"/root": {"a.txt": 100}})
    # Make /root itself a symlink in the fake FS so scandir can look it up
    # by injecting children; we use a plain dir here to let list_directory succeed.
    # (In production the symlink target is followed by os.scandir.)
    scanner = DiskScanner(fs)
    await scanner.scan_sizes(symlink_node)
    # list_directory should have been called and children populated
    assert symlink_node.children is not None
    assert symlink_node.size is None
