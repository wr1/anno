"""Load D2 however it was dumped: raw .d2, optional fences, stray notes."""

from __future__ import annotations

import re

_FENCE = re.compile(r"```d2[ \t]*\n(.*?)(?:```|$)", re.S | re.I)
_EDGE = re.compile(r"(<->|<-|->|--)")
_KEY = re.compile(r"^[A-Za-z_][\w.-]*(\.[A-Za-z_][\w.-]*)*\s*:")
_BARE_ID = re.compile(r"^[A-Za-z_][\w.-]*$")
_KEEP_HEAD = ("vars", "classes", "layers", "scenarios", "steps")


def extract_sources(text: str) -> list[str]:
    """Bodies to render: ```d2 fences (even unclosed), or the whole file."""
    found = [m.group(1) for m in _FENCE.finditer(text)]
    if found:
        return found
    return [text]


def _keep_line(stripped: str) -> bool:
    if not stripped or stripped.startswith("#"):
        return True
    if stripped == "}" or stripped.startswith("}"):
        return True
    if _EDGE.search(stripped):
        return True
    if _KEY.match(stripped):
        return True
    if _BARE_ID.match(stripped):
        return True
    head = stripped.split(None, 1)[0].rstrip(":").lower()
    return head in _KEEP_HEAD


# `user: ||md` / `|md` / `||` — D2 block-string open/close (any pipe run + tag).
_BLOCK_OPEN = re.compile(r"^(?:[A-Za-z_][\w.-]*(?:\.[A-Za-z_][\w.-]*)*\s*:)?\s*(\|+)([A-Za-z][\w-]*)?\s*$")


def _block_close(stripped: str, delim: str) -> bool:
    if not stripped.startswith(delim):
        return False
    rest = stripped[len(delim) :].lstrip()
    return rest == "" or rest.startswith("{")


def soften_comments(src: str) -> str:
    """Turn prose / notes into D2 `#` comments. Leaves statements and block strings alone."""
    out: list[str] = []
    delim: str | None = None
    for line in src.splitlines():
        raw = line.rstrip("\n")
        stripped = raw.strip()
        if delim is not None:
            out.append(raw)
            if _block_close(stripped, delim):
                delim = None
            continue
        opened = _BLOCK_OPEN.match(stripped)
        if opened:
            delim = opened.group(1)
            out.append(raw)
            continue
        if _keep_line(stripped):
            out.append(raw)
            continue
        indent = raw[: len(raw) - len(raw.lstrip())]
        text = stripped[2:].lstrip() if stripped.startswith("# ") else stripped
        out.append(f"{indent}# {text}")
    return "\n".join(out)


_CONN_ID = re.compile(r"^\((.+)\)\[\d+\]$")
_EDGE_SEP = (" <-> ", " -> ", " <- ", " -- ")


def find_object_span(src: str, object_id: str) -> tuple[int, int] | None:
    """Char span of an object's declaration (or edge) in `src`, or None."""
    object_id = (object_id or "").strip()
    if not object_id:
        return None
    conn = _CONN_ID.match(object_id)
    if conn:
        return _find_edge_span(src, conn.group(1))
    return _find_shape_span(src, object_id)


def _key_pattern(leaf: str) -> re.Pattern[str]:
    esc = re.escape(leaf)
    return re.compile(rf'(?m)^([ \t]*)(?:"{esc}"|{esc})(?=\s*[:{{]|\s*$)')


def _span_of_key(src: str, match: re.Match[str], leaf: str) -> tuple[int, int]:
    start = match.start() + len(match.group(1))
    if start < len(src) and src[start] == '"':
        return start, start + len(leaf) + 2
    return start, start + len(leaf)


def _find_shape_span(src: str, path: str) -> tuple[int, int] | None:
    parts = [p for p in path.split(".") if p]
    if not parts:
        return None
    leaf = parts[-1]
    matches = list(_key_pattern(leaf).finditer(src))
    if not matches:
        return None
    chosen = matches[0]
    if len(parts) > 1 and len(matches) > 1:
        parent = _find_shape_span(src, ".".join(parts[:-1]))
        if parent:
            after = [m for m in matches if m.start() >= parent[0]]
            if after:
                chosen = after[0]
    return _span_of_key(src, chosen, leaf)


def _find_edge_span(src: str, inner: str) -> tuple[int, int] | None:
    left = right = sep = None
    for token in _EDGE_SEP:
        if token in inner:
            left, right = inner.split(token, 1)
            sep = token.strip()
            break
    if left is None or right is None or sep is None:
        return None
    left_leaf = left.split(".")[-1].strip().strip('"')
    right_leaf = right.split(".")[-1].strip().strip('"')
    pat = re.compile(rf"(?m)^([ \t]*){re.escape(left_leaf)}\s*{re.escape(sep)}\s*{re.escape(right_leaf)}")
    match = pat.search(src)
    if not match:
        return None
    start = match.start() + len(match.group(1))
    return start, match.end()


def sources_for_preview(text: str) -> list[str]:
    """Extract dump bodies and soften stray notes so D2 can render."""
    return [soften_comments(src) for src in extract_sources(text)]
