"""Local mermaid.js editor: live preview, save back to the .md. Format shim.

The HTTP sidecar, state files, and launch/reuse logic live in `anno.live`;
this module supplies the mermaid editor page and its state directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

from anno.live import LiveConfig, build_html
from anno.live import preview_url_if_running as _preview
from anno.live import run_live_editor as _run
from anno.live import serve_until_done as _serve
from anno.live import start_live_server as _start
from anno.live import write_state as _write_state_impl

_MM_CSS = r"""
  textarea {
    resize: none; border: 0; padding: 12px; outline: none;
    background: #161b22; color: #e6edf3; font: 13px/1.45 ui-monospace, monospace;
    flex: 0 0 auto; width: var(--split, 50%); min-width: 120px;
  }
  .block { margin-bottom: 24px; }
"""

_MM_EDITOR = r"""  <textarea id="src" spellcheck="false"></textarea>"""
_MM_PREVIEW = r"""  <div id="preview"></div>"""
_MM_HEAD = r"""<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>"""
_MM_SETUP = r"""mermaid.initialize({ startOnLoad: false, theme: "neutral", securityLevel: "loose" });"""
_MM_RENDER_JS = r"""function extractSources(md) {
  const out = [];
  const re = /```(?:mermaid)?[ \t]*\n([\s\S]*?)(?:```|$)/gi;
  let m;
  while ((m = re.exec(md))) out.push(m[1]);
  if (out.length) return out;
  const lines = md.split("\n");
  let i = 0;
  while (i < lines.length && (!lines[i].trim() || lines[i].trim().startsWith("#"))) i++;
  const body = lines.slice(i).join("\n");
  const first = (body.split("\n").find((ln) => ln.trim()) || "").trim();
  if (/^(flowchart|graph|sequenceDiagram|stateDiagram|classDiagram)\b/i.test(first)) return [body];
  return [];
}

let token = 0;
let lastGood = "";
async function render() {
  const mine = ++token;
  const codes = extractSources(src.value);
  if (!codes.length) {
    if (!lastGood) preview.innerHTML = "<p class=err>no mermaid fence</p>";
    return;
  }
  const bits = [];
  try {
    for (let i = 0; i < codes.length; i++) {
      const id = "m" + mine + "_" + i;
      const { svg } = await mermaid.render(id, codes[i]);
      if (mine !== token) return;
      bits.push(svg);
    }
  } catch (e) {
    if (mine !== token) return;
    setStatus(String(e).split("\n")[0], "warn");
    if (!lastGood) preview.innerHTML = "<pre class=err>" + String(e) + "</pre>";
    return;
  }
  if (mine !== token) return;
  preview.innerHTML = bits.map((s) => "<div class=block>" + s + "</div>").join("");
  lastGood = preview.innerHTML;
}

"""

LIVE_HTML = build_html(
    title="anno mermaid",
    kind="mermaid",
    head=_MM_HEAD,
    css=_MM_CSS,
    editor=_MM_EDITOR,
    preview=_MM_PREVIEW,
    status_hint="live preview — stays up; disk edits rerender",
    setup=_MM_SETUP,
    render_js=_MM_RENDER_JS,
    footer="renderSoon();",
)

MERMAID_LIVE = LiveConfig(
    kind="mermaid",
    html=LIVE_HTML,
    module="anno.mermaid_live",
    state_dir_env="ANNO_MERMAID_LIVE_DIR",
    state_subdir="mermaid-live",
)


def start_live_server(path: Path, preferred_port: int | None = None):
    return _start(MERMAID_LIVE, path, preferred_port)


def _write_state(path: Path, port: int) -> None:
    _write_state_impl(MERMAID_LIVE, path, port)


def preview_url_if_running(path: Path) -> str | None:
    return _preview(MERMAID_LIVE, path)


def serve_until_done(path: Path) -> str:
    return _serve(MERMAID_LIVE, path)


def run_live_editor(path: Path) -> bool:
    """Open (or reuse) a detached live preview. Returns immediately."""
    return _run(MERMAID_LIVE, path)


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: python -m anno.mermaid_live <file.md>")
    serve_until_done(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
