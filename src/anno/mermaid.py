import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from anno.clipboard import copy_text_to_clipboard
from anno.constants import DEFAULT_MERMAID_DIR
from anno.log_util import log_activity

# Later: anno dot / neato — Graphviz as a sibling group, same find-or-create + editor rhythm.
STYLES = ("flowchart", "sequence", "state", "class")

_TEMPLATES = {
    "flowchart": ("# {title}\n\n```mermaid\nflowchart TD\n  start[Start] --> done[Done]\n```\n"),
    "sequence": (
        "# {title}\n\n```mermaid\nsequenceDiagram\n  actor User\n  User->>API: request\n  API-->>User: response\n```\n"
    ),
    "state": (
        "# {title}\n\n```mermaid\nstateDiagram-v2\n  [*] --> Closed\n  Closed --> Open\n  Open --> Closed\n```\n"
    ),
    "class": ("# {title}\n\n```mermaid\nclassDiagram\n  class Thing {{\n    +id\n  }}\n```\n"),
}


def mermaid_template(style: str, title: str) -> str:
    if style not in _TEMPLATES:
        raise ValueError(f"unknown mermaid style {style!r}; available: {', '.join(STYLES)}")
    return _TEMPLATES[style].format(title=title)


def mermaid_path(notes_dir: Path, style: str, name: str) -> Path:
    if name:
        return notes_dir / f"{Path(name).stem}.md"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return notes_dir / f"{style}_{ts}.md"


def ensure_mermaid_file(path: Path, style: str, title: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(mermaid_template(style, title))
    return True


def editor_argv(path: Path) -> list[str]:
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        return [editor, str(path)]
    if shutil.which("gvim"):
        return ["gvim", "--nofork", str(path)]
    raise RuntimeError("no editor: set $VISUAL or $EDITOR, or install gvim")


def open_mermaid(
    style: str,
    name: str = "",
    notes_dir: str = str(DEFAULT_MERMAID_DIR),
    *,
    run_editor: Callable[[list[str]], object] | None = None,
    copy_text: Callable[[str], object] | None = None,
) -> Path:
    name = name or ""
    out_dir = Path(notes_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = mermaid_path(out_dir, style, name)
    created = ensure_mermaid_file(path, style, path.stem)
    print(f"{'created' if created else 'opening'}: {path}")
    try:
        argv = editor_argv(path)
    except RuntimeError as exc:
        sys.exit(f"error  : {exc}")
    (run_editor or subprocess.run)(argv)
    text = path.read_text() if path.exists() else ""
    (copy_text or copy_text_to_clipboard)(text)
    log_activity("mermaid_edit", path)
    print(f"saved  : {path}")
    print("copied : markdown to clipboard")
    return path


def cmd_mermaid_flowchart(name: str = "", notes_dir: str = str(DEFAULT_MERMAID_DIR)) -> None:
    open_mermaid("flowchart", name, notes_dir)


def cmd_mermaid_sequence(name: str = "", notes_dir: str = str(DEFAULT_MERMAID_DIR)) -> None:
    open_mermaid("sequence", name, notes_dir)


def cmd_mermaid_state(name: str = "", notes_dir: str = str(DEFAULT_MERMAID_DIR)) -> None:
    open_mermaid("state", name, notes_dir)


def cmd_mermaid_class(name: str = "", notes_dir: str = str(DEFAULT_MERMAID_DIR)) -> None:
    open_mermaid("class", name, notes_dir)
