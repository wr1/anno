"""Local D2 editor: live preview via @terrastruct/d2 WASM, save back, block until Done."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event
from urllib.error import URLError
from urllib.request import urlopen

LIVE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>anno d2</title>
<style>
  :root { color-scheme: dark; }
  html, body {
    height: 100%; margin: 0; background: #0d1117; color: #e6edf3;
    font: 14px/1.4 ui-sans-serif, system-ui, sans-serif;
  }
  #bar {
    display: flex; align-items: center; gap: 12px; padding: 8px 12px;
    border-bottom: 1px solid #30363d;
  }
  #bar button {
    background: #238636; color: #fff; border: 0; border-radius: 6px;
    padding: 6px 12px; font-weight: 600; cursor: pointer;
  }
  #bar button:hover { background: #2ea043; }
  #bar .zoom button {
    background: #21262d; padding: 6px 10px;
  }
  #bar .zoom button:hover { background: #30363d; }
  #zoomPct { color: #8b949e; min-width: 3.5em; }
  #status { color: #8b949e; }
  #status[data-kind="err"] { color: #f85149; }
  #status[data-kind="ok"] { color: #3fb950; }
  #status[data-kind="warn"] { color: #d29922; }
  #wrap {
    display: flex; height: calc(100% - 45px); min-height: 0;
  }
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
  #gutter {
    flex: 0 0 6px; cursor: col-resize; background: #30363d;
  }
  #gutter:hover, #gutter.drag { background: #58a6ff; }
  #preview {
    flex: 1 1 auto; min-width: 120px; overflow: hidden; padding: 0;
    background: #fff; color: #111; position: relative; cursor: grab;
    touch-action: none; overscroll-behavior: none;
  }
  #preview.panning { cursor: grabbing; }
  #stage {
    position: absolute; left: 0; top: 0; transform-origin: 0 0;
  }
  #preview .err {
    color: #cf222e; white-space: pre-wrap; font: 13px/1.45 ui-monospace, monospace;
    padding: 16px;
  }
  #preview svg { max-width: none; max-height: none; display: block; }
  #stage g { cursor: pointer; }
</style>
</head>
<body>
<div id="bar">
  <button type="button" id="done">Done</button>
  <button type="button" id="saveNow">Save</button>
  <button type="button" id="checkNow">Check</button>
  <button type="button" id="reconnect">Reconnect</button>
  <span class="zoom">
    <button type="button" id="zoomOut" title="zoom out">−</button>
    <button type="button" id="zoomFit" title="fit diagram">Fit</button>
    <button type="button" id="zoomIn" title="zoom in">+</button>
    <span id="zoomPct">100%</span>
  </span>
  <span id="status">live preview — wheel / Ctrl± zoom, drag pan</span>
</div>
<div id="wrap">
  <div id="editor">
    <pre id="hl" aria-hidden="true"></pre>
    <textarea id="src" spellcheck="false" wrap="off"></textarea>
  </div>
  <div id="gutter" role="separator" aria-orientation="vertical" title="drag to resize"></div>
  <div id="preview"><div id="stage"></div></div>
</div>
<script type="module">
import { D2 } from "https://esm.sh/@terrastruct/d2";

const initial = __INITIAL_JSON__;
const src = document.getElementById("src");
const hl = document.getElementById("hl");
const preview = document.getElementById("preview");
const stage = document.getElementById("stage");
const status = document.getElementById("status");
const wrap = document.getElementById("wrap");
const gutter = document.getElementById("gutter");
const zoomPct = document.getElementById("zoomPct");
src.value = initial;

function escHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function highlightD2(text) {
  const kw = new RegExp(
    "^(direction|shape|label|style|class|classes|near|link|tooltip|icon|" +
      "constraint|width|height|vars|layers|scenarios|steps|opacity|fill|" +
      "stroke|font-color|font-size|bold|italic|underline|shadow|multiple|" +
      "animated|filled)\\\\b"
  );
  let i = 0;
  let out = "";
  const n = text.length;
  while (i < n) {
    const ch = text[i];
    if (ch === "#") {
      let j = text.indexOf("\\n", i);
      if (j < 0) j = n;
      out += '<span class="tok-c">' + escHtml(text.slice(i, j)) + "</span>";
      i = j;
      continue;
    }
    if (ch === '"') {
      let j = i + 1;
      while (j < n && text[j] !== '"') {
        if (text[j] === "\\\\") j++;
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
      while (j < n && /[\\w.-]/.test(text[j])) j++;
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
  return out + "\\n";
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
(function initSplit() {
  const n = parseFloat(localStorage.getItem("anno-d2-split") || "50");
  if (!isNaN(n)) wrap.style.setProperty("--split", Math.min(80, Math.max(20, n)) + "%");
})();
gutter.addEventListener("pointerdown", (ev) => {
  ev.preventDefault();
  gutter.classList.add("drag");
  gutter.setPointerCapture(ev.pointerId);
  const move = (e) => {
    const r = wrap.getBoundingClientRect();
    const pct = ((e.clientX - r.left) / r.width) * 100;
    const clamped = Math.min(80, Math.max(20, pct));
    wrap.style.setProperty("--split", clamped + "%");
    try { localStorage.setItem("anno-d2-split", String(clamped)); } catch (err) {}
  };
  const up = () => {
    gutter.classList.remove("drag");
    gutter.removeEventListener("pointermove", move);
    gutter.removeEventListener("pointerup", up);
  };
  gutter.addEventListener("pointermove", move);
  gutter.addEventListener("pointerup", up);
});

const d2 = new D2();

function extractSources(text) {
  const out = [];
  const re = /```d2[ \\t]*\\n([\\s\\S]*?)(?:```|$)/gi;
  let m;
  while ((m = re.exec(text))) out.push(m[1]);
  if (out.length) return out;
  return [text];
}

function soften(src) {
  const openRe = /^(?:[A-Za-z_][\\w.-]*(?:\\.[A-Za-z_][\\w.-]*)*\\s*:)?\\s*(\\|+)([A-Za-z][\\w-]*)?\\s*$/;
  const lines = src.split("\\n");
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
    if (/^[A-Za-z_][\\w.-]*(\\.[A-Za-z_][\\w.-]*)*\\s*:/.test(stripped)) { out.push(line); continue; }
    if (/^[A-Za-z_][\\w.-]*$/.test(stripped)) { out.push(line); continue; }
    const indent = line.slice(0, line.length - line.trimStart().length);
    out.push(indent + "# " + stripped);
  }
  return out.join("\\n");
}

let token = 0;
let lastGood = "";
let renderTimer;
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
  return String(e).split("\\n")[0];
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

function renderSoon() {
  clearTimeout(renderTimer);
  renderTimer = setTimeout(() => { render().catch(() => {}); }, 180);
}

let saveTimer;
let lastDisk = initial;
const fileKey = "__FILE_KEY__";
const lsKey = "anno-d2:" + fileKey;

function setStatus(msg, kind) {
  status.textContent = msg;
  status.dataset.kind = kind || "";
}

function stash(text) {
  try { localStorage.setItem(lsKey, text); } catch (e) {}
}

async function postSave(text) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 4000);
  try {
    return await fetch("/save", {
      method: "POST",
      body: text,
      cache: "no-store",
      keepalive: true,
      signal: ctrl.signal,
    });
  } finally {
    clearTimeout(t);
  }
}

async function save() {
  const text = src.value;
  if (!text.trim() && lastDisk.trim()) {
    setStatus("refusing to save empty over existing file — editor text kept", "err");
    return;
  }
  stash(text);
  let lastErr = "";
  for (let i = 0; i < 3; i++) {
    try {
      const res = await postSave(text);
      if (res.ok) {
        lastDisk = text;
        setStatus(src.value === text ? "saved to disk" : "saved to disk (newer edits still in editor)", "ok");
        return;
      }
      lastErr = "HTTP " + res.status;
    } catch (e) {
      lastErr = (e && e.name === "AbortError") ? "timeout" : ((e && e.message) || String(e));
    }
    await new Promise((r) => setTimeout(r, 250 * (i + 1)));
  }
  setStatus(
    "save failed (" + lastErr + "). Click Reconnect. Text is kept.",
    "err"
  );
}

src.addEventListener("input", () => {
  paintHighlight();
  setStatus("editing…", "");
  renderSoon();
  clearTimeout(saveTimer);
  saveTimer = setTimeout(save, 400);
});

document.getElementById("saveNow").addEventListener("click", () => {
  clearTimeout(saveTimer);
  save();
});
document.getElementById("checkNow").addEventListener("click", async () => {
  await render();
  if (status.dataset.kind === "ok") setStatus("valid D2", "ok");
});
document.getElementById("reconnect").addEventListener("click", () => {
  location.reload();
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
    if (!bin || /[\\x00-\\x08\\x0e-\\x1f]/.test(bin)) return null;
    return bin;
  } catch (e) {
    return null;
  }
}

function looksLikeObjectId(id) {
  if (!id || id.length > 240) return false;
  if (/^\\(.*\\)\\[\\d+\\]$/.test(id)) return true;
  return /[A-Za-z_]/.test(id) && !/\\s{2,}/.test(id);
}

function objectIdFromNode(el) {
  while (el && el !== stage && el !== preview) {
    const cls = (el.getAttribute && el.getAttribute("class")) || "";
    for (const c of cls.split(/\\s+/)) {
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
  const conn = objectId.match(/^\\((.+)\\)\\[\\d+\\]$/);
  if (conn) return findEdgeSpan(text, conn[1]);
  return findShapeSpan(text, objectId);
}

function keyRe(leaf) {
  const esc = leaf.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&");
  return new RegExp("^([ \\t]*)(?:\\"" + esc + "\\"|" + esc + ")(?=\\\\s*[:{]|\\\\s*$)", "m");
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
  const esc = (s) => s.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&");
  const re = new RegExp("^([ \\t]*)" + esc(leftLeaf) + "\\\\s*" + esc(sep) + "\\\\s*" + esc(rightLeaf), "m");
  const hit = re.exec(text);
  if (!hit) return null;
  return [hit.index + hit[1].length, hit.index + hit[0].length];
}

function snapEditor(start, end) {
  src.focus();
  src.setSelectionRange(start, end);
  const before = src.value.slice(0, start);
  const line = before.split("\\n").length;
  const cs = getComputedStyle(src);
  let lh = parseFloat(cs.lineHeight);
  if (!lh || cs.lineHeight === "normal") lh = (parseFloat(cs.fontSize) || 13) * 1.45;
  const pad = parseFloat(cs.paddingTop) || 0;
  src.scrollTop = Math.max(0, (line - 3) * lh - pad);
  syncHlScroll();
  setStatus("snapped to " + src.value.slice(start, end).replace(/\\s+/g, " "), "ok");
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
applyView();

function applyDisk(text) {
  if (text === src.value) {
    lastDisk = text;
    return;
  }
  if (text === lastDisk) return;
  if (src.value !== lastDisk) stash(src.value);
  lastDisk = text;
  src.value = text;
  paintHighlight();
  setStatus("loaded from disk", "ok");
  renderSoon();
}

async function pollDisk() {
  try {
    const data = await (await fetch("/content")).json();
    applyDisk(data.text);
  } catch (e) {}
}

try {
  const es = new EventSource("/events");
  es.onmessage = (ev) => {
    try { applyDisk(JSON.parse(ev.data).text); } catch (e) {}
  };
} catch (e) {}

async function finish() {
  clearTimeout(saveTimer);
  await save();
  try { await fetch("/done", { method: "POST" }); } catch (e) {}
}

document.getElementById("done").addEventListener("click", finish);
setInterval(pollDisk, 1000);
setStatus("loading d2 wasm…", "");
renderSoon();
</script>
</body>
</html>
"""


