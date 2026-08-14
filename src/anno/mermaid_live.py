"""Local mermaid.js editor: live preview, save back to the .md, block until Done."""

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
<title>anno mermaid</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
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
  #status { color: #8b949e; }
  #status[data-kind="err"] { color: #f85149; }
  #status[data-kind="ok"] { color: #3fb950; }
  #status[data-kind="warn"] { color: #d29922; }
  #wrap {
    display: flex; height: calc(100% - 45px); min-height: 0;
  }
  textarea {
    resize: none; border: 0; padding: 12px; outline: none;
    background: #161b22; color: #e6edf3; font: 13px/1.45 ui-monospace, monospace;
    flex: 0 0 auto; width: var(--split, 50%); min-width: 120px;
  }
  #gutter {
    flex: 0 0 6px; cursor: col-resize; background: #30363d;
  }
  #gutter:hover, #gutter.drag { background: #58a6ff; }
  #preview {
    flex: 1 1 auto; min-width: 120px; overflow: auto; padding: 16px;
    background: #fff; color: #111;
  }
  #preview .err {
    color: #cf222e; white-space: pre-wrap; font: 13px/1.45 ui-monospace, monospace;
  }
  .block { margin-bottom: 24px; }
</style>
</head>
<body>
<div id="bar">
  <button type="button" id="done">Done</button>
  <button type="button" id="saveNow">Save</button>
  <button type="button" id="reconnect">Reconnect</button>
  <span id="status">live preview — stays up; disk edits rerender</span>
</div>
<div id="wrap">
  <textarea id="src" spellcheck="false"></textarea>
  <div id="gutter" role="separator" aria-orientation="vertical" title="drag to resize"></div>
  <div id="preview"></div>
</div>
<script>
const initial = __INITIAL_JSON__;
const src = document.getElementById("src");
const preview = document.getElementById("preview");
const status = document.getElementById("status");
const wrap = document.getElementById("wrap");
const gutter = document.getElementById("gutter");
src.value = initial;
(function initSplit() {
  const n = parseFloat(localStorage.getItem("anno-mermaid-split") || "50");
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
    try { localStorage.setItem("anno-mermaid-split", String(clamped)); } catch (err) {}
  };
  const up = () => {
    gutter.classList.remove("drag");
    gutter.removeEventListener("pointermove", move);
    gutter.removeEventListener("pointerup", up);
  };
  gutter.addEventListener("pointermove", move);
  gutter.addEventListener("pointerup", up);
});
mermaid.initialize({ startOnLoad: false, theme: "neutral", securityLevel: "loose" });

function extractSources(md) {
  const out = [];
  const re = /```(?:mermaid)?[ \\t]*\\n([\\s\\S]*?)(?:```|$)/gi;
  let m;
  while ((m = re.exec(md))) out.push(m[1]);
  if (out.length) return out;
  const lines = md.split("\\n");
  let i = 0;
  while (i < lines.length && (!lines[i].trim() || lines[i].trim().startsWith("#"))) i++;
  const body = lines.slice(i).join("\\n");
  const first = (body.split("\\n").find((ln) => ln.trim()) || "").trim();
  if (/^(flowchart|graph|sequenceDiagram|stateDiagram|classDiagram)\\b/i.test(first)) return [body];
  return [];
}

let token = 0;
let lastGood = "";
let renderTimer;
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
    setStatus(String(e).split("\\n")[0], "warn");
    if (!lastGood) preview.innerHTML = "<pre class=err>" + String(e) + "</pre>";
    return;
  }
  if (mine !== token) return;
  preview.innerHTML = bits.map((s) => "<div class=block>" + s + "</div>").join("");
  lastGood = preview.innerHTML;
}

function renderSoon() {
  clearTimeout(renderTimer);
  renderTimer = setTimeout(() => { render().catch(() => {}); }, 180);
}

let saveTimer;
let lastDisk = initial;
const fileKey = "__FILE_KEY__";
const lsKey = "anno-mermaid:" + fileKey;

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
  setStatus("editing…", "");
  renderSoon();
  clearTimeout(saveTimer);
  saveTimer = setTimeout(save, 400);
});

document.getElementById("saveNow").addEventListener("click", () => {
  clearTimeout(saveTimer);
  save();
});
document.getElementById("reconnect").addEventListener("click", () => {
  location.reload();
});

function applyDisk(text) {
  if (text === src.value) {
    lastDisk = text;
    return;
  }
  if (text === lastDisk) return;
  if (src.value !== lastDisk) return;
  lastDisk = text;
  src.value = text;
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
    raw = os.environ.get("ANNO_MERMAID_LIVE_DIR")
    return Path(raw) if raw else Path.home() / ".anno" / "mermaid-live"


def _state_file(path: Path) -> Path:
    key = hashlib.sha1(str(path.resolve()).encode()).hexdigest()[:16]
    return _state_dir() / f"{key}.json"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


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
        [sys.executable, "-m", "anno.mermaid_live", str(path)],
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
        sys.exit("usage: python -m anno.mermaid_live <file.md>")
    serve_until_done(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
