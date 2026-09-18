import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from anno.activity_log import log_activity
from anno.clipboard import copy_text_to_clipboard
from anno.constants import DEFAULT_MERMAID_DIR
from anno.editor import OpenResult, editor_argv, stub
from anno.mermaid_live import run_live_editor

# Later: anno dot / neato — Graphviz as a sibling group, same find-or-create + editor rhythm.
STYLES = ("flowchart", "sequence", "state", "class")


_TEMPLATES = {
    "flowchart": stub("""
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
    "sequence": stub("""
        # {title}

        ```mermaid
        sequenceDiagram
          actor User
          User->>API: request
          API-->>User: response
        ```
    """),
    "state": stub("""
        # {title}

        ```mermaid
        stateDiagram-v2
          [*] --> Closed
          Closed --> Open
          Open --> Closed
        ```
    """),
    "class": stub("""
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


def open_mermaid(
    style: str,
    name: str = "",
    notes_dir: str = str(DEFAULT_MERMAID_DIR),
    *,
    run_editor: Callable[[list[str]], object] | None = None,
    copy_text: Callable[[str], object] | None = None,
) -> OpenResult:
    name = name or ""
    out_dir = Path(notes_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = mermaid_path(out_dir, style, name)
    created = ensure_mermaid_file(path, style, path.stem)
    messages = [f"{'created' if created else 'opening'}: {path}"]
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
    log_activity("mermaid_edit", path)
    messages += [
        f"saved  : {path}",
        "copied : markdown to clipboard",
        "note   : preview stays open and rerenders when the file changes",
    ]
    return OpenResult(path, created, copied=True, messages=tuple(messages))


def _emit(result: OpenResult) -> None:
    for line in result.messages:
        print(line)
    if not result.ok:
        sys.exit(result.exit_code)


def cmd_mermaid_flowchart(name: str = "", notes_dir: str = str(DEFAULT_MERMAID_DIR)) -> None:
    _emit(open_mermaid("flowchart", name, notes_dir))


def cmd_mermaid_sequence(name: str = "", notes_dir: str = str(DEFAULT_MERMAID_DIR)) -> None:
    _emit(open_mermaid("sequence", name, notes_dir))


def cmd_mermaid_state(name: str = "", notes_dir: str = str(DEFAULT_MERMAID_DIR)) -> None:
    _emit(open_mermaid("state", name, notes_dir))


def cmd_mermaid_class(name: str = "", notes_dir: str = str(DEFAULT_MERMAID_DIR)) -> None:
    _emit(open_mermaid("class", name, notes_dir))
