"""Tests for D2 stubs, paths, and editor argv."""

from pathlib import Path

from anno.d2 import (
    check_d2,
    compile_d2,
    d2_path,
    d2_template,
    editor_argv,
    ensure_d2_file,
    open_d2,
    validate_d2,
)


def test_template_is_rightward_container_flow():
    text = d2_template("pipeline")
    assert text.startswith("# pipeline\n")
    assert "direction: right" in text
    assert "inputs -> group" in text
    assert "group: {" in text
    assert "g_data: data" in text
    assert "g_algo: algo" in text
    assert "group -> group2" in text
    assert "group2: {" in text
    assert "group2 -> outputs" in text
    assert "```" not in text


def test_named_path_is_stem_d2(tmp_path: Path):
    assert d2_path(tmp_path, "Auth Flow.d2") == tmp_path / "Auth Flow.d2"
    assert d2_path(tmp_path, "pipeline") == tmp_path / "pipeline.d2"


def test_scratch_path_uses_prefix_and_timestamp(tmp_path: Path):
    path = d2_path(tmp_path, "")
    assert path.parent == tmp_path
    assert path.name.startswith("d2_")
    assert path.suffix == ".d2"


def test_ensure_creates_only_when_missing(tmp_path: Path):
    path = tmp_path / "pipeline.d2"
    assert ensure_d2_file(path, "pipeline") is True
    original = path.read_text()
    path.write_text("# hand-edited\n")
    assert ensure_d2_file(path, "pipeline") is False
    assert path.read_text() == "# hand-edited\n"
    assert "direction: right" in original


def test_editor_prefers_visual_then_editor(monkeypatch):
    monkeypatch.setenv("VISUAL", "hx")
    monkeypatch.setenv("EDITOR", "vim")
    monkeypatch.setattr("anno.d2.shutil.which", lambda name: None)
    assert editor_argv(Path("x.d2")) == ["hx", "x.d2"]
    monkeypatch.delenv("VISUAL")
    assert editor_argv(Path("x.d2")) == ["vim", "x.d2"]


