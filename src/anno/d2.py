import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from anno.activity_log import log_activity
from anno.clipboard import copy_text_to_clipboard
from anno.constants import DEFAULT_D2_DIR
from anno.d2_dump import sources_for_preview
from anno.d2_live import run_live_editor, running_live_paths
from anno.editor import OpenResult, editor_argv, stub

_TEMPLATE = stub("""
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


# --- compile / validate ---


@dataclass(frozen=True)
class CheckResult:
    path: Path | None
    ok: bool
    mode: str
    messages: tuple[str, ...]
    exit_code: int
    status: str = "ok"  # ok | no_diagram | not_found | empty | invalid


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
    """Full-compile a .d2 file. Does not create files or print."""
    path = resolve_check_path(name, Path(notes_dir))
    mode = "strict" if strict else "preview"
    if path is None:
        return CheckResult(None, False, mode, ("no diagram",), 2, "no_diagram")
    if not path.is_file():
        return CheckResult(path, False, mode, (f"not found: {path}",), 2, "not_found")

    text = path.read_text()
    bodies = [text] if strict else sources_for_preview(text)
    if not any(body.strip() for body in bodies):
        return CheckResult(path, False, mode, ("empty d2",), 1, "empty")

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
            messages.append(f"[{i + 1}] {cleaned}" if len(bodies) > 1 else cleaned)

    return CheckResult(path, ok, mode, tuple(messages), 0 if ok else 1, "ok" if ok else "invalid")


def check_lines(result: CheckResult) -> list[str]:
    """Render a CheckResult as the labels `anno d2 check` prints."""
    if result.status == "no_diagram":
        return ["error  : no diagram — pass a name (anno d2 check pipeline)"]
    if result.status == "not_found":
        return [f"error  : not found: {result.path}"]
    lines = [f"check  : {result.path}", f"mode   : {result.mode}"]
    if result.ok:
        lines.append("ok     : valid D2")
    elif result.status == "empty":
        lines.append("error  : empty d2")
    else:
        for msg in result.messages or ("compile failed",):
            for line in msg.splitlines() or [msg]:
                lines.append(f"error  : {line}")
    return lines


# --- find-or-create + edit ---


def open_d2(
    name: str = "",
    notes_dir: str = str(DEFAULT_D2_DIR),
    *,
    force: bool = False,
    no_check: bool = False,
    run_editor: Callable[[list[str]], object] | None = None,
    copy_text: Callable[[str], object] | None = None,
    validate: Callable[[str], tuple[bool, str]] | None = None,
) -> OpenResult:
    name = name or ""
    out_dir = Path(notes_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = d2_path(out_dir, name)
    created = ensure_d2_file(path, path.stem)
    messages = [f"{'created' if created else 'opening'}: {path}"]
    if not no_check:
        result = check_d2(str(path), str(out_dir), validate=validate)
        messages.extend(check_lines(result))
        missing = any("PATH" in m for m in result.messages)
        if missing:
            messages.append("note   : d2 not on PATH — launching without compile check")
        elif not result.ok and not force:
            messages.append("error  : refusing to launch — fix the graph or pass --force")
            return OpenResult(path, created, copied=False, messages=tuple(messages), ok=False, exit_code=1)
        elif not result.ok:
            messages.append("note   : launching anyway (--force)")
    try:
        if run_editor is not None:
            run_editor(editor_argv(path))
        elif not run_live_editor(path):
            subprocess.run(editor_argv(path))
    except RuntimeError as exc:
        messages.append(f"error  : {exc}")
        return OpenResult(path, created, copied=False, messages=tuple(messages), ok=False, exit_code=1)
    text = path.read_text() if path.exists() else ""
    (copy_text or copy_text_to_clipboard)(text)
    log_activity("d2_edit", path)
    messages += [
        f"saved  : {path}",
        "copied : d2 to clipboard",
        "note   : preview stays open and rerenders when the file changes",
    ]
    return OpenResult(path, created, copied=True, messages=tuple(messages))


def _emit(result: OpenResult) -> None:
    for line in result.messages:
        print(line)
    if not result.ok:
        sys.exit(result.exit_code)


def cmd_d2_open(
    name: str = "",
    notes_dir: str = str(DEFAULT_D2_DIR),
    force: bool = False,
) -> None:
    _emit(open_d2(name, notes_dir, force=force))


def cmd_d2_check(
    name: str = "",
    notes_dir: str = str(DEFAULT_D2_DIR),
) -> None:
    result = check_d2(name or "", notes_dir)
    for line in check_lines(result):
        print(line)
    sys.exit(result.exit_code)
