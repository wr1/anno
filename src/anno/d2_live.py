"""Local D2 editor: live preview via @terrastruct/d2 WASM. Format shim.

The HTTP sidecar, state files, and launch/reuse logic live in `anno.live`;
this module supplies the D2 editor page and the format's state directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

from anno.live import LiveConfig, build_html
from anno.live import preview_url_if_running as _preview
from anno.live import run_live_editor as _run
from anno.live import running_live_paths as _running
from anno.live import serve_until_done as _serve
from anno.live import start_live_server as _start
from anno.live import write_state as _write_state_impl

_D2_CSS = r"""
  #bar .zoom button {
    background: #21262d; padding: 6px 10px;
  }
  #bar .zoom button:hover { background: #30363d; }
  #zoomPct { color: #8b949e; min-width: 3.5em; }
  #editor {
    position: relative; flex: 0 0 auto; width: var(--split, 50%);
    min-width: 120px; min-height: 0; background: #161b22;
  }
  #hl, #src {
    position: absolute; inset: 0; margin: 0; border: 0; padding: 12px;
    font: 13px/1.45 ui-monospace, Menlo, Consolas, monospace;
    white-space: pre; overflow: auto; tab-size: 2; box-sizing: border-box;
  }
  #hl {
    pointer-events: none; color: #e6edf3; z-index: 0;
    overflow: hidden;
  }
  #src {
    resize: none; outline: none; background: transparent;
    color: transparent; caret-color: #e6edf3; z-index: 1;
  }
  #src::selection { background: rgba(56, 139, 253, 0.35); color: transparent; }
  .tok-c { color: #8b949e; }
  .tok-s { color: #a5d6ff; }
  .tok-k { color: #ff7b72; }
  .tok-e { color: #d2a8ff; }
  .tok-n { color: #79c0ff; }
  .tok-p { color: #8b949e; }
  .tok-i { color: #7ee787; }
  #preview {
    overflow: hidden; padding: 0; position: relative; cursor: grab;
    touch-action: none; overscroll-behavior: none;
  }
  #preview.panning { cursor: grabbing; }
  #stage {
    position: absolute; left: 0; top: 0; transform-origin: 0 0;
  }
  #preview svg { max-width: none; max-height: none; display: block; }
  #stage g { cursor: pointer; }
"""

_D2_EDITOR = r"""  <div id="editor">
    <pre id="hl" aria-hidden="true"></pre>
    <textarea id="src" spellcheck="false" wrap="off"></textarea>
  </div>"""
_D2_PREVIEW = r"""  <div id="preview"><div id="stage"></div></div>"""
_D2_BAR_EXTRA = r"""  <span class="zoom">
    <button type="button" id="zoomOut" title="zoom out">−</button>
    <button type="button" id="zoomFit" title="fit diagram">Fit</button>
    <button type="button" id="zoomIn" title="zoom in">+</button>
    <span id="zoomPct">100%</span>
  </span>"""
_D2_REFS = r"""const stage = document.getElementById("stage");
const zoomPct = document.getElementById("zoomPct");
const hl = document.getElementById("hl");"""
_D2_RENDER_JS = r"""function escHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function highlightD2(text) {
  const kw = new RegExp(
    "^(direction|shape|label|style|class|classes|near|link|tooltip|icon|" +
      "constraint|width|height|vars|layers|scenarios|steps|opacity|fill|" +
      "stroke|font-color|font-size|bold|italic|underline|shadow|multiple|" +
      "animated|filled)\\b"
  );
  let i = 0;
  let out = "";
  const n = text.length;
  while (i < n) {
    const ch = text[i];
    if (ch === "#") {
      let j = text.indexOf("\n", i);
      if (j < 0) j = n;
      out += '<span class="tok-c">' + escHtml(text.slice(i, j)) + "</span>";
      i = j;
      continue;
    }
    if (ch === '"') {
      let j = i + 1;
      while (j < n && text[j] !== '"') {
        if (text[j] === "\\") j++;
        j++;
      }
      if (j < n) j++;
      out += '<span class="tok-s">' + escHtml(text.slice(i, j)) + "</span>";
      i = j;
      continue;
    }
    if (ch === "|") {
      const j = text.indexOf("|", i + 1);
      const end = j < 0 ? n : j + 1;
      out += '<span class="tok-s">' + escHtml(text.slice(i, end)) + "</span>";
      i = end;
      continue;
    }
    if (text.startsWith("<->", i)) {
      out += '<span class="tok-e">&lt;-&gt;</span>';
      i += 3;
      continue;
    }
    if (text.startsWith("->", i) || text.startsWith("<-", i) || text.startsWith("--", i)) {
      out += '<span class="tok-e">' + escHtml(text.slice(i, i + 2)) + "</span>";
      i += 2;
      continue;
    }
    if (/[A-Za-z_]/.test(ch)) {
      let j = i + 1;
      while (j < n && /[\w.-]/.test(text[j])) j++;
      const word = text.slice(i, j);
      const cls = kw.test(word) ? "tok-k" : "tok-i";
      out += '<span class="' + cls + '">' + escHtml(word) + "</span>";
      i = j;
      continue;
    }
    if (/[0-9]/.test(ch)) {
      let j = i + 1;
      while (j < n && /[0-9.]/.test(text[j])) j++;
      out += '<span class="tok-n">' + escHtml(text.slice(i, j)) + "</span>";
      i = j;
      continue;
    }
    if ("{}[]():".includes(ch)) {
      out += '<span class="tok-p">' + escHtml(ch) + "</span>";
      i++;
      continue;
    }
    out += escHtml(ch);
    i++;
  }
  return out + "\n";
}

function syncHlScroll() {
  hl.scrollTop = src.scrollTop;
  hl.scrollLeft = src.scrollLeft;
}

function paintHighlight() {
  hl.innerHTML = highlightD2(src.value);
  syncHlScroll();
}

paintHighlight();
src.addEventListener("scroll", syncHlScroll);
const d2 = new D2();

function extractSources(text) {
  const out = [];
  const re = /```d2[ \t]*\n([\s\S]*?)(?:```|$)/gi;
  let m;
  while ((m = re.exec(text))) out.push(m[1]);
  if (out.length) return out;
  return [text];
}

function soften(src) {
  const openRe = /^(?:[A-Za-z_][\w.-]*(?:\.[A-Za-z_][\w.-]*)*\s*:)?\s*(\|+)([A-Za-z][\w-]*)?\s*$/;
  const lines = src.split("\n");
  const out = [];
  let delim = null;
  for (const line of lines) {
    const stripped = line.trim();
    if (delim) {
      out.push(line);
      if (stripped.startsWith(delim)) {
        const rest = stripped.slice(delim.length).trimStart();
        if (!rest || rest.startsWith("{")) delim = null;
      }
      continue;
    }
    const opened = openRe.exec(stripped);
    if (opened) {
      delim = opened[1];
      out.push(line);
      continue;
    }
    if (!stripped || stripped.startsWith("#") || stripped.startsWith("}")) {
      out.push(line);
      continue;
    }
    if (/<->|<-|->|--/.test(stripped)) { out.push(line); continue; }
    if (/^[A-Za-z_][\w.-]*(\.[A-Za-z_][\w.-]*)*\s*:/.test(stripped)) { out.push(line); continue; }
    if (/^[A-Za-z_][\w.-]*$/.test(stripped)) { out.push(line); continue; }
    const indent = line.slice(0, line.length - line.trimStart().length);
    out.push(indent + "# " + stripped);
  }
  return out.join("\n");
}

let token = 0;
let lastGood = "";
let world = { x: 0, y: 0, w: 1, h: 1 };
let cam = { x: 0, y: 0, w: 1, h: 1 };
let fitted = false;
let lastPtr = { x: 0, y: 0, on: false };

function clampCamW(w) {
  const minW = world.w / 20;
  const maxW = world.w / 0.05;
  return Math.min(maxW, Math.max(minW, w));
}

function sizeSvgToPreview(svg) {
  const pr = preview.getBoundingClientRect();
  const w = Math.max(1, pr.width);
  const h = Math.max(1, pr.height);
  svg.style.maxWidth = "none";
  svg.style.maxHeight = "none";
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
  svg.setAttribute("width", String(w));
  svg.setAttribute("height", String(h));
  svg.style.width = w + "px";
  svg.style.height = h + "px";
}

function applyView() {
  // Camera is the SVG viewBox. Display size stays the preview pane so zoom
  // is around the cursor instead of growing the SVG from its top-left.
  const svg = stage.querySelector("svg");
  if (!svg) return;
  svg.setAttribute("viewBox", cam.x + " " + cam.y + " " + cam.w + " " + cam.h);
  sizeSvgToPreview(svg);
  zoomPct.textContent = Math.round((world.w / cam.w) * 100) + "%";
}

function clientToWorld(clientX, clientY) {
  const svg = stage.querySelector("svg");
  if (!svg) return null;
  const r = svg.getBoundingClientRect();
  if (r.width < 1 || r.height < 1) return null;
  const s = Math.min(r.width / cam.w, r.height / cam.h);
  if (s < 1e-9) return null;
  const ox = r.left + (r.width - cam.w * s) / 2;
  const oy = r.top + (r.height - cam.h * s) / 2;
  const lx = (clientX - ox) / s;
  const ly = (clientY - oy) / s;
  return { x: cam.x + lx, y: cam.y + ly, nx: lx / cam.w, ny: ly / cam.h, s: s, r: r };
}

function zoomAt(clientX, clientY, factor) {
  const mapped = clientToWorld(clientX, clientY);
  if (!mapped) return;
  const nextW = clampCamW(cam.w / factor);
  if (nextW === cam.w) return;
  const nextH = nextW * (cam.h / cam.w);
  cam.x = mapped.x - mapped.nx * nextW;
  cam.y = mapped.y - mapped.ny * nextH;
  cam.w = nextW;
  cam.h = nextH;
  applyView();
}

function zoomTowardPointer(factor) {
  const r = preview.getBoundingClientRect();
  if (lastPtr.on) zoomAt(r.left + lastPtr.x, r.top + lastPtr.y, factor);
  else zoomAt(r.left + r.width / 2, r.top + r.height / 2, factor);
}

function pinWorld(root) {
  const svg = root.querySelector("svg");
  if (!svg) return;
  let x = 0, y = 0, w = 0, h = 0;
  const vb = svg.viewBox && svg.viewBox.baseVal;
  if (vb && vb.width > 1 && vb.height > 1) {
    x = vb.x; y = vb.y; w = vb.width; h = vb.height;
  } else {
    w = parseFloat(svg.getAttribute("width") || "");
    h = parseFloat(svg.getAttribute("height") || "");
  }
  if (w < 1 || h < 1) {
    try {
      const b = svg.getBBox();
      x = b.x; y = b.y; w = b.width; h = b.height;
    } catch (e) {}
  }
  if (w < 1 || h < 1) return;
  world = { x: x, y: y, w: w, h: h };
  if (!fitted) cam = { x: x, y: y, w: w, h: h };
}

function fitView() {
  cam = { x: world.x, y: world.y, w: world.w, h: world.h };
  applyView();
  fitted = true;
}

function compileErrText(e) {
  if (Array.isArray(e) && e[0] && e[0].errmsg) return e[0].errmsg;
  if (e && e.errmsg) return e.errmsg;
  return String(e).split("\n")[0];
}

async function compileOne(code) {
  try {
    return { ok: true, result: await d2.compile(code) };
  } catch (e) {
    return { ok: false, err: e };
  }
}

async function render() {
  const mine = ++token;
  const raws = extractSources(src.value);
  if (!raws.length || !raws.some((c) => c.trim())) {
    if (!lastGood) stage.innerHTML = "<p class=err>empty d2</p>";
    return;
  }
  try {
    const bits = [];
    let usedSoft = false;
    let lastErr = null;
    for (let i = 0; i < raws.length; i++) {
      let got = await compileOne(raws[i]);
      if (mine !== token) return;
      if (!got.ok) {
        lastErr = got.err;
        got = await compileOne(soften(raws[i]));
        if (mine !== token) return;
        if (got.ok) usedSoft = true;
      }
      if (!got.ok) throw lastErr || got.err;
      const svg = await d2.render(got.result.diagram, got.result.renderOptions);
      if (mine !== token) return;
      bits.push(svg);
    }
    stage.innerHTML = bits.join("");
    pinWorld(stage);
    lastGood = stage.innerHTML;
    setStatus(usedSoft ? "rendered (softened notes)" : "valid D2", "ok");
    if (!fitted) requestAnimationFrame(fitView);
    else applyView();
  } catch (e) {
    if (mine !== token) return;
    setStatus("compile failed: " + compileErrText(e), "err");
    if (!lastGood) stage.innerHTML = "<pre class=err>" + compileErrText(e) + "</pre>";
  }
}

"""
_D2_INIT_JS = r"""document.getElementById("checkNow").addEventListener("click", async () => {
  await render();
  if (status.dataset.kind === "ok") setStatus("valid D2", "ok");
});
document.getElementById("zoomIn").addEventListener("click", () => {
  zoomTowardPointer(1.25);
});
document.getElementById("zoomOut").addEventListener("click", () => {
  zoomTowardPointer(0.8);
});
document.getElementById("zoomFit").addEventListener("click", () => {
  fitted = false;
  fitView();
});
preview.addEventListener("pointermove", (ev) => {
  const r = preview.getBoundingClientRect();
  lastPtr = { x: ev.clientX - r.left, y: ev.clientY - r.top, on: true };
}, { passive: true });
preview.addEventListener("wheel", (ev) => {
  ev.preventDefault();
  const r = preview.getBoundingClientRect();
  lastPtr = { x: ev.clientX - r.left, y: ev.clientY - r.top, on: true };
  const factor = ev.deltaY < 0 ? 1.12 : 1 / 1.12;
  zoomAt(ev.clientX, ev.clientY, factor);
}, { passive: false });
const SKIP_CLASS = new Set([
  "shape", "connection", "text", "text-bold", "text-mono", "text-italic",
  "text-underline", "text-link", "animated-shape", "animated-connection",
  "md", "blend", "light-code", "dark-code",
]);

function decodeD2Class(cls) {
  if (!cls) return null;
  try {
    const pad = cls.length % 4 === 0 ? "" : "=".repeat(4 - (cls.length % 4));
    const b64 = (cls + pad).replace(/-/g, "+").replace(/_/g, "/");
    const bin = atob(b64);
    if (!bin || /[\x00-\x08\x0e-\x1f]/.test(bin)) return null;
    return bin;
  } catch (e) {
    return null;
  }
}

function looksLikeObjectId(id) {
  if (!id || id.length > 240) return false;
  if (/^\(.*\)\[\d+\]$/.test(id)) return true;
  return /[A-Za-z_]/.test(id) && !/\s{2,}/.test(id);
}

function objectIdFromNode(el) {
  while (el && el !== stage && el !== preview) {
    const cls = (el.getAttribute && el.getAttribute("class")) || "";
    for (const c of cls.split(/\s+/)) {
      if (!c || SKIP_CLASS.has(c)) continue;
      const id = decodeD2Class(c);
      if (id && looksLikeObjectId(id)) return id;
    }
    el = el.parentElement || el.parentNode;
  }
  return null;
}

function findObjectSpan(text, objectId) {
  objectId = (objectId || "").trim();
  if (!objectId) return null;
  const conn = objectId.match(/^\((.+)\)\[\d+\]$/);
  if (conn) return findEdgeSpan(text, conn[1]);
  return findShapeSpan(text, objectId);
}

function keyRe(leaf) {
  const esc = leaf.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp("^([ \t]*)(?:\"" + esc + "\"|" + esc + ")(?=\\s*[:{]|\\s*$)", "m");
}

function spanOfKey(text, match, leaf) {
  const start = match.index + match[1].length;
  if (text[start] === '"') return [start, start + leaf.length + 2];
  return [start, start + leaf.length];
}

function findShapeSpan(text, path) {
  const parts = path.split(".").filter(Boolean);
  if (!parts.length) return null;
  const leaf = parts[parts.length - 1];
  const all = [];
  let from = 0;
  while (from <= text.length) {
    const hit = keyRe(leaf).exec(text.slice(from));
    if (!hit) break;
    all.push({ index: from + hit.index, g1: hit[1] });
    from += hit.index + Math.max(1, hit[0].length);
  }
  if (!all.length) return null;
  let chosen = all[0];
  if (parts.length > 1 && all.length > 1) {
    const parent = findShapeSpan(text, parts.slice(0, -1).join("."));
    if (parent) {
      const after = all.filter((x) => x.index >= parent[0]);
      if (after.length) chosen = after[0];
    }
  }
  const fake = ["", chosen.g1];
  fake.index = chosen.index;
  return spanOfKey(text, fake, leaf);
}

function findEdgeSpan(text, inner) {
  const seps = [" <-> ", " -> ", " <- ", " -- "];
  let left, right, sep;
  for (const token of seps) {
    if (inner.includes(token)) {
      const bits = inner.split(token);
      left = bits[0];
      right = bits[1];
      sep = token.trim();
      break;
    }
  }
  if (left == null || right == null || !sep) return null;
  const leftLeaf = left.split(".").pop().trim().replace(/^"|"$/g, "");
  const rightLeaf = right.split(".").pop().trim().replace(/^"|"$/g, "");
  const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp("^([ \t]*)" + esc(leftLeaf) + "\\s*" + esc(sep) + "\\s*" + esc(rightLeaf), "m");
  const hit = re.exec(text);
  if (!hit) return null;
  return [hit.index + hit[1].length, hit.index + hit[0].length];
}

function snapEditor(start, end) {
  src.focus();
  src.setSelectionRange(start, end);
  const before = src.value.slice(0, start);
  const line = before.split("\n").length;
  const cs = getComputedStyle(src);
  let lh = parseFloat(cs.lineHeight);
  if (!lh || cs.lineHeight === "normal") lh = (parseFloat(cs.fontSize) || 13) * 1.45;
  const pad = parseFloat(cs.paddingTop) || 0;
  src.scrollTop = Math.max(0, (line - 3) * lh - pad);
  syncHlScroll();
  setStatus("snapped to " + src.value.slice(start, end).replace(/\s+/g, " "), "ok");
}

function snapFromEvent(el) {
  const id = objectIdFromNode(el);
  if (!id) return false;
  const span = findObjectSpan(src.value, id);
  if (!span) {
    setStatus("no source for " + id, "warn");
    return false;
  }
  snapEditor(span[0], span[1]);
  return true;
}

preview.addEventListener("pointerdown", (ev) => {
  if (ev.button !== 0) return;
  ev.preventDefault();
  const hit = ev.target;
  preview.setPointerCapture(ev.pointerId);
  let lx = ev.clientX;
  let ly = ev.clientY;
  let panning = false;
  const move = (e) => {
    if (!panning && Math.hypot(e.clientX - lx, e.clientY - ly) < 5) return;
    if (!panning) {
      panning = true;
      preview.classList.add("panning");
    }
    const mapped = clientToWorld(lx, ly);
    if (mapped) {
      cam.x -= (e.clientX - lx) / mapped.s;
      cam.y -= (e.clientY - ly) / mapped.s;
      applyView();
    }
    lx = e.clientX;
    ly = e.clientY;
  };
  const up = (e) => {
    preview.classList.remove("panning");
    preview.removeEventListener("pointermove", move);
    preview.removeEventListener("pointerup", up);
    if (!panning) snapFromEvent(hit);
  };
  preview.addEventListener("pointermove", move);
  preview.addEventListener("pointerup", up);
});
preview.addEventListener("dblclick", () => {
  fitted = false;
  fitView();
});
window.addEventListener("keydown", (ev) => {
  if (!(ev.ctrlKey || ev.metaKey)) return;
  if (ev.key === "=" || ev.key === "+") {
    ev.preventDefault();
    zoomTowardPointer(1.25);
  } else if (ev.key === "-" || ev.key === "_") {
    ev.preventDefault();
    zoomTowardPointer(0.8);
  } else if (ev.key === "0") {
    ev.preventDefault();
    fitted = false;
    fitView();
  }
});
applyView();"""
_D2_FOOTER = r"""setStatus("loading d2 wasm…", "");
renderSoon();"""

LIVE_HTML = build_html(
    title="anno d2",
    kind="d2",
    import_js='import { D2 } from "https://esm.sh/@terrastruct/d2";',
    script_open='<script type="module">',
    css=_D2_CSS,
    bar='  <button type="button" id="checkNow">Check</button>',
    bar_extra=_D2_BAR_EXTRA,
    editor=_D2_EDITOR,
    preview=_D2_PREVIEW,
    status_hint="live preview — wheel / Ctrl± zoom, drag pan",
    refs=_D2_REFS,
    render_js=_D2_RENDER_JS,
    init_js=_D2_INIT_JS,
    input_hook="paintHighlight();",
    disk_hook="paintHighlight();",
    footer=_D2_FOOTER,
)

D2_LIVE = LiveConfig(
    kind="d2",
    html=LIVE_HTML,
    module="anno.d2_live",
    state_dir_env="ANNO_D2_LIVE_DIR",
    state_subdir="d2-live",
)


def start_live_server(path: Path, preferred_port: int | None = None):
    return _start(D2_LIVE, path, preferred_port)


def _write_state(path: Path, port: int) -> None:
    _write_state_impl(D2_LIVE, path, port)


def preview_url_if_running(path: Path) -> str | None:
    return _preview(D2_LIVE, path)


def running_live_paths() -> list[Path]:
    """`.d2` files whose live sidecar is still up."""
    return _running(D2_LIVE)


def serve_until_done(path: Path) -> str:
    return _serve(D2_LIVE, path)


def run_live_editor(path: Path) -> bool:
    """Open (or reuse) a detached live preview. Returns immediately."""
    return _run(D2_LIVE, path)


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: python -m anno.d2_live <file.d2>")
    serve_until_done(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
