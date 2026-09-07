import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from textwrap import dedent

from anno.clipboard import copy_text_to_clipboard
from anno.constants import DEFAULT_D2_DIR
from anno.d2_dump import sources_for_preview
from anno.d2_live import run_live_editor, running_live_paths
from anno.log_util import log_activity


def _stub(body: str) -> str:
    return dedent(body).lstrip("\n")


_TEMPLATE = _stub("""
    # {title}

    direction: right
    inputs -> group
    group: {
      g_data: data
      g_algo: algo
    }
    group -> group2
    group2: {
      h_data: data
      h_algo: algo
    }
    group2 -> outputs
""")


def d2_template(title: str) -> str:
    return _TEMPLATE.replace("{title}", title)


def d2_path(notes_dir: Path, name: str) -> Path:
    if name:
        return notes_dir / f"{Path(name).stem}.d2"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return notes_dir / f"d2_{ts}.d2"


def ensure_d2_file(path: Path, title: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(d2_template(title))
    return True


def editor_argv(path: Path) -> list[str]:
    """Fallback when the live D2 preview cannot run."""
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        return [editor, str(path)]
    if shutil.which("gvim"):
        return ["gvim", "--nofork", str(path)]
    if shutil.which("code"):
        return ["code", "--wait", str(path)]
    raise RuntimeError("no editor: set $VISUAL/$EDITOR, or install gvim or VS Code")


def open_d2(
    name: str = "",
    notes_dir: str = str(DEFAULT_D2_DIR),
    *,
    force: bool = False,
    no_check: bool = False,
    run_editor: Callable[[list[str]], object] | None = None,
    copy_text: Callable[[str], object] | None = None,
    validate: Callable[[str], tuple[bool, str]] | None = None,
) -> Path:
    name = name or ""
    out_dir = Path(notes_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = d2_path(out_dir, name)
    created = ensure_d2_file(path, path.stem)
    print(f"{'created' if created else 'opening'}: {path}")
    if not no_check:
        result = check_d2(str(path), str(out_dir), validate=validate)
        missing = any("PATH" in m for m in result.messages)
        if missing:
            print("note   : d2 not on PATH — launching without compile check")
        elif not result.ok and not force:
            print("error  : refusing to launch — fix the graph or pass --force")
            sys.exit(1)
        elif not result.ok:
            print("note   : launching anyway (--force)")
    if run_editor is not None:
        try:
            argv = editor_argv(path)
        except RuntimeError as exc:
            sys.exit(f"error  : {exc}")
        run_editor(argv)
    elif not run_live_editor(path):
        try:
            argv = editor_argv(path)
        except RuntimeError as exc:
            sys.exit(f"error  : {exc}")
        subprocess.run(argv)
    text = path.read_text() if path.exists() else ""
    (copy_text or copy_text_to_clipboard)(text)
    log_activity("d2_edit", path)
    print(f"saved  : {path}")
    print("copied : d2 to clipboard")
    print("note   : preview stays open and rerenders when the file changes")
    return path


def cmd_d2_open(
    name: str = "",
    notes_dir: str = str(DEFAULT_D2_DIR),
    force: bool = False,
    no_check: bool = False,
) -> None:
    open_d2(name, notes_dir, force=force, no_check=no_check)


@dataclass(frozen=True)
class CheckResult:
    path: Path | None
    ok: bool
    mode: str
    messages: tuple[str, ...]
    exit_code: int


def clean_d2_message(msg: str) -> str:
    """Drop d2 CLI noise; keep `line:col: reason` lines."""
    lines: list[str] = []
    for raw in (msg or "").splitlines():
        line = raw.strip()
        if line.startswith("err: "):
            line = line[5:]
        if "validateCmd: " in line:
            line = line.split("validateCmd: ", 1)[1]
        loc = re.search(r"\d+:\d+:\s+\S.*", line)
        if loc:
            line = loc.group(0)
        if line:
            lines.append(line)
    return "\n".join(lines)


def validate_d2(src: str) -> tuple[bool, str]:
    """Syntax-only `d2 validate`. Misses markdown/render errors — prefer compile_d2."""
    exe = shutil.which("d2")
    if not exe:
        return False, "d2 not on PATH — install from https://d2lang.com"
    proc = subprocess.run(
        [exe, "validate", "-"],
        input=src,
        capture_output=True,
        text=True,
    )
    msg = (proc.stderr or proc.stdout or "").strip()
    return proc.returncode == 0, msg


def compile_d2(src: str) -> tuple[bool, str]:
    """Full compile (`d2` → SVG). Catches markdown/HTML errors that validate misses."""
    exe = shutil.which("d2")
    if not exe:
        return False, "d2 not on PATH — install from https://d2lang.com"
    proc = subprocess.run(
        [exe, "--stdout-format", "svg", "-", "-"],
        input=src,
        capture_output=True,
        text=True,
    )
    msg = (proc.stderr or proc.stdout or "").strip()
    if proc.returncode != 0:
        return False, msg
    return True, msg or "compiled"


def resolve_check_path(name: str, notes_dir: Path) -> Path | None:
    """Existing file, notes-dir stem, or the single running live preview."""
    name = (name or "").strip()
    if name:
        given = Path(name)
        if given.is_file():
            return given
        return d2_path(notes_dir, name)
    lives = running_live_paths()
    if len(lives) == 1:
        return lives[0]
    return None


def check_d2(
    name: str = "",
    notes_dir: str = str(DEFAULT_D2_DIR),
    *,
    strict: bool = False,
    validate: Callable[[str], tuple[bool, str]] | None = None,
) -> CheckResult:
    """Full-compile a .d2 file. Does not create files."""
    path = resolve_check_path(name, Path(notes_dir))
    mode = "strict" if strict else "preview"
    if path is None:
        print("error  : no diagram — pass a name (anno d2 check pipeline)")
        return CheckResult(None, False, mode, ("no diagram",), 2)
    if not path.is_file():
        print(f"error  : not found: {path}")
        return CheckResult(path, False, mode, (f"not found: {path}",), 2)

    text = path.read_text()
    bodies = [text] if strict else sources_for_preview(text)
    if not any(body.strip() for body in bodies):
        print(f"check  : {path}")
        print(f"mode   : {mode}")
        print("error  : empty d2")
        return CheckResult(path, False, mode, ("empty d2",), 1)

    runner = validate or compile_d2
    messages: list[str] = []
    ok = True
    for i, body in enumerate(bodies):
        if not body.strip():
            continue
        body_ok, raw = runner(body)
        cleaned = clean_d2_message(raw)
        if not body_ok:
            ok = False
        if cleaned:
            if len(bodies) > 1:
                messages.append(f"[{i + 1}] {cleaned}")
            else:
                messages.append(cleaned)

    print(f"check  : {path}")
    print(f"mode   : {mode}")
    if ok:
        print("ok     : valid D2")
        return CheckResult(path, True, mode, tuple(messages), 0)
    for msg in messages or ("compile failed",):
        for line in msg.splitlines() or [msg]:
            print(f"error  : {line}")
    return CheckResult(path, False, mode, tuple(messages), 1)


def cmd_d2_check(
    name: str = "",
    notes_dir: str = str(DEFAULT_D2_DIR),
    strict: bool = False,
) -> None:
    result = check_d2(name or "", notes_dir, strict=strict)
    sys.exit(result.exit_code)
