"""Dumped mermaid with notes/comments still yields a renderable body."""

from anno.mermaid_dump import extract_sources, soften_comments, sources_for_preview

DUMP = """# pipeline

```mermaid
flowchart LR
  subgraph drp2
    drape_book
  end

where matdb?

  subgraph twod
    anba
add secfem
  end
  drape_book --> anba
```
"""


def test_extract_fenced_body():
    srcs = extract_sources(DUMP)
    assert len(srcs) == 1
    assert "flowchart LR" in srcs[0]
    assert "where matdb?" in srcs[0]


def test_extract_unclosed_fence():
    md = "```mermaid\nflowchart LR\n  a --> b\n"
    assert "a --> b" in extract_sources(md)[0]


def test_extract_raw_diagram_without_fence():
    md = "flowchart LR\n  a --> b\n"
    assert extract_sources(md) == ["flowchart LR\n  a --> b\n"]


def test_soften_turns_prose_into_percent_comments():
    src = extract_sources(DUMP)[0]
    out = soften_comments(src)
    assert "%% where matdb?" in out
    assert "%% add secfem" in out
    assert "drape_book --> anba" in out
    assert "subgraph twod" in out
    assert "    anba\n" in out or "    anba\r" in out or "    anba" in out.splitlines()


def test_soften_keeps_edges_and_bare_nodes():
    src = "flowchart LR\n  chord --> bem\n  anba\n"
    assert soften_comments(src) == src.rstrip("\n") or soften_comments(src) == src


def test_sources_for_preview_is_renderable_flowchart():
    body = sources_for_preview(DUMP)[0]
    assert body.lstrip().startswith("flowchart")
    assert "where matdb?" not in [ln.strip() for ln in body.splitlines() if not ln.strip().startswith("%%")]
    assert "add secfem" not in [ln.strip() for ln in body.splitlines() if not ln.strip().startswith("%%")]
