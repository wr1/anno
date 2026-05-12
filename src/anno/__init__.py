import base64
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape as _xml_escape

from treeparse import argument, cli, color_config, command, group, option
from treeparse.utils.color_config import ColorTheme

DEFAULT_NOTES_DIR = Path("notes") / "draw"
DEFAULT_SCREENSHOTS_DIR = Path.home() / "Pictures" / "Screenshots"
DEFAULT_MIND_DIR = Path("notes") / "mind"
DEFAULT_LOG_FILE = Path.home() / ".anno" / "log.jsonl"
DEFAULT_PARA_NOTES_DIR = Path("notes") / "para"
DEFAULT_NOTES_ROOT = Path("notes")
DEFAULT_PLANS_DIR = Path("notes") / "plans"
DEFAULT_FS_DEPTH = 3
MINDER = "com.github.phase1geo.minder"

EXPORT_DPI = 300
DEFAULT_FONT_SIZE = 30

# Force X11 backend to avoid Inkscape SIGSEGV on Wayland (known bug in 1.2.x)
_INKSCAPE_ENV = {**os.environ, "GDK_BACKEND": "x11"}


# --- activity log ---


def _log(action: str, path: Path) -> None:
    DEFAULT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "action": action,
        "file": str(path.resolve()),
        "type": path.suffix.lstrip("."),
    }
    with DEFAULT_LOG_FILE.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


# --- image helpers ---


def _image_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", data[16:24])
        return w, h
    if data[:2] == b"\xff\xd8":  # JPEG
        i = 2
        while i + 4 < len(data):
            if data[i] != 0xFF:
                break
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB):
                h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                return w, h
            length = struct.unpack(">H", data[i + 2 : i + 4])[0]
            i += 2 + length
    return 800, 600


def _embed_image_into_svg(img_path: Path, svg_path: Path) -> None:
    data = base64.b64encode(img_path.read_bytes()).decode()
    w, h = _image_dimensions(img_path)
    mime = "image/jpeg" if img_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:xlink="http://www.w3.org/1999/xlink"
     xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <sodipodi:namedview inkscape:document-units="px"/>
  <style>
    text, tspan {{ font-size: {DEFAULT_FONT_SIZE}px; }}
  </style>
  <image xlink:href="data:{mime};base64,{data}" x="0" y="0" width="{w}" height="{h}"/>
</svg>"""
    svg_path.write_text(svg)


def _export_png(svg_path: Path) -> Path:
    out = svg_path.with_suffix(".png")
    subprocess.run(
        [
            "inkscape",
            "--export-type=png",
            f"--export-dpi={EXPORT_DPI}",
            f"--export-filename={out}",
            str(svg_path),
        ],
        check=True,
        stderr=subprocess.DEVNULL,
        env=_INKSCAPE_ENV,
    )
    return out


def _run_inkscape_and_export(svg: Path) -> None:
    svg = svg.resolve()
    result = subprocess.run(["inkscape", str(svg)], env=_INKSCAPE_ENV)
    if result.returncode not in (0, -11):  # -11 = SIGSEGV (known on some builds on close)
        sys.exit(f"inkscape exited with code {result.returncode}")
    _log("ink_export", svg)
    out_png = _export_png(svg)
    _copy_to_clipboard(out_png)
    print(f"saved  : {svg}")
    print(f"saved  : {out_png}")
    print("copied : PNG to clipboard")


def _copy_to_clipboard(png_path: Path) -> None:
    if shutil.which("xclip"):
        subprocess.run(
            [
                "xclip",
                "-selection",
                "clipboard",
                "-t",
                "image/png",
                "-i",
                str(png_path),
            ],
            check=True,
        )
    elif sys.platform == "darwin":
        subprocess.run(
            [
                "osascript",
                "-e",
                f'set the clipboard to (read (POSIX file "{png_path}") as \xab class PNGf\xbb)',
            ],
            check=True,
        )
    else:
        print("clipboard copy not supported on this platform", file=sys.stderr)


def _copy_text_to_clipboard(text: str) -> None:
    if shutil.which("xclip"):
        subprocess.run(["xclip", "-selection", "clipboard"], input=text, text=True, check=True)
    elif sys.platform == "darwin":
        subprocess.run(["pbcopy"], input=text, text=True, check=True)
    else:
        print("clipboard copy not supported on this platform", file=sys.stderr)


# --- ink callbacks ---


def _make_blank_svg(path: Path, w: int = 1920, h: int = 1080) -> None:
    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <sodipodi:namedview inkscape:document-units="px"/>
  <style>
    text, tspan {{ font-size: {DEFAULT_FONT_SIZE}px; }}
  </style>
</svg>"""
    path.write_text(svg)