def start_live_server(path: Path, preferred_port: int | None = None) -> tuple[ThreadingHTTPServer, int, Event]:
    done = Event()
    md_path = path
    subscribers: list[queue.Queue[str]] = []
    lock = threading.Lock()
    ignore_text: list[str | None] = [None]

    def _broadcast(text: str) -> None:
        payload = json.dumps({"text": text})
        with lock:
            targets = list(subscribers)
        for q in targets:
            q.put(payload)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _fmt: str, *_args: object) -> None:
            return

        def _send(self, code: int, body: str | bytes, ctype: str = "text/plain; charset=utf-8") -> None:
            data = body if isinstance(body, bytes) else body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            route = self.path.split("?", 1)[0]
            if route == "/content":
                payload = json.dumps({"text": md_path.read_text(), "mtime": md_path.stat().st_mtime})
                self._send(200, payload, "application/json; charset=utf-8")
                return
            if route == "/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                q: queue.Queue[str] = queue.Queue()
                with lock:
                    subscribers.append(q)
                try:
                    while not done.is_set():
                        try:
                            msg = q.get(timeout=1.0)
                        except queue.Empty:
                            self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                            continue
                        self.wfile.write(f"data: {msg}\n\n".encode())
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    with lock:
                        if q in subscribers:
                            subscribers.remove(q)
                return
            if route != "/":
                self._send(404, "not found")
                return
            html = LIVE_HTML.replace("__INITIAL_JSON__", json.dumps(md_path.read_text())).replace(
                "__FILE_KEY__", _state_file(md_path).stem
            )
            self._send(200, html, "text/html; charset=utf-8")

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            route = self.path.split("?", 1)[0]
            if route == "/save":
                try:
                    text = body.decode()
                    existing = md_path.read_text() if md_path.is_file() else ""
                    if not text.strip() and existing.strip():
                        self._send(
                            409,
                            json.dumps({"ok": False, "error": "refusing empty overwrite"}),
                            "application/json; charset=utf-8",
                        )
                        return
                    md_path.write_text(text)
                    ignore_text[0] = text
                    self._send(
                        200,
                        json.dumps({"ok": True, "bytes": len(text)}),
                        "application/json; charset=utf-8",
                    )
                except Exception as exc:
                    self._send(
                        500,
                        json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}),
                        "application/json; charset=utf-8",
                    )
            elif route == "/done":
                done.set()
                self._send(200, "ok")
            else:
                self._send(404, "not found")

    httpd = None
    if preferred_port:
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", preferred_port), Handler)
        except OSError:
            httpd = None
    if httpd is None:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def _watch_file() -> None:
        try:
            last = md_path.read_text()
        except OSError:
            last = ""
        while not done.wait(timeout=0.2):
            try:
                text = md_path.read_text()
            except OSError:
                continue
            if text == last:
                continue
            last = text
            if ignore_text[0] == text:
                ignore_text[0] = None
                continue
            _broadcast(text)

    threading.Thread(target=_watch_file, daemon=True).start()
    return httpd, httpd.server_address[1], done


