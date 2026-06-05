import re
from pathlib import Path
from typing import Optional

from anno.mind.tree import (
    MindNode,
    parse_headings_markdown,
    tree_to_headings_markdown,
)

SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._\- ]+")

SKIP_DIR_NAMES = {"__pycache__", "node_modules", "venv"}


def safe_dirname(title: str) -> str:
    """Map a node title to a filesystem-safe directory name."""
    name = SAFE_NAME_RE.sub("-", title).strip(" -.") or "untitled"
    return name


def is_skippable_dir(path: Path) -> bool:
    # Hidden dirs (.git, .venv, .ruff_cache, .mypy_cache, .pytest_cache,
    # .ipynb_checkpoints, …) and common build/cache names. Keeps these
    # out of the mind-map tree so the user only sees content folders.
    name = path.name
    return name.startswith(".") or name in SKIP_DIR_NAMES


def folder_to_tree(root_dir: Path, fs_depth: int) -> tuple[MindNode, set[Path]]:
    """Walk `root_dir` and build a mind-map tree.

    Subdirectories become child nodes. An `index.md` at *any* depth has its
    parsed subtree grafted onto its containing folder's node (its body
    becomes the folder node's note, its headings become deeper children).

    Returns `(tree, ingested_index_paths)`. The ingested paths are reported
    so callers can delete them before writing the canonical layout back —
    that's how content migrates cleanly when a user hand-places index.md
    above the leaf depth or when Minder reorganises the tree."""
    ingested: set[Path] = set()
    root = MindNode(title=root_dir.name)

    def _ingest(idx: Path, node: MindNode) -> None:
        sub_root = parse_headings_markdown(idx.read_text())
        # sub_root.title is by convention the folder name (decorative).
        # Lift sub_root.note onto this node's note (concatenating if both
        # already have content, which is rare).
        if sub_root.note:
            node.note = (node.note + "\n\n" + sub_root.note).strip() if node.note else sub_root.note
        node.children.extend(sub_root.children)
        ingested.add(idx.resolve())

    def _walk(dir_path: Path, parent: MindNode, depth: int) -> None:
        idx = dir_path / "index.md"
        if idx.exists():
            _ingest(idx, parent)
        for sub in sorted(p for p in dir_path.iterdir() if p.is_dir() and not is_skippable_dir(p)):
            node = MindNode(title=sub.name)
            parent.children.append(node)
            _walk(sub, node, depth + 1)

    if root_dir.exists():
        _walk(root_dir, root, 0)
    # fs_depth is currently used only by the writer; keep the read-side
    # tolerant so users can rearrange index.md placement freely.
    _ = fs_depth
    return root, ingested


def tree_to_folder(
    root: MindNode,
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

    def _walk(node: MindNode, dir_path: Path, depth: int) -> None:
        for child in node.children:
            child_dir = dir_path / safe_dirname(child.title)
            child_dir.mkdir(parents=True, exist_ok=True)
            used_dirs.add(child_dir.resolve())
            if depth + 1 < fs_depth:
                # Intermediate level: preserve the node's own note (if any) as
                # index.md so it survives a round-trip; children continue as
                # subfolders below. Without this, notes on non-leaf nodes get
                # silently dropped when Minder saves.
                if child.note:
                    idx_path = child_dir / "index.md"
                    idx_path.write_text(
                        tree_to_headings_markdown(MindNode(title=child.title, note=child.note), base_level=1)
                    )
                    written_index.add(idx_path.resolve())
                _walk(child, child_dir, depth + 1)
            else:
                # leaf-folder level: collapse descendants into index.md
                if child.children or child.note:
                    leaf_root = MindNode(title=child.title, note=child.note, children=child.children)
                    idx_path = child_dir / "index.md"
                    idx_path.write_text(tree_to_headings_markdown(leaf_root, base_level=1))
                    written_index.add(idx_path.resolve())

    # Note for the root itself: if Minder's root carries a non-empty note,
    # write it as <root_dir>/index.md so it survives a round-trip.
    if root.note:
        idx_path = root_dir / "index.md"
        idx_path.write_text(tree_to_headings_markdown(MindNode(title=root.title, note=root.note), base_level=1))
        written_index.add(idx_path.resolve())

    _walk(root, root_dir, 0)
    prune_empty_dirs(root_dir, used_dirs)
    return written_index


def folder_has_content(folder: Path) -> bool:
    """True iff `folder` looks like a populated folder-sync tree.

    Cheap top-level peek that mirrors what `folder_to_tree` would actually
    pick up: a non-skippable subdir, or an `index.md` at the root."""
    if not folder.exists():
        return False
    for p in folder.iterdir():
        if p.is_dir() and not is_skippable_dir(p):
            return True
        if p.is_file() and p.name == "index.md":
            return True
    return False


def prune_empty_dirs(root_dir: Path, keep: set[Path]) -> None:
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
