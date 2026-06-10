import re
from dataclasses import dataclass, field
from typing import Optional
from xml.sax.saxutils import escape as xml_escape

from anno.mind.styles import MINDER_STYLES


@dataclass
class MindNode:
    title: str
    note: str = ""
    children: list["MindNode"] = field(default_factory=list)


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
# Bullet items in Minder's markdown export: optional indent + "- " + title.
BULLET_RE = re.compile(r"^(\s*)-\s+(.*?)\s*$")
# Note lines in Minder's markdown export: optional indent + "> " + text.
NOTE_RE = re.compile(r"^(\s*)>\s?(.*)$")


def parse_headings_markdown(text: str) -> MindNode:
    """Parse heading-style markdown (`#`, `##`, …) into a single-rooted tree.

    Body lines under a heading become that node's note. A missing H1 is
    tolerated: a synthetic root titled "root" is created and all H1+ headings
    nest under it (rare; usually the caller writes a valid H1)."""
    root = MindNode(title="root")
    stack: list[tuple[int, MindNode]] = [(0, root)]
    note_buf: list[str] = []
    saw_h1 = False
    for raw in text.splitlines():
        m = HEADING_RE.match(raw)
        if m:
            # flush pending note lines into the current top-of-stack node
            if note_buf:
                stack[-1][1].note = "\n".join(note_buf).rstrip()
                note_buf = []
            level = len(m.group(1))
            title = m.group(2)
            if level == 1 and not saw_h1:
                # First H1 sets the root title.
                root.title = title
                saw_h1 = True
                continue
            # Pop until we find a strictly-shallower ancestor.
            while stack and stack[-1][0] >= level:
                stack.pop()
            parent = stack[-1][1] if stack else root
            node = MindNode(title=title)
            parent.children.append(node)
            stack.append((level, node))
        else:
            note_buf.append(raw)
    if note_buf:
        stack[-1][1].note = "\n".join(note_buf).rstrip()
    # Strip leading blank lines from notes for cleanliness.
    strip_note_blanks(root)
    return root


def parse_bullets_markdown(text: str) -> MindNode:
    """Parse Minder's bullet-list markdown export back into a tree.

    Minder writes:  `# Root`, then `  - child`, `    - grand`, with notes as
    `> text` lines indented to match their owner."""
    root = MindNode(title="root")
    # Stack entries: (indent_cols, node). indent_cols == -1 marks the root.
    stack: list[tuple[int, MindNode]] = [(-1, root)]
    note_target: Optional[MindNode] = None
    note_buf: list[str] = []

    def _flush_note() -> None:
        nonlocal note_buf, note_target
        if note_target is not None and note_buf:
            note_target.note = "\n".join(note_buf).rstrip()
        note_buf = []
        note_target = None

    for raw in text.splitlines():
        if not raw.strip():
            # Blank line — keep note accumulation alive; just skip.
            continue
        h = HEADING_RE.match(raw)
        if h and len(h.group(1)) == 1:
            _flush_note()
            root.title = h.group(2)
            note_target = root
            continue
        b = BULLET_RE.match(raw)
        if b:
            _flush_note()
            indent = len(b.group(1))
            title = b.group(2)
            # Pop siblings/uncles deeper or equal to this indent.
            while stack and stack[-1][0] >= indent and stack[-1][0] != -1:
                stack.pop()
            parent = stack[-1][1] if stack else root
            node = MindNode(title=title)
            parent.children.append(node)
            stack.append((indent, node))
            note_target = node
            continue
        n = NOTE_RE.match(raw)
        if n:
            note_buf.append(n.group(2))
            continue
        # Anything else (paragraph text) attaches to the most recent target.
        if note_target is not None:
            note_buf.append(raw.lstrip())
    _flush_note()
    strip_note_blanks(root)
    return root


def strip_note_blanks(node: MindNode) -> None:
    node.note = node.note.strip("\n")
    for c in node.children:
        strip_note_blanks(c)


