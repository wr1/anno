"""Minder 2.0 `.minder` archive (gzip tar + map.xml). 1.x XML is refused."""

import gzip
import io
import os
import tarfile
from pathlib import Path

import pytest

from anno.mind.format import (
    MAP_XML_NAME,
    is_minder2_archive,
    read_map_xml,
    require_minder_archive,
    write_minder_archive,
)
from anno.mind.process import minder_export_markdown, minder_launch_gui
from anno.mind.styles import make_minder_file
from anno.mind.templates import seed_minder
from anno.mind.tree import MindNode, tree_to_minder_xml

MAP_XML = (
    '<?xml version="1.0"?>\n'
    '<minder version="2.0.3" parent-etag="0" etag="0">\n'
    '  <theme name="dark" label="Dark" index="1"/>\n'
    "  <nodes/>\n"
    "</minder>\n"
)
V1_XML = '<?xml version="1.0"?>\n<minder version="1.16.2"/>\n'


def test_write_archive_is_gzip_with_map_xml(tmp_path: Path) -> None:
    path = tmp_path / "map.minder"
    write_minder_archive(path, MAP_XML)
    assert is_minder2_archive(path)
    assert read_map_xml(path) == MAP_XML


def test_write_creates_parent_dirs(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "map.minder"
    write_minder_archive(path, MAP_XML)
    assert path.is_file()
    assert read_map_xml(path) == MAP_XML


def test_write_leaves_no_tmp_on_replace_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a, **_k):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", boom)
    path = tmp_path / "x.minder"
    with pytest.raises(OSError, match="replace failed"):
        write_minder_archive(path, MAP_XML)
    assert not path.exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_is_minder2_archive_false_for_missing_and_xml(tmp_path: Path) -> None:
    missing = tmp_path / "gone.minder"
    xml_path = tmp_path / "old.minder"
    xml_path.write_text(V1_XML)
    assert is_minder2_archive(missing) is False
    assert is_minder2_archive(xml_path) is False


def test_require_and_read_refuse_v1_xml(tmp_path: Path) -> None:
    path = tmp_path / "old.minder"
    path.write_text(V1_XML)
    with pytest.raises(ValueError, match="1.x XML"):
        require_minder_archive(path)
    with pytest.raises(ValueError, match="1.x XML"):
        read_map_xml(path)


def test_require_refuses_missing_and_non_archive(tmp_path: Path) -> None:
    missing = tmp_path / "gone.minder"
    junk = tmp_path / "junk.minder"
    junk.write_bytes(b"not gzip and not xml")
    with pytest.raises(ValueError, match="not a file"):
        require_minder_archive(missing)
    with pytest.raises(ValueError, match="not a Minder 2.0 archive"):
        require_minder_archive(junk)


def test_read_refuses_gzip_without_map_xml(tmp_path: Path) -> None:
    path = tmp_path / "empty.minder"
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w") as tar:
        info = tarfile.TarInfo(name="other.xml")
        payload = b"<other/>"
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    path.write_bytes(gzip.compress(tar_buf.getvalue()))
    with pytest.raises(ValueError, match="no map.xml"):
        read_map_xml(path)


def test_read_refuses_directory_map_xml_member(tmp_path: Path) -> None:
    path = tmp_path / "dirmember.minder"
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w") as tar:
        info = tarfile.TarInfo(name=MAP_XML_NAME)
        info.type = tarfile.DIRTYPE
        tar.addfile(info)
    path.write_bytes(gzip.compress(tar_buf.getvalue()))
    with pytest.raises(ValueError, match="could not extract"):
        read_map_xml(path)


def test_read_refuses_corrupt_gzip_tar(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.minder"
    path.write_bytes(gzip.compress(b"not a tar"))
    with pytest.raises(ValueError, match="not a Minder 2.0 archive"):
        read_map_xml(path)


def test_seed_and_empty_file_are_archives(tmp_path: Path) -> None:
    seeded = tmp_path / "seeded.minder"
    seed_minder(seeded, root_title="roadmap")
    assert is_minder2_archive(seeded)
    xml = read_map_xml(seeded)
    assert '<text data="roadmap"/>' in xml
    assert 'version="2.0.3"' in xml

    empty = tmp_path / "empty.minder"
    make_minder_file(empty)
    assert is_minder2_archive(empty)
    assert "<nodes/>" in read_map_xml(empty)


def test_tree_xml_roundtrip_inside_archive(tmp_path: Path) -> None:
    tree = MindNode(title="root", children=[MindNode(title="child", note="note")])
    path = tmp_path / "tree.minder"
    write_minder_archive(path, tree_to_minder_xml(tree))
    xml = read_map_xml(path)
    assert '<text data="root"/>' in xml
    assert '<text data="child"/>' in xml
    assert "<nodenote>note</nodenote>" in xml


def test_export_and_launch_refuse_v1_xml(tmp_path: Path) -> None:
    path = tmp_path / "old.minder"
    path.write_text(V1_XML)
    with pytest.raises(SystemExit, match="1.x XML"):
        minder_export_markdown(path, tmp_path / "out.md")
    with pytest.raises(SystemExit, match="1.x XML"):
        minder_launch_gui(path)
