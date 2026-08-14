import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from textwrap import dedent

from anno.clipboard import copy_text_to_clipboard
from anno.constants import DEFAULT_MERMAID_DIR
from anno.log_util import log_activity
from anno.mermaid_live import run_live_editor

# Later: anno dot / neato — Graphviz as a sibling group, same find-or-create + editor rhythm.
STYLES = ("flowchart", "sequence", "state", "class")


def _stub(body: str) -> str:
    return dedent(body).lstrip("\n")


_TEMPLATES = {
    "flowchart": _stub("""
        # {title}

        ```mermaid
        flowchart LR
          inputs --> group
          subgraph group
            g_data@{ shape: diff, label: "data" }
            g_algo@{ shape: diff, label: "algo" }
          end
          group --> group2
          subgraph group2
            h_data@{ shape: diff, label: "data" }
            h_algo@{ shape: diff, label: "algo" }
          end
          group2 --> outputs
        ```
    """),
    "sequence": _stub("""
        # {title}

        ```mermaid
        sequenceDiagram
          actor User
          User->>API: request
          API-->>User: response
        ```
    """),
    "state": _stub("""
        # {title}

        ```mermaid
        stateDiagram-v2
          [*] --> Closed
          Closed --> Open
          Open --> Closed
        ```
    """),
    "class": _stub("""
        # {title}

        ```mermaid
        classDiagram
          class Thing {
            +id
          }
        ```
    """),
}


def mermaid_template(style: str, title: str) -> str:
    if style not in _TEMPLATES:
        raise ValueError(f"unknown mermaid style {style!r}; available: {', '.join(STYLES)}")
    return _TEMPLATES[style].replace("{title}", title)


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
    """Fallback when the live mermaid.js preview cannot run."""
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        return [editor, str(path)]
    if shutil.which("gvim"):
        return ["gvim", "--nofork", str(path)]
    if shutil.which("code"):
        return ["code", "--wait", str(path)]
    raise RuntimeError("no editor: set $VISUAL/$EDITOR, or install gvim or VS Code")


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
    log_activity("mermaid_edit", path)
    print(f"saved  : {path}")
    print("copied : markdown to clipboard")
    print("note   : preview stays open and rerenders when the file changes")
    return path


def cmd_mermaid_flowchart(name: str = "", notes_dir: str = str(DEFAULT_MERMAID_DIR)) -> None:
    open_mermaid("flowchart", name, notes_dir)


def cmd_mermaid_sequence(name: str = "", notes_dir: str = str(DEFAULT_MERMAID_DIR)) -> None:
    open_mermaid("sequence", name, notes_dir)


def cmd_mermaid_state(name: str = "", notes_dir: str = str(DEFAULT_MERMAID_DIR)) -> None:
    open_mermaid("state", name, notes_dir)


def cmd_mermaid_class(name: str = "", notes_dir: str = str(DEFAULT_MERMAID_DIR)) -> None:
    open_mermaid("class", name, notes_dir)