def test_editor_falls_back_to_gvim_then_code(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr("anno.d2.shutil.which", lambda name: "/usr/bin/gvim" if name == "gvim" else None)
    assert editor_argv(Path("x.d2")) == ["gvim", "--nofork", "x.d2"]
    monkeypatch.setattr("anno.d2.shutil.which", lambda name: "/usr/bin/code" if name == "code" else None)
    assert editor_argv(Path("x.d2")) == ["code", "--wait", "x.d2"]


def test_open_d2_creates_edits_and_copies(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VISUAL", "hx")
    launched = []
    copied = []

    def fake_editor(argv):
        launched.append(argv)
        Path(argv[-1]).write_text("# edited\n\ninputs -> outputs\n")

    path = open_d2(
        "pipeline",
        notes_dir=str(tmp_path),
        no_check=True,
        run_editor=fake_editor,
        copy_text=copied.append,
    )
    assert path == tmp_path / "pipeline.d2"
    assert launched[0][-1] == str(path)
    assert copied == [path.read_text()]
    assert "inputs -> outputs" in path.read_text()


def test_open_d2_does_not_overwrite_existing(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VISUAL", "hx")
    existing = tmp_path / "pipeline.d2"
    existing.write_text("# keep me\n")
    open_d2(
        "pipeline",
        notes_dir=str(tmp_path),
        no_check=True,
        run_editor=lambda argv: None,
        copy_text=lambda text: None,
    )
    assert existing.read_text() == "# keep me\n"


def test_check_ok_softens_notes_then_validates(tmp_path: Path, capsys):
    (tmp_path / "ok.d2").write_text("a -> b\nwhere matdb?\n")
    seen: list[str] = []

    def validate(src: str) -> tuple[bool, str]:
        seen.append(src)
        return True, "Success! [Input] is valid D2."

    result = check_d2("ok", notes_dir=str(tmp_path), validate=validate)
    assert result.ok is True
    assert result.exit_code == 0
    assert result.mode == "preview"
    assert "# where matdb?" in seen[0]
    assert "where matdb?" not in [ln.strip() for ln in seen[0].splitlines() if not ln.strip().startswith("#")]
    out = capsys.readouterr().out
    assert "ok.d2" in out
    assert "preview" in out
    assert "valid D2" in out


def test_check_strict_validates_raw_file(tmp_path: Path):
    (tmp_path / "notes.d2").write_text("a -> b\nwhere matdb?\n")
    seen: list[str] = []

    def validate(src: str) -> tuple[bool, str]:
        seen.append(src)
        return True, "ok"

    result = check_d2("notes", notes_dir=str(tmp_path), strict=True, validate=validate)
    assert result.ok is True
    assert result.mode == "strict"
    assert "where matdb?" in seen[0]
    assert "# where matdb?" not in seen[0]


def test_check_prints_compiler_errors(tmp_path: Path, capsys):
    (tmp_path / "bad.d2").write_text("a -> {\n")
    d2_err = "err: oss.terrastruct.com/d2/d2cli.validateCmd: 1:6: maps must be terminated with }"
    result = check_d2(
        "bad",
        notes_dir=str(tmp_path),
        validate=lambda src: (False, d2_err),
    )
    assert result.ok is False
    assert result.exit_code == 1
    out = capsys.readouterr().out
    assert "1:6: maps must be terminated with }" in out
    assert "oss.terrastruct.com" not in out


def test_check_missing_file_does_not_create(tmp_path: Path, capsys):
    result = check_d2("nope", notes_dir=str(tmp_path))
    assert result.ok is False
    assert result.exit_code == 2
    assert not (tmp_path / "nope.d2").exists()
    assert "not found" in capsys.readouterr().out.lower()


def test_check_accepts_existing_path(tmp_path: Path):
    path = tmp_path / "nested" / "x.d2"
    path.parent.mkdir()
    path.write_text("a -> b\n")
    seen: list[str] = []

    def validate(src: str) -> tuple[bool, str]:
        seen.append(src)
        return True, "ok"

    result = check_d2(str(path), notes_dir=str(tmp_path / "other"), validate=validate)
    assert result.ok is True
    assert result.path == path
    assert seen


def test_validate_d2_reports_missing_binary(monkeypatch):
    monkeypatch.setattr("anno.d2.shutil.which", lambda name: None)
    ok, msg = validate_d2("a -> b\n")
    assert ok is False
    assert "PATH" in msg


def test_check_no_name_uses_single_live_file(tmp_path: Path, monkeypatch):
    path = tmp_path / "live.d2"
    path.write_text("a -> b\n")
    monkeypatch.setattr("anno.d2.running_live_paths", lambda: [path])
    result = check_d2("", notes_dir=str(tmp_path), validate=lambda src: (True, "ok"))
    assert result.ok is True
    assert result.path == path


def test_validate_d2_real_compiler_accepts_simple_edge():
    import shutil

    if not shutil.which("d2"):
        return
    ok, msg = validate_d2("a -> b\n")
    assert ok, msg


def test_compile_d2_catches_markdown_html_that_validate_accepts():
    import shutil

    if not shutil.which("d2"):
        return
    src = "user: |md\n  hello <gb10-lan>\n|\n"
    vok, _ = validate_d2(src)
    cok, cmsg = compile_d2(src)
    assert vok is True
    assert cok is False
    assert "malformed Markdown" in cmsg or "gb10-lan" in cmsg


def test_open_refuses_when_compile_fails(tmp_path: Path, capsys):
    (tmp_path / "bad.d2").write_text("a -> b\n")
    launched: list[object] = []
    try:
        open_d2(
            "bad",
            notes_dir=str(tmp_path),
            run_editor=launched.append,
            copy_text=lambda text: None,
            validate=lambda src: (False, "1:1: malformed Markdown: element <x>"),
        )
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("expected SystemExit")
    assert launched == []
    assert "refusing to launch" in capsys.readouterr().out


def test_open_force_launches_when_compile_fails(tmp_path: Path):
    (tmp_path / "bad.d2").write_text("a -> b\n")
    launched: list[object] = []
    open_d2(
        "bad",
        notes_dir=str(tmp_path),
        force=True,
        run_editor=launched.append,
        copy_text=lambda text: None,
        validate=lambda src: (False, "1:1: malformed Markdown"),
    )
    assert launched


def test_open_no_check_skips_compile(tmp_path: Path):
    (tmp_path / "bad.d2").write_text("a -> b\n")
    seen: list[str] = []
    launched: list[object] = []
    open_d2(
        "bad",
        notes_dir=str(tmp_path),
        no_check=True,
        run_editor=launched.append,
        copy_text=lambda text: None,
        validate=lambda src: seen.append(src) or (False, "should not run"),
    )
    assert launched
    assert seen == []
