from __future__ import annotations

from pathlib import Path

from danalyze.exceptions import DiskAnalyzerError, ExportError, NavigationError, ScanError
from danalyze.models import AppMode, DriveInfo, FileNode, FileTree, ScanStatus


def make_node(
    path: str, *, is_dir: bool = True, children: list[FileNode] | None = None
) -> FileNode:
    return FileNode(path=Path(path), name=Path(path).name, is_dir=is_dir, children=children)


class TestExceptions:
    def test_scan_error_is_disk_analyzer_error(self):
        exc = ScanError("test")
        assert isinstance(exc, DiskAnalyzerError)

    def test_export_error_is_disk_analyzer_error(self):
        exc = ExportError("test")
        assert isinstance(exc, DiskAnalyzerError)

    def test_navigation_error_is_disk_analyzer_error(self):
        exc = NavigationError("test")
        assert isinstance(exc, DiskAnalyzerError)


class TestFileNodeDefaults:
    def test_default_scan_status_is_unscanned(self):
        node = make_node("/home")
        assert node.scan_status == ScanStatus.UNSCANNED

    def test_default_size_is_none(self):
        node = make_node("/home")
        assert node.size is None

    def test_default_children_is_none(self):
        node = make_node("/home")
        assert node.children is None

    def test_default_error_is_none(self):
        node = make_node("/home")
        assert node.error is None

    def test_error_node_stores_scan_status_and_message(self):
        node = FileNode(
            path=Path("/private"),
            name="private",
            is_dir=True,
            scan_status=ScanStatus.ERROR,
            error="permission denied",
        )
        assert node.scan_status == ScanStatus.ERROR
        assert node.error == "permission denied"


class TestFileTree:
    def _build_tree(self) -> tuple[FileNode, FileNode, FileNode]:
        child_file = FileNode(path=Path("/root/a.txt"), name="a.txt", is_dir=False)
        child_dir = FileNode(
            path=Path("/root/docs"), name="docs", is_dir=True, children=[child_file]
        )
        root = FileNode(path=Path("/root"), name="root", is_dir=True, children=[child_dir])
        return root, child_dir, child_file

    def test_find_by_path_root(self):
        root, _, _ = self._build_tree()
        tree = FileTree(root=root)
        assert tree.find_by_path(Path("/root")) is root

    def test_find_by_path_nested_dir(self):
        root, child_dir, _ = self._build_tree()
        tree = FileTree(root=root)
        assert tree.find_by_path(Path("/root/docs")) is child_dir

    def test_find_by_path_nested_file(self):
        root, _, child_file = self._build_tree()
        tree = FileTree(root=root)
        assert tree.find_by_path(Path("/root/a.txt")) is child_file

    def test_find_by_path_missing_returns_none(self):
        root, _, _ = self._build_tree()
        tree = FileTree(root=root)
        assert tree.find_by_path(Path("/root/nonexistent")) is None

    def test_ancestors_of_root_is_empty(self):
        root, _, _ = self._build_tree()
        tree = FileTree(root=root)
        assert tree.ancestors(root) == []

    def test_ancestors_of_direct_child(self):
        root, child_dir, _ = self._build_tree()
        tree = FileTree(root=root)
        assert tree.ancestors(child_dir) == [root]

    def test_ancestors_of_grandchild(self):
        root, child_dir, child_file = self._build_tree()
        tree = FileTree(root=root)
        assert tree.ancestors(child_file) == [root, child_dir]

    def test_ancestors_excludes_node_itself(self):
        root, _, child_file = self._build_tree()
        tree = FileTree(root=root)
        ancestors = tree.ancestors(child_file)
        assert child_file not in ancestors


class TestDriveInfo:
    def test_valid_drive_info(self):
        info = DriveInfo(
            device="/dev/sda1",
            total=500_000_000_000,
            used=300_000_000_000,
            free=200_000_000_000,
            mount_point=Path("/"),
        )
        assert info.free + info.used <= info.total

    def test_mount_point_stored(self):
        info = DriveInfo(
            device="/dev/sda1",
            total=1000,
            used=400,
            free=600,
            mount_point=Path("/mnt"),
        )
        assert info.mount_point == Path("/mnt")


class TestEnums:
    def test_scan_status_values_are_lowercase(self):
        for member in ScanStatus:
            assert member.value == member.value.lower()

    def test_app_mode_values_are_lowercase(self):
        for member in AppMode:
            assert member.value == member.value.lower()

    def test_scan_status_has_expected_members(self):
        names = {m.name for m in ScanStatus}
        assert names == {"UNSCANNED", "LISTED", "SCANNING", "DONE", "ERROR"}

    def test_app_mode_has_expected_members(self):
        names = {m.name for m in AppMode}
        assert names == {"BROWSE", "NOTE_INPUT", "QUIT_PROMPT", "SAVE_PROMPT"}