def has_browser() -> bool:
    return any(shutil.which(name) for name in ("xdg-open", "firefox", "chromium", "brave", "google-chrome"))


def _state_dir() -> Path:
    raw = os.environ.get("ANNO_D2_LIVE_DIR")
    return Path(raw) if raw else Path.home() / ".anno" / "d2-live"


def _state_file(path: Path) -> Path:
    key = hashlib.sha1(str(path.resolve()).encode()).hexdigest()[:16]
    return _state_dir() / f"{key}.json"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def running_live_paths() -> list[Path]:
    """`.d2` files whose live sidecar is still up."""
    folder = _state_dir()
    if not folder.is_dir():
        return []
    found: list[Path] = []
    for state in folder.glob("*.json"):
        try:
            data = json.loads(state.read_text())
        except json.JSONDecodeError:
            continue
        raw = data.get("file")
        if not isinstance(raw, str):
            continue
        path = Path(raw)
        if path.is_file() and preview_url_if_running(path):
            found.append(path)
    return found


def preview_url_if_running(path: Path) -> str | None:
    state = _state_file(path)
    if not state.is_file():
        return None
    try:
        data = json.loads(state.read_text())
    except json.JSONDecodeError:
        return None
    pid, port = data.get("pid"), data.get("port")
    if not isinstance(pid, int) or not isinstance(port, int):
        return None
    if not _pid_alive(pid):
        return None
    url = f"http://127.0.0.1:{port}/"
    try:
        urlopen(url + "content", timeout=1)
    except (OSError, URLError):
        return None
    return url


