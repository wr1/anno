"""Tests for anno list file collection."""

import os
from pathlib import Path

from anno.listing import listed_files


def test_listed_files_missing_dir_is_empty(tmp_path: Path):
    assert listed_files(tmp_path / "missing", "*.md") == []


def test_listed_files_mermaid_md_newest_first(tmp_path: Path):
    older = tmp_path / "old.md"
    newer = tmp_path / "new.md"
    older.write_text("# old\n")
    newer.write_text("# new\n")
    (tmp_path / "skip.txt").write_text("nope")
    os.utime(older, (1_000_000, 1_000_000))
    os.utime(newer, (2_000_000, 2_000_000))
    names = [p.name for p in listed_files(tmp_path, "*.md")]
    assert names == ["new.md", "old.md"]
    assert "skip.txt" not in names


def test_open_invocation_is_sub_and_stem():
    from anno.listing import open_invocation

    assert open_invocation("ink", Path("notes/draw/myfigure.svg")) == "ink myfigure"
    assert open_invocation("mind", Path("roadmap.minder")) == "mind roadmap"
    assert open_invocation("mermaid", Path("notes/mermaid/pipeline.md")) == "mermaid pipeline"


def test_collect_entries_sorted_by_mtime_mixed_types(tmp_path: Path):
    from anno.listing import collect_entries

    draw = tmp_path / "draw"
    mind = tmp_path / "mind"
    mer = tmp_path / "mermaid"
    for d in (draw, mind, mer):
        d.mkdir()
    ink = draw / "fig.svg"
    minder = mind / "map.minder"
    md = mer / "pipe.md"
    ink.write_text("<svg/>")
    minder.write_text("x")
    md.write_text("# p\n")
    os.utime(minder, (1_000_000, 1_000_000))
    os.utime(md, (2_000_000, 2_000_000))
    os.utime(ink, (3_000_000, 3_000_000))
    entries = collect_entries(str(draw), str(mind), str(mer))
    assert [e.sub for e in entries] == ["ink", "mermaid", "mind"]
    assert [e.open_cmd for e in entries] == ["ink fig", "mermaid pipe", "mind map"]


def test_type_style_differs_by_sub():
    from anno.listing import type_style

    assert type_style("ink") != type_style("mind")
    assert type_style("mind") != type_style("mermaid")
    assert type_style("ink") != type_style("mermaid")