def tree_to_headings_markdown(root: MindNode, base_level: int = 1) -> str:
    """Render a tree back to heading-style markdown.

    `base_level` controls the H-level used for the root (1 for top-level,
    higher when splicing under a deeper heading)."""
    out: list[str] = []

    def _walk(node: MindNode, level: int) -> None:
        out.append(f"{'#' * level} {node.title}".rstrip())
        if node.note:
            out.append("")
            out.append(node.note)
        for child in node.children:
            out.append("")
            _walk(child, level + 1)

    _walk(root, base_level)
    out.append("")
    return "\n".join(out)


def tree_to_numbered_markdown(root: MindNode) -> str:
    """Render a tree as a numbered outline.

    The outline numbers (1., 1.1, 1.1.1, ...) make the hierarchy explicit in the
    text so it survives aggressive whitespace stripping / flattening by some
    CLI agents and paste targets.

    A top-level # heading is emitted for the root title (synthetic "root" is
    omitted). Node notes appear indented under their item, before any children.
    """
    out: list[str] = []

    def _walk(node: MindNode, numbers: list[int], depth: int) -> None:
        if numbers:
            num_str = ".".join(str(n) for n in numbers)
            indent = "   " * depth
            # Top level gets "1. Title"; deeper use "1.1 Title" (cleaner, still unambiguous)
            label = f"{num_str}. " if len(numbers) == 1 else f"{num_str} "
            out.append(f"{indent}{label}{node.title}")
            if node.note:
                note_indent = "   " * (depth + 1)
                for line in node.note.splitlines():
                    out.append(f"{note_indent}{line}")
        for i, child in enumerate(node.children, 1):
            _walk(child, numbers + [i], depth + 1)

    # Emit a top-level heading for the root title (skip synthetic "root")
    if root.title and root.title != "root":
        out.append(f"# {root.title}")
        if root.note:
            out.append("")
            out.append(root.note)
        out.append("")

    # Number the direct children of the root at depth 0
    for i, child in enumerate(root.children, 1):
        _walk(child, [i], 0)

    out.append("")
    return "\n".join(out)


# --- markdown → Minder XML ---


def tree_to_minder_xml(root: MindNode) -> str:
    """Generate a complete .minder XML document from a tree.

    We assign safe default geometry: each child shifted right per depth and
    down per sibling index. Minder happily opens this and recomputes the
    layout-derived attrs (treesize, etc.) on first save."""
    counter = [0]

    def _next_id() -> int:
        counter[0] += 1
        return counter[0] - 1

    base_x, base_y = 400.0, 600.0
    dx, dy = 220.0, 60.0

    lines: list[str] = []

    def _emit(node: MindNode, depth: int, sibling_idx: int, parent_y: float) -> None:
        nid = _next_id()
        x = base_x + dx * depth
        y = parent_y + dy * sibling_idx if depth > 0 else base_y
        indent = "      " + "  " * depth
        title = xml_escape(node.title, {'"': "&quot;"})
        note = xml_escape(node.note) if node.note else ""
        lines.append(
            f'{indent}<node id="{nid}" posx="{x}" posy="{y}" width="100" height="50"'
            ' side="right" fold="false" treesize="50" summarized="false"'
            ' layout="Horizontal" group="false">'
        )
        lines.append(f'{indent}  <nodename maxwidth="200"><text data="{title}"/></nodename>')
        lines.append(f"{indent}  <nodenote>{note}</nodenote>")
        if node.children:
            lines.append(f"{indent}  <nodes>")
            for i, child in enumerate(node.children):
                _emit(child, depth + 1, i, y)
            lines.append(f"{indent}  </nodes>")
        lines.append(f"{indent}</node>")

    _emit(root, 0, 0, base_y)
    nodes_xml = "\n".join(lines)
    return (
        '<?xml version="1.0"?>\n'
        '<minder version="1.16.2" parent-etag="0" etag="0">\n'
        '  <theme name="dark" label="Dark" index="1"/>\n'
        f"  <styles>{MINDER_STYLES}</styles>\n"
        "  <images/>\n"
        "  <nodes>\n"
        f"{nodes_xml}\n"
        "  </nodes>\n"
        "  <selected-nodes/>\n"
        "  <groups/>\n"
        "  <stickers/>\n"
        '  <nodelinks id="0"/>\n'
        "</minder>\n"
    )


def flatten(node: MindNode) -> list[MindNode]:
    out = [node]
    for c in node.children:
        out.extend(flatten(c))
    return out
