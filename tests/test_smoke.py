"""Minor smoke: every CLI leaf parses, and each workflow's path runs without a GUI."""

from __future__ import annotations

import ast
import json
import os
import struct
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen

from anno.cli import app

# Frozen so a new leaf fails here until a smoke step covers it.
EXPECTED_LEAVES = frozenset(
    {
        ("cam",),
        ("list",),
        ("log",),
        ("ink", "open"),
        ("ink", "fig"),
        ("ink", "screen"),
        ("mind", "open"),
        ("mind", "import"),
        ("mermaid", "flowchart"),
        ("mermaid", "sequence"),
        ("mermaid", "state"),
        ("mermaid", "class"),
        ("d2", "open"),
        ("d2", "check"),
        ("para", "new"),
        ("para", "open"),
    }
)

_SRC = Path(__file__).resolve().parent.parent / "src" / "anno"


def _leaves() -> list[tuple[str, ...]]:
    leaves = [(c.name,) for c in app.commands]
    for group in app.subgroups:
        leaves.extend((group.name, c.name) for c in group.commands)
    return leaves


def _run_anno(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", "from anno import main; main()", *args],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )


def _tiny_png(path: Path) -> None:
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x00IHDR" + struct.pack(">II", 1, 1))


def _ping_live(start_server, path: Path, title: str) -> None:
    httpd, port, done = start_server(path)
    try:
        page = urlopen(f"http://127.0.0.1:{port}/", timeout=2).read().decode()
        assert title in page
        assert "textarea" in page
        urlopen(Request(f"http://127.0.0.1:{port}/done", data=b"", method="POST"), timeout=2)
        assert done.wait(timeout=2)
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_smoke_covers_every_cli_leaf():
    discovered = frozenset(_leaves())
    assert discovered == EXPECTED_LEAVES, (
        f"CLI leaves changed.\nmissing from smoke: {sorted(discovered - EXPECTED_LEAVES)}\n"
        f"extra in smoke: {sorted(EXPECTED_LEAVES - discovered)}"
    )


def test_smoke_every_leaf_help_and_json():
    root = _run_anno("--help")
    assert root.returncode == 0, root.stderr
    assert "ink" in root.stdout and "mind" in root.stdout
    js = _run_anno("-j")
    assert js.returncode == 0, js.stderr
    assert "anno" in js.stdout
    for parts in sorted(_leaves()):
        result = _run_anno(*parts, "--help")
        assert result.returncode == 0, (parts, result.stderr or result.stdout)


def test_all_workflows_smoke(tmp_path: Path, monkeypatch, capsys):
    log_file = tmp_path / "log.jsonl"
    monkeypatch.setattr("anno.log_util.DEFAULT_LOG_FILE", log_file)
    _smoke_ink(tmp_path, monkeypatch)
    _smoke_mind(tmp_path, monkeypatch)
    _smoke_mermaid(tmp_path, monkeypatch)
    _smoke_d2(tmp_path, monkeypatch)
    _smoke_cam(tmp_path, monkeypatch)
    _smoke_para(tmp_path, monkeypatch)
    _smoke_list_log(tmp_path, log_file)
    capsys.readouterr()


def _smoke_ink(tmp_path: Path, monkeypatch) -> None:
    from anno import ink

    opened: list[Path] = []

    def fake_run(svg: Path) -> None:
        opened.append(svg)
        assert svg.is_file()
        text = svg.read_text()
        assert ink.SODIPODI_NS in text
        assert "sodipodi-0.0.dtd" not in text

    monkeypatch.setattr(ink, "_run_inkscape_and_export", fake_run)
    draw = tmp_path / "draw"
    ink.cmd_ink_open("smoke", notes_dir=str(draw))
    assert (draw / "smoke.svg").is_file()

    png = tmp_path / "dot.png"
    _tiny_png(png)
    ink.cmd_ink_fig(str(png), notes_dir=str(draw))
    assert any("xlink:href" in p.read_text() for p in draw.glob("dot_*.svg"))

    shots = tmp_path / "shots"
    shots.mkdir()
    _tiny_png(shots / "latest.png")
    ink.cmd_ink_screen(notes_dir=str(draw / "from_screen"), screenshots_dir=str(shots))
    assert list((draw / "from_screen").glob("*.svg"))
    assert len(opened) == 3


def _smoke_mind(tmp_path: Path, monkeypatch) -> None:
    from anno.mind.folder import folder_to_tree, tree_to_folder
    from anno.mind.sync import cmd_mind_import, cmd_mind_open, resolve_open_target
    from anno.mind.templates import load_template, seed_minder

    mind_dir = tmp_path / "mind"
    notes_root = tmp_path / "notes"
    plans_dir = tmp_path / "plans"
    mind_dir.mkdir()
    notes_root.mkdir()
    plans_dir.mkdir()

    monkeypatch.setattr("anno.mind.sync.refuse_if_minder_running", lambda force: None)
    launched: list[object] = []
    monkeypatch.setattr(
        "anno.mind.sync.run_minder",
        lambda *a, **k: launched.append((a, k)),
    )
    cmd_mind_open(
        "smoke",
        mind_dir=str(mind_dir),
        notes_root=str(notes_root),
        plans_dir=str(plans_dir),
        no_clipboard=True,
    )
    minder = mind_dir / "smoke.minder"
    assert minder.is_file()
    assert launched

    tree = load_template("software", root_title="software")
    folder = notes_root / "software"
    tree_to_folder(tree, folder, fs_depth=3)
    back, _ = folder_to_tree(folder, 3)
    assert "Aim" in [c.title for c in back.children]
    mode, target = resolve_open_target("software", mind_dir, notes_root, plans_dir)
    assert mode == "folder" and target == folder.resolve()

    def fake_export(minder_file: Path, md_file: Path) -> None:
        md_file.write_text("# imported\n\n- Aim\n- Success\n")

    monkeypatch.setattr("anno.mind.sync.minder_export_markdown", fake_export)
    imported = tmp_path / "imported"
    seed_minder(minder, root_title="smoke")
    cmd_mind_import(str(minder), str(imported), no_clipboard=True)
    assert (imported / "Aim").is_dir()


def _smoke_mermaid(tmp_path: Path, monkeypatch) -> None:
    from anno.mermaid import STYLES, open_mermaid
    from anno.mermaid_live import start_live_server

    monkeypatch.setenv("VISUAL", "true")
    mer = tmp_path / "mermaid"
    for style in STYLES:
        path = open_mermaid(
            style,
            f"smoke-{style}",
            notes_dir=str(mer),
            run_editor=lambda argv: None,
            copy_text=lambda text: None,
        )
        assert path.is_file()
        assert "```mermaid" in path.read_text()
    _ping_live(start_live_server, mer / "smoke-flowchart.md", "anno mermaid")


def _smoke_d2(tmp_path: Path, monkeypatch) -> None:
    from anno.d2 import check_d2, open_d2
    from anno.d2_live import start_live_server

    monkeypatch.setenv("VISUAL", "true")
    d2dir = tmp_path / "d2"
    path = open_d2(
        "smoke",
        notes_dir=str(d2dir),
        no_check=True,
        run_editor=lambda argv: None,
        copy_text=lambda text: None,
    )
    assert path.is_file()
    assert "direction: right" in path.read_text()
    result = check_d2("smoke", notes_dir=str(d2dir), validate=lambda src: (True, "ok"))
    assert result.ok and result.exit_code == 0
    _ping_live(start_live_server, path, "anno d2")


def _smoke_cam(tmp_path: Path, monkeypatch) -> None:
    from anno.cam import cmd_cam

    monkeypatch.setattr("anno.cam.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("anno.cam.copy_png_to_clipboard", lambda p: None)

    def fake_run(argv, **kwargs):
        exe = Path(argv[0]).name
        if exe == "ffplay":
            return subprocess.CompletedProcess(argv, 0)
        if exe == "ffmpeg":
            Path(argv[-1]).write_bytes(b"\xff\xd8\xff\xd9")
            return subprocess.CompletedProcess(argv, 0)
        if exe == "convert":
            _tiny_png(Path(argv[-1]))
            return subprocess.CompletedProcess(argv, 0)
        raise AssertionError(argv)

    monkeypatch.setattr("anno.cam.subprocess.run", fake_run)
    cmd_cam(notes_dir=str(tmp_path / "cam"))
    assert list((tmp_path / "cam").glob("cam_*.jpg"))


def _smoke_para(tmp_path: Path, monkeypatch) -> None:
    from anno.para_launch import cmd_para_new, cmd_para_open

    for name in ("startup.py", "export.py"):
        ast.parse((_SRC / "paraview" / name).read_text())

    monkeypatch.setattr("anno.para_launch.shutil.which", lambda name: "/usr/bin/paraview")
    launched: list[tuple] = []

    def fake_popen(argv, env=None):
        launched.append((list(argv), dict(env or {})))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr("anno.para_launch.subprocess.Popen", fake_popen)
    mesh = tmp_path / "blade.vtu"
    mesh.write_text("mesh")
    notes = tmp_path / "para"
    cmd_para_new([str(mesh)], notes_dir=str(notes))
    assert launched and "paraview" in launched[0][0][0]
    assert launched[0][1]["ANNO_MESH_FILES"].endswith("blade.vtu")
    assert (notes).is_dir()

    log = tmp_path / "para-log.jsonl"
    log.write_text(json.dumps({"action": "para_open", "file": str(mesh), "ts": "2026-01-01T00:00:00"}) + "\n")
    monkeypatch.setattr("anno.para_launch.DEFAULT_LOG_FILE", log)
    launched.clear()
    cmd_para_open(notes_dir=str(notes))
    assert launched


def _smoke_list_log(tmp_path: Path, log_file: Path) -> None:
    from anno.activity_log import cmd_log
    from anno.listing import cmd_list

    draw = tmp_path / "list-draw"
    mind = tmp_path / "list-mind"
    mer = tmp_path / "list-mer"
    d2 = tmp_path / "list-d2"
    for d in (draw, mind, mer, d2):
        d.mkdir()
    (draw / "fig.svg").write_text("<svg/>")
    (mind / "map.minder").write_text("<minder/>")
    (mer / "pipe.md").write_text("# p\n")
    (d2 / "flow.d2").write_text("a -> b\n")
    cmd_list(str(draw), str(mind), str(mer), str(d2))
    cmd_log(log_file=str(log_file))
    cmd_log(date="1999-01-01", log_file=str(tmp_path / "missing.jsonl"))