def cmd_ink_new(name: str = "", notes_dir: str = str(DEFAULT_NOTES_DIR)) -> None:
    out_dir = Path(notes_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if name:
        svg = out_dir / f"{Path(name).stem}.svg"
        if svg.exists():
            sys.exit(f"Already exists: {svg}")
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        svg = out_dir / f"fig_{ts}.svg"
    _make_blank_svg(svg)
    print(f"opening {svg}")
    _run_inkscape_and_export(svg)


def cmd_ink_open(name: str, notes_dir: str = str(DEFAULT_NOTES_DIR)) -> None:
    out_dir = Path(notes_dir)
    svg = out_dir / f"{Path(name).stem}.svg"
    if not svg.exists():
        sys.exit(f"Not found: {svg}")
    print(f"opening {svg}")
    _run_inkscape_and_export(svg)


def cmd_ink_fig(file: Optional[str] = None, notes_dir: str = str(DEFAULT_NOTES_DIR)) -> None:
    if file is None:
        scr_dir = DEFAULT_SCREENSHOTS_DIR
        pngs = sorted(scr_dir.glob("*.png"), key=lambda p: p.stat().st_mtime)
        if not pngs:
            sys.exit(f"No PNGs found in {scr_dir}")
        img_path = pngs[-1].resolve()
        print(f"latest : {img_path.name}")
    else:
        img_path = Path(file).resolve()
        if not img_path.exists():
            sys.exit(f"File not found: {img_path}")

    out_dir = Path(notes_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = img_path.stem.lower().replace(" ", "_")
    svg = out_dir / f"{stem}_{ts}.svg"

    _embed_image_into_svg(img_path, svg)
    print(f"opening {svg}")
    _run_inkscape_and_export(svg)


def cmd_ink_screen(
    notes_dir: str = str(DEFAULT_NOTES_DIR),
    screenshots_dir: str = str(DEFAULT_SCREENSHOTS_DIR),
) -> None:
    scr_dir = Path(screenshots_dir)
    pngs = sorted(scr_dir.glob("*.png"), key=lambda p: p.stat().st_mtime)
    if not pngs:
        sys.exit(f"No PNGs found in {scr_dir}")
    latest = pngs[-1]
    print(f"latest : {latest.name}")
    cmd_ink_fig(str(latest), notes_dir)


# --- minder helpers ---

_STYLE_COMMON = (
    ' branchmargin="100" branchradius="25" linktype="straight" linkwidth="4" linkarrow="false"'
    ' linkdash="solid" nodeborder="underlined" nodewidth="200" nodeborderwidth="4" nodefill="false"'
    ' nodemargin="8" nodepadding="6" nodefont="Sans 11" nodemarkup="true" connectiondash="dotted"'
    ' connectionlwidth="2" connectionarrow="fromto" connectionpadding="3" connectionfont="Sans 10"'
    ' connectiontwidth="100" calloutfont="Sans 12" calloutpadding="5" calloutptrwidth="20"'
    ' calloutptrlength="20"'
)
_STYLES = (
    '<style level="0" isset="false" branchmargin="100" branchradius="25" linktype="straight"'
    ' linkwidth="4" linkarrow="false" linkdash="solid" nodeborder="rounded" nodewidth="200"'
    ' nodeborderwidth="4" nodefill="false" nodemargin="10" nodepadding="10" nodefont="Sans 11"'
    ' nodemarkup="true" connectiondash="dotted" connectionlwidth="2" connectionarrow="fromto"'
    ' connectionpadding="3" connectionfont="Sans 10" connectiontwidth="100" calloutfont="Sans 12"'
    ' calloutpadding="5" calloutptrwidth="20" calloutptrlength="20"/>'
    + "".join(f'<style level="{i}" isset="false"{_STYLE_COMMON}/>' for i in range(1, 11))
)


def _make_minder_file(path: Path) -> None:
    path.write_text(
        '<?xml version="1.0"?>\n'
        '<minder version="1.16.2" parent-etag="0" etag="0">\n'
        '  <theme name="dark" label="Dark" index="1"/>\n'
        f"  <styles>{_STYLES}</styles>\n"
        "  <images/>\n"
        "  <nodes/>\n"
        "  <selected-nodes/>\n"
        "  <groups/>\n"
        "  <stickers/>\n"
        '  <nodelinks id="0"/>\n'
        "</minder>\n"
    )


def _run_minder(minder_file: Path, md_file: Path) -> None:
    _minder_launch_gui(minder_file)
    _log("mind_export", minder_file)
    _minder_export_markdown(minder_file, md_file)
    md = md_file.read_text() if md_file.exists() else ""
    _copy_text_to_clipboard(md)
    print(f"saved  : {minder_file}")
    print(f"saved  : {md_file}")
    print("copied : markdown to clipboard")


# Headless export keeps the dbus-run-session wrapper — it works fine there
# and side-steps singleton issues if Minder happens to be open in another
# window. The GUI launch deliberately does NOT use it: under at least some
# desktop sessions, the fresh dbus session can't reach
# org.freedesktop.secrets and xdg-desktop-portal hangs Minder's init.
def _minder_export_markdown(minder_file: Path, md_file: Path) -> None:
    subprocess.run(
        ["dbus-run-session", "--", MINDER, str(minder_file), "--export=markdown", str(md_file)],
        capture_output=True,
    )


def _minder_launch_gui(minder_file: Path) -> None:
    subprocess.run([MINDER, str(minder_file)], check=True)


# --- markdown ↔ mind-map tree ---


@dataclass
class _MindNode:
    title: str
    note: str = ""
    children: list["_MindNode"] = field(default_factory=list)


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
# Bullet items in Minder's markdown export: optional indent + "- " + title.
_BULLET_RE = re.compile(r"^(\s*)-\s+(.*?)\s*$")
# Note lines in Minder's markdown export: optional indent + "> " + text.
_NOTE_RE = re.compile(r"^(\s*)>\s?(.*)$")


def _parse_headings_markdown(text: str) -> _MindNode:
    """Parse heading-style markdown (`#`, `##`, …) into a single-rooted tree.

    Body lines under a heading become that node's note. A missing H1 is
    tolerated: a synthetic root titled "root" is created and all H1+ headings
    nest under it (rare; usually the caller writes a valid H1)."""
    root = _MindNode(title="root")
    stack: list[tuple[int, _MindNode]] = [(0, root)]
    note_buf: list[str] = []
    saw_h1 = False
    for raw in text.splitlines():
        m = _HEADING_RE.match(raw)
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
            node = _MindNode(title=title)
            parent.children.append(node)
            stack.append((level, node))
        else:
            note_buf.append(raw)
    if note_buf:
        stack[-1][1].note = "\n".join(note_buf).rstrip()
    # Strip leading blank lines from notes for cleanliness.
    _strip_note_blanks(root)
    return root


def _parse_bullets_markdown(text: str) -> _MindNode:
    """Parse Minder's bullet-list markdown export back into a tree.

    Minder writes:  `# Root`, then `  - child`, `    - grand`, with notes as
    `> text` lines indented to match their owner."""
    root = _MindNode(title="root")
    # Stack entries: (indent_cols, node). indent_cols == -1 marks the root.
    stack: list[tuple[int, _MindNode]] = [(-1, root)]
    note_target: Optional[_MindNode] = None
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
        h = _HEADING_RE.match(raw)
        if h and len(h.group(1)) == 1:
            _flush_note()
            root.title = h.group(2)
            note_target = root
            continue
        b = _BULLET_RE.match(raw)
        if b:
            _flush_note()
            indent = len(b.group(1))
            title = b.group(2)
            # Pop siblings/uncles deeper or equal to this indent.
            while stack and stack[-1][0] >= indent and stack[-1][0] != -1:
                stack.pop()
            parent = stack[-1][1] if stack else root
            node = _MindNode(title=title)
            parent.children.append(node)
            stack.append((indent, node))
            note_target = node
            continue
        n = _NOTE_RE.match(raw)
        if n:
            note_buf.append(n.group(2))
            continue
        # Anything else (paragraph text) attaches to the most recent target.
        if note_target is not None:
            note_buf.append(raw.lstrip())
    _flush_note()
    _strip_note_blanks(root)
    return root


def _strip_note_blanks(node: _MindNode) -> None:
    node.note = node.note.strip("\n")
    for c in node.children:
        _strip_note_blanks(c)


def _tree_to_headings_markdown(root: _MindNode, base_level: int = 1) -> str:
    """Render a tree back to heading-style markdown.

    `base_level` controls the H-level used for the root (1 for top-level,
    higher when splicing under a deeper heading)."""
    out: list[str] = []

    def _walk(node: _MindNode, level: int) -> None:
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


# --- markdown → Minder XML ---


def _tree_to_minder_xml(root: _MindNode) -> str:
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

    def _emit(node: _MindNode, depth: int, sibling_idx: int, parent_y: float) -> None:
        nid = _next_id()
        x = base_x + dx * depth
        y = parent_y + dy * sibling_idx if depth > 0 else base_y
        indent = "      " + "  " * depth
        title = _xml_escape(node.title, {'"': "&quot;"})
        note = _xml_escape(node.note) if node.note else ""
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
        f"  <styles>{_STYLES}</styles>\n"
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


# --- folder ↔ tree ---


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._\- ]+")


def _safe_dirname(title: str) -> str:
    """Map a node title to a filesystem-safe directory name."""
    name = _SAFE_NAME_RE.sub("-", title).strip(" -.") or "untitled"
    return name


def _folder_to_tree(root_dir: Path, fs_depth: int) -> tuple[_MindNode, set[Path]]:
    """Walk `root_dir` and build a mind-map tree.

    Subdirectories become child nodes. An `index.md` at *any* depth has its
    parsed subtree grafted onto its containing folder's node (its body
    becomes the folder node's note, its headings become deeper children).

    Returns `(tree, ingested_index_paths)`. The ingested paths are reported
    so callers can delete them before writing the canonical layout back —
    that's how content migrates cleanly when a user hand-places index.md
    above the leaf depth or when Minder reorganises the tree."""
    ingested: set[Path] = set()
    root = _MindNode(title=root_dir.name)

    def _ingest(idx: Path, node: _MindNode) -> None:
        sub_root = _parse_headings_markdown(idx.read_text())
        # sub_root.title is by convention the folder name (decorative).
        # Lift sub_root.note onto this node's note (concatenating if both
        # already have content, which is rare).
        if sub_root.note:
            node.note = (node.note + "\n\n" + sub_root.note).strip() if node.note else sub_root.note
        node.children.extend(sub_root.children)
        ingested.add(idx.resolve())

    def _walk(dir_path: Path, parent: _MindNode, depth: int) -> None:
        idx = dir_path / "index.md"
        if idx.exists():
            _ingest(idx, parent)
        for sub in sorted(p for p in dir_path.iterdir() if p.is_dir()):
            node = _MindNode(title=sub.name)
            parent.children.append(node)
            _walk(sub, node, depth + 1)

    if root_dir.exists():
        _walk(root_dir, root, 0)
    # fs_depth is currently used only by the writer; keep the read-side
    # tolerant so users can rearrange index.md placement freely.
    _ = fs_depth
    return root, ingested


def _tree_to_folder(
    root: _MindNode,
    root_dir: Path,
    fs_depth: int,
    delete_first: Optional[set[Path]] = None,
) -> set[Path]:
    """Write a tree out to `root_dir` as folders + index.md files.

    Nodes at depth 1..fs_depth become folders. A node at depth fs_depth with
    its own children (or a non-empty note) writes those descendants into
    `<folder>/index.md` as a heading-style document. Pass `delete_first` to
    remove a set of pre-known stale index.md paths before writing — callers
    use this to migrate ingested-from-elsewhere content cleanly."""
    root_dir.mkdir(parents=True, exist_ok=True)
    if delete_first:
        for p in delete_first:
            if p.exists():
                p.unlink()
    written_index: set[Path] = set()
    used_dirs: set[Path] = {root_dir.resolve()}

    def _walk(node: _MindNode, dir_path: Path, depth: int) -> None:
        for child in node.children:
            child_dir = dir_path / _safe_dirname(child.title)
            child_dir.mkdir(parents=True, exist_ok=True)
            used_dirs.add(child_dir.resolve())
            if depth + 1 < fs_depth:
                # Intermediate level: preserve the node's own note (if any) as
                # index.md so it survives a round-trip; children continue as
                # subfolders below. Without this, notes on non-leaf nodes get
                # silently dropped when Minder saves.
                if child.note:
                    idx_path = child_dir / "index.md"
                    idx_path.write_text(_tree_to_headings_markdown(
                        _MindNode(title=child.title, note=child.note), base_level=1
                    ))
                    written_index.add(idx_path.resolve())
                _walk(child, child_dir, depth + 1)
            else:
                # leaf-folder level: collapse descendants into index.md
                if child.children or child.note:
                    leaf_root = _MindNode(
                        title=child.title, note=child.note, children=child.children
                    )
                    idx_path = child_dir / "index.md"
                    idx_path.write_text(_tree_to_headings_markdown(leaf_root, base_level=1))
                    written_index.add(idx_path.resolve())

    # Note for the root itself: if Minder's root carries a non-empty note,
    # write it as <root_dir>/index.md so it survives a round-trip.
    if root.note:
        idx_path = root_dir / "index.md"
        idx_path.write_text(_tree_to_headings_markdown(
            _MindNode(title=root.title, note=root.note), base_level=1
        ))
        written_index.add(idx_path.resolve())

    _walk(root, root_dir, 0)
    _prune_empty_dirs(root_dir, used_dirs)
    return written_index


def _prune_empty_dirs(root_dir: Path, keep: set[Path]) -> None:
    """Remove directories under `root_dir` that we no longer use AND that
    contain no user-managed files (anno only owns `index.md` — anything else
    in a dir keeps it alive)."""
    # Walk bottom-up so we can prune nested dirs that empty out as we go.
    for path in sorted(
        (p for p in root_dir.rglob("*") if p.is_dir()),
        key=lambda p: len(p.parts),
        reverse=True,
    ):
        if path.resolve() in keep:
            continue
        try:
            path.rmdir()
        except OSError:
            # non-empty (user has other files in there); leave it.
            pass


# --- smart-sync runners ---


def _resolve_open_target(
    name: str,
    mind_dir: Path,
    notes_root: Path,
    plans_dir: Path,
) -> tuple[str, Path]:
    """Return (mode, path). Mode is "legacy", "plan", or "folder".

    Resolution order:
      1. *.minder suffix     → legacy at <mind_dir>/<name>
      2. plans_dir/<name>.md → plan smart sync
      3. otherwise           → folder smart sync at notes_root/<name>/
         (the directory is created on demand if it doesn't exist).

    Notes:
      - A pre-existing `<mind_dir>/<name>.minder` is intentionally ignored
        here — to open one, pass the name with the `.minder` suffix
        (e.g. `anno mind open foo.minder`). This keeps the bare-name path
        unambiguous and reserves it for the markdown-source-of-truth flow.
    """
    if name.endswith(".minder"):
        return ("legacy", mind_dir / name)
    plan_md = plans_dir / f"{name}.md"
    if plan_md.is_file():
        return ("plan", plan_md.resolve())
    folder = notes_root / name
    legacy = mind_dir / f"{name}.minder"
    if not folder.exists() and legacy.is_file():
        print(
            f"note   : a legacy {legacy} exists. To open it directly, run\n"
            f"         `anno mind open {name}.minder`. Continuing with folder\n"
            f"         sync at {folder}/ — created fresh."
        )
    return ("folder", folder.resolve())


def _run_minder_smart_sync_plan(plan_md: Path, copy_clipboard: bool) -> None:
    print(f"mode   : plan sync ({plan_md})")
    with tempfile.TemporaryDirectory(prefix="anno-plan-") as td:
        tmp_minder = Path(td) / f"{plan_md.stem}.minder"
        body = plan_md.read_text() if plan_md.exists() else ""
        if body.strip():
            tree = _parse_headings_markdown(body)
            tmp_minder.write_text(_tree_to_minder_xml(tree))
            print(f"import : {len(_flatten(tree)) - 1} nodes from {plan_md.name}")
        else:
            # Fresh plan: seed with the stem as the root title.
            seed = _MindNode(title=plan_md.stem)
            tmp_minder.write_text(_tree_to_minder_xml(seed))
            print(f"import : empty plan, seeded root '{plan_md.stem}'")
        _minder_launch_gui(tmp_minder)
        _log("mind_export", tmp_minder)
        exported_md = tmp_minder.with_suffix(".md")
        _minder_export_markdown(tmp_minder, exported_md)
        exported = exported_md.read_text() if exported_md.exists() else ""
        out_tree = _parse_bullets_markdown(exported) if exported else _MindNode(title=plan_md.stem)
        plan_md.parent.mkdir(parents=True, exist_ok=True)
        plan_md.write_text(_tree_to_headings_markdown(out_tree))
        print(f"saved  : {plan_md}")
        if copy_clipboard:
            _copy_text_to_clipboard(plan_md.read_text())
            print("copied : markdown to clipboard")


def _run_minder_smart_sync_folder(root_dir: Path, fs_depth: int, copy_clipboard: bool) -> None:
    print(f"mode   : folder sync ({root_dir}, fs-depth={fs_depth})")
    tree_in, ingested = _folder_to_tree(root_dir, fs_depth)
    with tempfile.TemporaryDirectory(prefix="anno-folder-") as td:
        tmp_minder = Path(td) / f"{root_dir.name}.minder"
        tmp_minder.write_text(_tree_to_minder_xml(tree_in))
        print(f"import : {len(_flatten(tree_in)) - 1} nodes from {root_dir}")
        _minder_launch_gui(tmp_minder)
        _log("mind_export", tmp_minder)
        exported_md = tmp_minder.with_suffix(".md")
        _minder_export_markdown(tmp_minder, exported_md)
        exported = exported_md.read_text() if exported_md.exists() else ""
        out_tree = _parse_bullets_markdown(exported) if exported else _MindNode(title=root_dir.name)
        # `ingested` are the index.md paths we read on entry. Deleting them
        # before writing lets us migrate content to the canonical leaf-depth
        # layout cleanly; the writer will recreate index.md where needed.
        _tree_to_folder(out_tree, root_dir, fs_depth, delete_first=ingested)
        print(f"saved  : {root_dir}/ ({len(_flatten(out_tree)) - 1} nodes)")
        if copy_clipboard:
            _copy_text_to_clipboard(_tree_to_headings_markdown(out_tree))
            print("copied : markdown to clipboard")


def _flatten(node: _MindNode) -> list[_MindNode]:
    out = [node]
    for c in node.children:
        out.extend(_flatten(c))
    return out


# --- mind callbacks ---


def cmd_mind_new(name: str = "", mind_dir: str = str(DEFAULT_MIND_DIR)) -> None:
    out_dir = Path(mind_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if name:
        minder_file = out_dir / f"{Path(name).stem}.minder"
        if minder_file.exists():
            sys.exit(f"Already exists: {minder_file}")
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = f"mm_{ts}"
        minder_file = out_dir / f"{stem}.minder"
    md_file = minder_file.with_suffix(".md")
    _make_minder_file(minder_file)
    _run_minder(minder_file, md_file)


def cmd_mind_open(
    name: str,
    mind_dir: str = str(DEFAULT_MIND_DIR),
    notes_root: str = str(DEFAULT_NOTES_ROOT),
    plans_dir: str = str(DEFAULT_PLANS_DIR),
    fs_depth: int = DEFAULT_FS_DEPTH,
    no_clipboard: bool = False,
) -> None:
    mode, target = _resolve_open_target(
        name,
        Path(mind_dir).resolve(),
        Path(notes_root).resolve(),
        Path(plans_dir).resolve(),
    )
    copy_clipboard = not no_clipboard
    if mode == "legacy":
        print(f"mode   : legacy ({target})")
        md_file = target.with_suffix(".md")
        _run_minder(target, md_file)
    elif mode == "plan":
        _run_minder_smart_sync_plan(target, copy_clipboard)
    else:
        _run_minder_smart_sync_folder(target, fs_depth, copy_clipboard)


# --- list callback ---


def cmd_list(notes_dir: str = str(DEFAULT_NOTES_DIR), mind_dir: str = str(DEFAULT_MIND_DIR)) -> None:
    from rich.console import Console
    from rich.table import Table

    svgs = (
        sorted(Path(notes_dir).glob("*.svg"), key=lambda p: p.stat().st_mtime, reverse=True)
        if Path(notes_dir).exists()
        else []
    )
    minders = (
        sorted(
            Path(mind_dir).glob("*.minder"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if Path(mind_dir).exists()
        else []
    )

    if not svgs and not minders:
        print("No annotations found.")
        return

    console = Console()

    def _render(label: str, files: list) -> None:
        if not files:
            return
        t = Table(title=label, show_header=False, box=None, padding=(0, 2))
        t.add_column("mtime", style="rgb(139,148,158)")
        t.add_column("name", style="rgb(165,214,255)")
        t.add_column("size", style="rgb(139,148,158)")
        for f in files:
            st = f.stat()
            mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
            size_kb = st.st_size // 1024
            uri = f.resolve().as_uri()
            t.add_row(mtime, f"[link={uri}]{f.name}[/link]", f"{size_kb} KB")
        console.print(t)

    _render(f"Annotations  {notes_dir}", svgs)
    _render(f"Mind maps    {mind_dir}", minders)


# --- log callback ---


def cmd_log(
    date: Optional[str] = None,
    log_file: str = str(DEFAULT_LOG_FILE),
) -> None:
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    from rich.console import Console
    from rich.table import Table

    log_path = Path(log_file)
    if not log_path.exists():
        print("No activity log found.")
        return

    entries = []
    for raw in log_path.read_text().splitlines():
        try:
            e = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if e.get("ts", "").startswith(date):
            entries.append(e)

    console = Console()

    if not entries:
        console.print(f"No activity on {date}.")
        return

    t = Table(title=f"Activity  {date}", show_header=True, box=None, padding=(0, 2))
    t.add_column("time", style="rgb(139,148,158)")
    t.add_column("action", style="rgb(165,214,255)")
    t.add_column("file", style="rgb(204,204,204)")
    for e in entries:
        time_part = e["ts"].split("T")[-1] if "T" in e["ts"] else e["ts"]
        file_path = Path(e.get("file", ""))
        uri = file_path.as_uri()
        md_path = file_path.with_suffix(".md")
        if file_path.suffix == ".minder" and md_path.exists():
            cell = f"[link={uri}]{file_path.stem}[/link]  [link={md_path.as_uri()}].md[/link]"
        else:
            cell = f"[link={uri}]{file_path.stem}[/link]"
        t.add_row(time_part, e.get("action", ""), cell)
    console.print(t)


# --- cam callback ---


def cmd_cam(notes_dir: str = str(DEFAULT_NOTES_DIR)) -> None:
    for tool in ("ffplay", "ffmpeg", "convert"):
        if not shutil.which(tool):
            sys.exit(f"cam requires {tool!r} on PATH (install ffmpeg + imagemagick)")

    device = "/dev/video0"
    print("Webcam preview open — press any key or click to capture.")
    subprocess.run(
        [
            "ffplay",
            "-loglevel",
            "error",
            "-f",
            "v4l2",
            "-input_format",
            "mjpeg",
            "-video_size",
            "1920x1080",
            "-i",
            device,
            "-window_title",
            "anno cam — any key / click to capture",
            "-exitonkeydown",
            "-exitonmousedown",
        ],
        stderr=subprocess.DEVNULL,
    )

    out_dir = Path(notes_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    orig_path = out_dir / f"cam_{ts}.jpg"

    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "v4l2",
            "-input_format",
            "mjpeg",
            "-video_size",
            "1920x1080",
            "-i",
            device,
            "-frames:v",
            "1",
            "-y",
            str(orig_path),
        ],
        check=True,
    )
    _log("cam_capture", orig_path)
    print(f"saved  : {orig_path}")

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        subprocess.run(
            [
                "convert",
                str(orig_path),
                "-normalize",
                "-fuzz",
                "5%",
                "-trim",
                "+repage",
                str(tmp_path),
            ],
            check=True,
        )
        _copy_to_clipboard(tmp_path)
        print("copied : enhanced PNG to clipboard")
    finally:
        tmp_path.unlink(missing_ok=True)


def _launch_paraview(mesh_paths: list[Path], notes_dir: str) -> None:
    notes_path = Path(notes_dir)
    notes_path.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["ANNO_NOTES_DIR"] = str(notes_path.resolve())
    env["ANNO_MESH_FILES"] = ":".join(str(p) for p in mesh_paths)

    pv_dir = Path(__file__).parent / "paraview"
    env["ANNO_EXPORT_PY"] = str(pv_dir / "export.py")

    subprocess.Popen(["paraview", "--pyscript", str(pv_dir / "startup.py")], env=env)
    for p in mesh_paths:
        _log("para_open", p)
        print(f"ParaView launched  : {p}")
    print(f"ANNO_NOTES_DIR     : {env['ANNO_NOTES_DIR']}")


def _last_para_mesh(name: Optional[str] = None) -> Optional[Path]:
    if not DEFAULT_LOG_FILE.exists():
        return None
    entries = [json.loads(line) for line in DEFAULT_LOG_FILE.read_text().splitlines() if line.strip()]
    para = [e for e in entries if e.get("action") == "para_open"]
    if name:
        para = [e for e in para if Path(e["file"]).stem == name]
    return Path(para[-1]["file"]) if para else None


def cmd_para_new(files, notes_dir: str = str(DEFAULT_PARA_NOTES_DIR)) -> None:
    if not shutil.which("paraview"):
        sys.exit("para requires 'paraview' on PATH")
    mesh_paths = []
    for f in files:
        p = Path(f).resolve()
        if not p.exists():
            sys.exit(f"File not found: {p}")
        mesh_paths.append(p)
    _launch_paraview(mesh_paths, notes_dir)


def cmd_para_open(name: Optional[str] = None, notes_dir: str = str(DEFAULT_PARA_NOTES_DIR)) -> None:
    if not shutil.which("paraview"):
        sys.exit("para requires 'paraview' on PATH")
    mesh_path = _last_para_mesh(name)
    if mesh_path is None:
        msg = f"No para session found for {name!r}" if name else "No previous para session in log"
        sys.exit(msg)
    if not mesh_path.exists():
        sys.exit(f"Mesh no longer exists: {mesh_path}")
    _launch_paraview([mesh_path], notes_dir)


# --- CLI definition ---

app = cli(
    name="anno",
    help=(
        "Quick CLI for annotating figures in Inkscape, building mind maps in Minder, "
        "capturing from webcam, and annotating 3D meshes in ParaView."
    ),
    line_connect=True,
    show_types=False,
    show_defaults=True,
    theme=ColorTheme.GITHUB,
    colors=color_config.from_theme(ColorTheme.GITHUB),
)

_notes_option = option(
    flags=["--notes-dir", "-d"],
    dest="notes_dir",
    arg_type=str,
    default=str(DEFAULT_NOTES_DIR),
    help="Directory to save SVGs",
    sort_key=10,
)
_screenshots_option = option(
    flags=["--screenshots-dir", "-s"],
    dest="screenshots_dir",
    arg_type=str,
    default=str(DEFAULT_SCREENSHOTS_DIR),
    help="Directory to search for screenshots",
    sort_key=11,
)
_mind_dir_option = option(
    flags=["--mind-dir", "-m"],
    dest="mind_dir",
    arg_type=str,
    default=str(DEFAULT_MIND_DIR),
    help="Directory for legacy .minder files",
    sort_key=10,
)
_notes_root_option = option(
    flags=["--notes-root"],
    dest="notes_root",
    arg_type=str,
    default=str(DEFAULT_NOTES_ROOT),
    help="Root for folder-sync lookup (notes/<name>/)",
    sort_key=11,
)
_plans_dir_option = option(
    flags=["--plans-dir"],
    dest="plans_dir",
    arg_type=str,
    default=str(DEFAULT_PLANS_DIR),
    help="Directory holding single-file plan .md sources",
    sort_key=12,
)
_fs_depth_option = option(
    flags=["--fs-depth"],
    dest="fs_depth",
    arg_type=int,
    default=DEFAULT_FS_DEPTH,
    help="Folder-sync: # of child layers stored as folders (deeper → index.md)",
    sort_key=13,
)
_no_clipboard_option = option(
    flags=["--no-clipboard"],
    dest="no_clipboard",
    arg_type=bool,
    default=False,
    help="Skip copying exported markdown to the clipboard",
    sort_key=14,
)
_para_notes_option = option(
    flags=["--notes-dir", "-d"],
    dest="notes_dir",
    arg_type=str,
    default=str(DEFAULT_PARA_NOTES_DIR),
    help="Directory to save ParaView exports",
    sort_key=10,
)
_log_option = option(
    flags=["--log-file", "-l"],
    dest="log_file",
    arg_type=str,
    default=str(DEFAULT_LOG_FILE),
    help="Path to the JSONL activity log",
    sort_key=12,
)

# ink group
ink_group = group(
    name="ink",
    help="Annotate figures with Inkscape. On close: saves SVG, copies result as PNG to clipboard.",
)
ink_group.commands.append(
    command(
        name="new",
        help="Open a new blank SVG in Inkscape.",
        callback=cmd_ink_new,
        arguments=[argument(name="name", arg_type=str, nargs="?", default=None, sort_key=0)],
        options=[_notes_option],
    )
)
ink_group.commands.append(
    command(
        name="open",
        help="Open an existing SVG annotation in Inkscape.",
        callback=cmd_ink_open,
        arguments=[argument(name="name", arg_type=str, sort_key=0)],
        options=[_notes_option],
    )
)
ink_group.commands.append(
    command(
        name="fig",
        help="Open a figure (PNG or JPG) in Inkscape.",
        callback=cmd_ink_fig,
        arguments=[argument(name="file", arg_type=str, nargs="?", default=None, sort_key=0)],
        options=[_notes_option],
    )
)
ink_group.commands.append(
    command(
        name="screen",
        help="Open the latest screenshot in Inkscape.",
        callback=cmd_ink_screen,
        options=[_notes_option, _screenshots_option],
    )
)
app.subgroups.append(ink_group)

# mind group
mind_group = group(
    name="mind",
    help="Mind maps with Minder. On close: exports markdown, copies to clipboard.",
)
mind_group.commands.append(
    command(
        name="new",
        help="Open a new blank mind map in Minder.",
        callback=cmd_mind_new,
        arguments=[argument(name="name", arg_type=str, nargs="?", default=None, sort_key=0)],
        options=[_mind_dir_option],
    )
)
mind_group.commands.append(
    command(
        name="open",
        help=(
            "Open a mind map by name. Resolves in order: notes/<name>/ (folder sync), "
            "notes/plans/<name>.md (plan sync), notes/mind/<name>.minder (legacy)."
        ),
        callback=cmd_mind_open,
        arguments=[argument(name="name", arg_type=str, sort_key=0)],
        options=[
            _mind_dir_option,
            _notes_root_option,
            _plans_dir_option,
            _fs_depth_option,
            _no_clipboard_option,
        ],
    )
)
app.subgroups.append(mind_group)

# cam
app.commands.append(
    command(
        name="cam",
        help=(
            "Capture from webcam. Any key/click in preview window shoots; saves original, "
            "copies enhanced PNG to clipboard. Requires ffmpeg + imagemagick."
        ),
        callback=cmd_cam,
        options=[_notes_option],
    )
)

# para group
para_group = group(
    name="para",
    help="3D mesh annotation in ParaView. Exports selections as Markdown + screenshot to notes/para/.",
)
para_group.commands.append(
    command(
        name="new",
        help="Open one or more meshes in ParaView.",
        callback=cmd_para_new,
        arguments=[argument(name="files", nargs="+", sort_key=0)],
        options=[_para_notes_option],
    )
)
para_group.commands.append(
    command(
        name="open",
        help="Reopen last (or named) mesh from activity log.",
        callback=cmd_para_open,
        arguments=[argument(name="name", arg_type=str, nargs="?", default=None, sort_key=0)],
        options=[_para_notes_option],
    )
)
app.subgroups.append(para_group)

# list
app.commands.append(
    command(
        name="list",
        help="List saved annotations and mind maps.",
        callback=cmd_list,
        options=[_notes_option, _mind_dir_option],
    )
)

# log
app.commands.append(
    command(
        name="log",
        help="Show activity log for a given date (default: today).",
        callback=cmd_log,
        arguments=[argument(name="date", arg_type=str, nargs="?", default=None, sort_key=0)],
        options=[_log_option],
    )
)


def main() -> None:
    app.run()


if __name__ == "__main__":
    main()
