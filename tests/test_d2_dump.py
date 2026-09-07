"""Dumped D2 with notes/comments still yields a renderable body."""

from anno.d2_dump import extract_sources, find_object_span, soften_comments, sources_for_preview

DUMP = """# pipeline

direction: right
inputs -> group
group: {
  g_data: data
}

where matdb?

group2: {
  anba
add secfem
}
group -> group2
"""


def test_extract_raw_d2_is_the_whole_file():
    srcs = extract_sources(DUMP)
    assert len(srcs) == 1
    assert "direction: right" in srcs[0]
    assert "where matdb?" in srcs[0]


def test_extract_fenced_d2_body():
    md = "# title\n\n```d2\ninputs -> outputs\n```\n"
    srcs = extract_sources(md)
    assert len(srcs) == 1
    assert "inputs -> outputs" in srcs[0]
    assert "# title" not in srcs[0]


def test_extract_unclosed_d2_fence():
    md = "```d2\ninputs -> outputs\n"
    assert "inputs -> outputs" in extract_sources(md)[0]


def test_soften_turns_prose_into_hash_comments():
    src = extract_sources(DUMP)[0]
    out = soften_comments(src)
    assert "# where matdb?" in out
    assert "# add secfem" in out
    assert "group -> group2" in out
    assert "group2: {" in out
    assert "direction: right" in out


def test_soften_keeps_edges_and_containers():
    src = "inputs -> bem\nanba\n"
    assert "inputs -> bem" in soften_comments(src)
    assert "anba" in soften_comments(src)


def test_soften_preserves_md_block_with_pipe_in_body():
    src = "user: ||md\n  **once**\n  ssh x | bash\n||\na -> b\n"
    out = soften_comments(src)
    assert "user: ||md" in out
    assert "ssh x | bash" in out
    assert "# ssh" not in out
    assert out.splitlines()[3] == "||"
    assert "a -> b" in out


def test_find_shape_span_is_declaration_key():
    src = DUMP
    start, end = find_object_span(src, "group")
    assert src[start:end] == "group"
    # declaration `group: {`, not `inputs -> group` or `group -> group2`
    assert src[:start].count("\n") + 1 == 5


def test_find_nested_shape_prefers_child_under_parent():
    src = """Spark: {
  Harness: {
    label: x
  }
}
Harness: leftover
"""
    start, end = find_object_span(src, "Spark.Harness")
    assert src[start:end] == "Harness"
    assert src[:start].count("\n") + 1 == 2


def test_find_edge_span_from_connection_id():
    src = DUMP
    start, end = find_object_span(src, "(group -> group2)[0]")
    assert "->" in src[start:end]
    assert src[start:end].startswith("group")


def test_find_unknown_object_is_none():
    assert find_object_span(DUMP, "nope") is None


def test_find_edge_with_full_path_uses_leaf_names():
    src = "  Harness -> Follower: runs\n"
    start, end = find_object_span(src, "(Spark.Harness -> Spark.Follower)[0]")
    assert src[start:end].startswith("Harness -> Follower")


def test_sources_for_preview_is_renderable():
    body = sources_for_preview(DUMP)[0]
    assert "direction: right" in body
    assert "where matdb?" not in [ln.strip() for ln in body.splitlines() if not ln.strip().startswith("#")]
    assert "add secfem" not in [ln.strip() for ln in body.splitlines() if not ln.strip().startswith("#")]
