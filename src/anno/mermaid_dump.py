"""Load mermaid however it was dumped: fences, raw diagrams, stray notes."""

from __future__ import annotations

import re

_DIAGRAM = re.compile(
    r"^(flowchart|graph|sequenceDiagram|stateDiagram(?:-v2)?|classDiagram|"
    r"erDiagram|journey|gantt|pie|gitGraph|mindmap|timeline|quadrantChart|"
    r"requirementDiagram|C4Context|block-beta|sankey-beta)\b",
    re.I,
)
_FENCE = re.compile(r"```(?:mermaid)?[ \t]*\n(.*?)(?:```|$)", re.S | re.I)
_EDGE = re.compile(r"(-->|---|-.->|==>|->>|-->>|--x|--o)")
_NODE_DEF = re.compile(r"^[A-Za-z_][\w.-]*(\[|\(|\{|>|@|:)")
_BARE_ID = re.compile(r"^[A-Za-z_][\w.-]*$")
_KEEP_START = (
    "subgraph",
    "end",
    "direction",
    "classdef",
    "class",
    "linkstyle",
    "style",
    "click",
    "participant",
    "actor",
    "note",
    "loop",
    "alt",
    "else",
    "opt",
    "par",
    "and",
    "rect",
    "activate",
    "deactivate",
    "state",
    "[*]",
    "acctitle",
    "accdescr",
)


def extract_sources(md: str) -> list[str]:
    """Bodies to render: ```mermaid fences (even unclosed), or a raw diagram."""
    found = [m.group(1) for m in _FENCE.finditer(md)]
    if found:
        return found
    body = md
    if body.lstrip().startswith("#"):
        lines = body.splitlines()
        i = 0
        while i < len(lines) and (not lines[i].strip() or lines[i].lstrip().startswith("#")):
            i += 1
        body = "\n".join(lines[i:])
    first = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")
    if first.startswith("%%{") or _DIAGRAM.match(first):
        return [body]
    return []


def _keep_line(stripped: str) -> bool:
    if not stripped or stripped.startswith("%%"):
        return True
    if _DIAGRAM.match(stripped):
        return True
    head = stripped.split(None, 1)[0].lower()
    if head in _KEEP_START or stripped.startswith("[*]"):
        return True
    if _EDGE.search(stripped):
        return True
    if _NODE_DEF.match(stripped) or _BARE_ID.match(stripped):
        return True
    return False


def soften_comments(src: str) -> str:
    """Turn prose / notes into mermaid `%%` comments. Leaves statements alone."""
    out: list[str] = []
    for line in src.splitlines():
        raw = line.rstrip("\n")
        stripped = raw.strip()
        if _keep_line(stripped):
            out.append(raw)
            continue
        indent = raw[: len(raw) - len(raw.lstrip())]
        text = stripped[2:].lstrip() if stripped.startswith("# ") else stripped
        out.append(f"{indent}%% {text}")
    return "\n".join(out)


def sources_for_preview(md: str) -> list[str]:
    """Extract dump bodies and soften stray notes so mermaid.js can render."""
    return [soften_comments(src) for src in extract_sources(md)]
