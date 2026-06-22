"""Load bundled mind-map templates into MindNode trees.

A template is a heading-style markdown file under ``templates/`` (e.g.
``software.md``). It is parsed with the same ``parse_headings_markdown`` used by
plan sync, so body text under each heading becomes that node's Minder note (the
guiding prompt). Drop another ``*.md`` file here to add a template — no code
changes needed.
"""

import sys
from pathlib import Path

from anno.mind.tree import MindNode, parse_headings_markdown

TEMPLATES_DIR = Path(__file__).parent / "templates"


def available_templates() -> list[str]:
    """Sorted names (stems) of the bundled template markdown files."""
    return sorted(p.stem for p in TEMPLATES_DIR.glob("*.md"))


def load_template(name_or_path: str, root_title: str = "") -> MindNode:
    """Resolve a template name (or path to an .md file) into a MindNode tree.

    A bundled name like ``software`` maps to ``templates/software.md``; an
    existing filesystem path is read directly. When ``root_title`` is given it
    overrides the template's H1 so the map's root is titled after its name.
    """
    candidate = Path(name_or_path).expanduser()
    if candidate.suffix == ".md" and candidate.is_file():
        path = candidate
    else:
        path = TEMPLATES_DIR / f"{name_or_path}.md"
    if not path.is_file():
        names = ", ".join(available_templates()) or "(none)"
        sys.exit(f"unknown template: {name_or_path}\navailable: {names}")
    tree = parse_headings_markdown(path.read_text())
    if root_title:
        tree.title = root_title
    return tree
