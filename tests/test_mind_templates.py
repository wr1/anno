"""Tests for bundled mind-map templates and the template loader.

Covers loading the `software` template into a MindNode tree, the root-title
override, the unknown-template error path, seed_minder, and that the tree
renders to valid Minder XML carrying section titles and their guiding notes.

Runs standalone (`python tests/test_mind_templates.py`) or under pytest.
"""

import tempfile
from pathlib import Path

from anno.mind.templates import TemplateNotFoundError, available_templates, load_template, seed_minder
from anno.mind.tree import tree_to_minder_xml

EXPECTED_SECTIONS = ["Aim", "Success", "Focus", "Approach", "Risks & Unknowns"]


def test_software_listed():
    assert "software" in available_templates()
    print("ok: software template is discoverable")


def test_software_sections_and_notes():
    tree = load_template("software")
    assert [c.title for c in tree.children] == EXPECTED_SECTIONS
    assert all(c.note.strip() for c in tree.children), "every section needs a guiding note"
    print("ok: software template has the expected sections, each with a note")


def test_root_title_override():
    assert load_template("software").title == "Project"
    assert load_template("software", root_title="myfeature").title == "myfeature"
    print("ok: root title defaults to template H1 and can be overridden")


def test_unknown_template_raises():
    try:
        load_template("definitely-not-a-template")
    except TemplateNotFoundError as exc:
        assert "available" in str(exc) and "software" in str(exc)
    else:
        raise AssertionError("expected TemplateNotFoundError for unknown template")
    print("ok: unknown template raises listing available templates")


def test_renders_to_minder_xml():
    xml = tree_to_minder_xml(load_template("software"))
    assert '<text data="Aim"/>' in xml
    # Guiding notes land in <nodenote> bodies.
    assert "<nodenote>What are we building" in xml
    assert xml.lstrip().startswith("<?xml")
    print("ok: software template renders to valid Minder XML with notes")


def test_seed_minder_without_template():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "roadmap.minder"
        seed_minder(path, root_title="roadmap")
        assert path.is_file()
        assert '<text data="roadmap"/>' in path.read_text()
    print("ok: seed_minder without template writes a single-root .minder")


def test_seed_minder_with_template():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "mm_20260101.minder"
        seed_minder(path, root_title="mm_20260101", template="software")
        text = path.read_text()
        assert '<text data="mm_20260101"/>' in text or '<text data="Aim"/>' in text
        assert '<text data="Aim"/>' in text
    print("ok: seed_minder with template writes section nodes and overrides root title")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"\nAll {len(tests)} tests passed.")
