"""Shared plumbing for the find-or-create editor commands (mermaid, D2).

Each command opens a file in a live browser sidecar, or falls back to a
terminal/GUI editor. The stubs, editor selection, and the result object they
return are identical, so they live here.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent


def stub(body: str) -> str:
    """Dedent a template body and drop its leading newline."""
    return dedent(body).lstrip("\n")


def editor_argv(path: Path) -> list[str]:
    """Fallback editor when the live preview cannot run."""
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        return [editor, str(path)]
    if shutil.which("gvim"):
        return ["gvim", "--nofork", str(path)]
    if shutil.which("code"):
        return ["code", "--wait", str(path)]
    raise RuntimeError("no editor: set $VISUAL/$EDITOR, or install gvim or VS Code")


@dataclass(frozen=True)
class OpenResult:
    """Outcome of a find-or-create editor command.

    `messages` are the ready-to-print lines; the `cmd_*` wrappers own stdout
    so the underlying `open_*` functions stay side-effect free.
    """

    path: Path
    created: bool
    copied: bool
    messages: tuple[str, ...]
    ok: bool = True
    exit_code: int = 0