def _write_state(path: Path, port: int) -> None:
    state = _state_file(path)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"pid": os.getpid(), "port": port, "file": str(path.resolve())}))


def _clear_state(path: Path) -> None:
    _state_file(path).unlink(missing_ok=True)


def _stale_port(path: Path) -> int | None:
    state = _state_file(path)
    if not state.is_file():
        return None
    try:
        port = json.loads(state.read_text()).get("port")
    except json.JSONDecodeError:
        return None
    return port if isinstance(port, int) else None


def serve_until_done(path: Path) -> str:
    httpd, port, done = start_live_server(path, preferred_port=_stale_port(path))
    url = f"http://127.0.0.1:{port}/"
    _write_state(path, port)
    print(f"preview: {url}", flush=True)
    webbrowser.open(url)
    try:
        done.wait()
    finally:
        _clear_state(path)
        httpd.shutdown()
        httpd.server_close()
    return url


def run_live_editor(path: Path) -> bool:
    """Open (or reuse) a detached live preview. Returns immediately."""
    if not has_browser():
        return False
    path = path.resolve()
    url = preview_url_if_running(path)
    if url:
        webbrowser.open(url)
        print(f"preview: {url}  (already running; disk edits rerender)")
        return True
    subprocess.Popen(
        [sys.executable, "-m", "anno.d2_live", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        url = preview_url_if_running(path)
        if url:
            print(f"preview: {url}  (stays open; disk edits rerender)")
            return True
        time.sleep(0.05)
    return False


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: python -m anno.d2_live <file.d2>")
    serve_until_done(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
