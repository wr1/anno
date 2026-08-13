import os
import shutil
from datetime import datetime
from pathlib import Path

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
