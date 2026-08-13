"""Tests for mermaid markdown stubs, paths, and editor argv."""

from pathlib import Path

from anno.mermaid import (
    STYLES,
    editor_argv,
    ensure_mermaid_file,
    mermaid_path,
    mermaid_template,
)


def test_styles_are_the_v1_set():
    assert STYLES == ("flowchart", "sequence", "state", "class")


def test_flowchart_template_is_fenced_mermaid():
    text = mermaid_template("flowchart", "pipeline")
    assert text.startswith("# pipeline\n")
    assert text == ("# pipeline\n\n```mermaid\nflowchart TD\n  start[Start] --> done[Done]\n```\n")


def test_sequence_state_class_templates_use_their_diagram_type():
    assert "sequenceDiagram\n" in mermaid_template("sequence", "auth")
    assert "stateDiagram-v2\n" in mermaid_template("state", "door")
    assert "classDiagram\n" in mermaid_template("class", "model")
    for style in ("sequence", "state", "class"):
        body = mermaid_template(style, "x")
        assert body.startswith("# x\n")
        assert body.count("```") == 2


def test_unknown_style_raises():
    try:
        mermaid_template("mindmap", "x")
    except ValueError as exc:
        assert "flowchart" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_named_path_is_stem_md(tmp_path: Path):
    assert mermaid_path(tmp_path, "sequence", "Auth Flow.md") == tmp_path / "Auth Flow.md"


def test_scratch_path_uses_style_and_timestamp(tmp_path: Path):
    path = mermaid_path(tmp_path, "flowchart", "")
    assert path.parent == tmp_path
    assert path.name.startswith("flowchart_")
    assert path.suffix == ".md"


def test_ensure_creates_only_when_missing(tmp_path: Path):
    path = tmp_path / "pipeline.md"
    assert ensure_mermaid_file(path, "flowchart", "pipeline") is True
    original = path.read_text()
    path.write_text("# hand-edited\n")
    assert ensure_mermaid_file(path, "flowchart", "pipeline") is False
    assert path.read_text() == "# hand-edited\n"
    assert "```mermaid" in original


def test_editor_prefers_visual_then_editor(monkeypatch):
    monkeypatch.setenv("VISUAL", "hx")
    monkeypatch.setenv("EDITOR", "vim")
    assert editor_argv(Path("x.md")) == ["hx", "x.md"]
    monkeypatch.delenv("VISUAL")
    assert editor_argv(Path("x.md")) == ["vim", "x.md"]


def test_editor_falls_back_to_gvim(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr("anno.mermaid.shutil.which", lambda name: "/usr/bin/gvim" if name == "gvim" else None)
    assert editor_argv(Path("x.md")) == ["gvim", "--nofork", "x.md"]
