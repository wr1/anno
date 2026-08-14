"""Tests for mermaid markdown stubs, paths, and editor argv."""

import shutil
import subprocess
from pathlib import Path

from anno.mermaid import (
    STYLES,
    editor_argv,
    ensure_mermaid_file,
    mermaid_path,
    mermaid_template,
    open_mermaid,
)


def test_styles_are_the_v1_set():
    assert STYLES == ("flowchart", "sequence", "state", "class")


def test_flowchart_template_is_fenced_mermaid():
    text = mermaid_template("flowchart", "pipeline")
    assert text.startswith("# pipeline\n")
    assert text == (
        "# pipeline\n"
        "\n"
        "```mermaid\n"
        "flowchart LR\n"
        "  inputs --> group\n"
        "  subgraph group\n"
        '    g_data@{ shape: diff, label: "data" }\n'
        '    g_algo@{ shape: diff, label: "algo" }\n'
        "  end\n"
        "  group --> group2\n"
        "  subgraph group2\n"
        '    h_data@{ shape: diff, label: "data" }\n'
        '    h_algo@{ shape: diff, label: "algo" }\n'
        "  end\n"
        "  group2 --> outputs\n"
        "```\n"
    )


def test_sequence_state_class_templates_use_their_diagram_type():
    assert "sequenceDiagram\n" in mermaid_template("sequence", "auth")
    assert "stateDiagram-v2\n" in mermaid_template("state", "door")
    assert "classDiagram\n" in mermaid_template("class", "model")
    for style in ("sequence", "state", "class"):
        body = mermaid_template(style, "x")
        assert body.startswith("# x\n")
        assert "<!--" not in body
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
    monkeypatch.setattr("anno.mermaid.shutil.which", lambda name: None)
    assert editor_argv(Path("x.md")) == ["hx", "x.md"]
    monkeypatch.delenv("VISUAL")
    assert editor_argv(Path("x.md")) == ["vim", "x.md"]


def test_editor_falls_back_to_gvim_then_code(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr("anno.mermaid.shutil.which", lambda name: "/usr/bin/gvim" if name == "gvim" else None)
    assert editor_argv(Path("x.md")) == ["gvim", "--nofork", "x.md"]
    monkeypatch.setattr("anno.mermaid.shutil.which", lambda name: "/usr/bin/code" if name == "code" else None)
    assert editor_argv(Path("x.md")) == ["code", "--wait", "x.md"]


def test_open_mermaid_creates_edits_and_copies(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VISUAL", "hx")
    launched = []
    copied = []

    def fake_editor(argv):
        launched.append(argv)
        Path(argv[-1]).write_text("# edited\n\n```mermaid\nflowchart TD\n  a --> b\n```\n")

    path = open_mermaid(
        "flowchart",
        "pipeline",
        notes_dir=str(tmp_path),
        run_editor=fake_editor,
        copy_text=copied.append,
    )
    assert path == tmp_path / "pipeline.md"
    assert launched[0][-1] == str(path)
    assert copied == [path.read_text()]
    assert "```mermaid" in path.read_text()


def test_open_mermaid_does_not_overwrite_existing(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VISUAL", "hx")
    existing = tmp_path / "pipeline.md"
    existing.write_text("# keep me\n")
    open_mermaid(
        "sequence",
        "pipeline",
        notes_dir=str(tmp_path),
        run_editor=lambda argv: None,
        copy_text=lambda text: None,
    )
    assert existing.read_text() == "# keep me\n"


def _fence_body(md: str) -> str:
    start = md.index("```mermaid\n") + len("```mermaid\n")
    end = md.index("```", start)
    return md[start:end]


# VS Code mermaid preview (native + bierner) dies silently on these.
# mmdc can still accept some of them — the lint is the previewer contract.
_PREVIEWER_UNSAFE = (
    "direction ",
    "class ",
    "classDef ",
    "stroke:#",
    "-->|0",
    "-->|1",
    "-->|2",
    "-->|3",
    "-->|4",
    "-->|5",
    "-->|6",
    "-->|7",
    "-->|8",
    "-->|9",
)


def test_flowchart_stub_is_previewer_safe():
    body = _fence_body(mermaid_template("flowchart", "x"))
    for needle in _PREVIEWER_UNSAFE:
        assert needle not in body, f"flowchart stub contains previewer-unsafe {needle!r}"


def test_templates_prerender(tmp_path: Path):
    mmdc = shutil.which("mmdc")
    if mmdc is None:
        return
    puppeteer = tmp_path / "puppeteer.json"
    puppeteer.write_text('{"args":["--no-sandbox","--disable-setuid-sandbox"]}')
    for style in STYLES:
        src = tmp_path / f"{style}.mmd"
        src.write_text(_fence_body(mermaid_template(style, style)))
        out = tmp_path / f"{style}.svg"
        result = subprocess.run(
            [mmdc, "-p", str(puppeteer), "-i", str(src), "-o", str(out), "-e", "svg"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 and "No such shape" in (result.stderr or ""):
            # mermaid-cli may ship an older mermaid than the live sidecar (diff, …).
            continue
        assert result.returncode == 0, f"{style} prerender failed:\n{result.stderr}\n{result.stdout}"
        assert out.is_file() and out.stat().st_size > 0
