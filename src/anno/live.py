"""Shared live-preview sidecar for browser-based editors (D2, mermaid).

Both `anno.d2_live` and `anno.mermaid_live` are thin format shims over this:
a threaded HTTP server serves a split editor/preview page, saves the buffer
back to disk, watches the file for out-of-band edits (SSE + poll), and blocks
in a detached process until the browser clicks Done.
"""

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
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event
from urllib.error import URLError
from urllib.request import urlopen

_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
__HEAD__
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
__CSS__
</style>
</head>
<body>
<div id="bar">
  <button type="button" id="done">Done</button>
  <button type="button" id="saveNow">Save</button>
__BAR__
  <button type="button" id="reconnect">Reconnect</button>
__BAR_EXTRA__
  <span id="status">__STATUS_HINT__</span>
</div>
<div id="wrap">
__EDITOR__
  <div id="gutter" role="separator" aria-orientation="vertical" title="drag to resize"></div>
__PREVIEW__
</div>
__SCRIPT_OPEN__
__IMPORT__
const initial = __INITIAL_JSON__;
const src = document.getElementById("src");
const preview = document.getElementById("preview");
const status = document.getElementById("status");
const wrap = document.getElementById("wrap");
const gutter = document.getElementById("gutter");
__REFS__

__SETUP__

(function initSplit() {
  const n = parseFloat(localStorage.getItem("anno-__KIND__-split") || "50");
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
    try { localStorage.setItem("anno-__KIND__-split", String(clamped)); } catch (err) {}
  };
  const up = () => {
    gutter.classList.remove("drag");
    gutter.removeEventListener("pointermove", move);
    gutter.removeEventListener("pointerup", up);
  };
  gutter.addEventListener("pointermove", move);
  gutter.addEventListener("pointerup", up);
});

let saveTimer;
let lastDisk = initial;
let renderTimer;
const fileKey = "__FILE_KEY__";
const lsKey = "anno-__KIND__:" + fileKey;

function setStatus(msg, kind) {
  status.textContent = msg;
  status.dataset.kind = kind || "";
}

function renderSoon() {
  clearTimeout(renderTimer);
  renderTimer = setTimeout(() => { render().catch(() => {}); }, 180);
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
  __INPUT_HOOK__
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

__RENDER_JS__

__INIT_JS__

function applyDisk(text) {
  if (text === src.value) {
    lastDisk = text;
    return;
  }
  if (text === lastDisk) return;
  if (src.value !== lastDisk) stash(src.value);
  lastDisk = text;
  src.value = text;
  __DISK_HOOK__
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
__FOOTER__
</script>
</body>
</html>
"""


def _initial_json(text: str) -> str:
    """JSON for an inline <script>: escape `<` so content cannot close the tag."""
    return json.dumps(text).replace("<", "\\u003c")


@dataclass(frozen=True)
class LiveConfig:
    """Format-specific bits the shared sidecar needs."""

    kind: str
    html: str
    module: str
    state_dir_env: str
    state_subdir: str


def build_html(
    *,
    title: str,
    kind: str,
    import_js: str = "",
    head: str = "",
    script_open: str = "<script>",
    css: str = "",
    bar: str = "",
    bar_extra: str = "",
    editor: str,
    preview: str,
    status_hint: str,
    refs: str = "",
    setup: str = "",
    render_js: str,
    init_js: str = "",
    input_hook: str = "",
    disk_hook: str = "",
    footer: str = "",
) -> str:
    """Assemble a format's editor page from the shared skeleton.

    `__INITIAL_JSON__` and `__FILE_KEY__` are left in place for the server to
    substitute per request; everything else is filled here.
    """
    return (
        _HTML_TEMPLATE.replace("__TITLE__", title)
        .replace("__HEAD__", head)
        .replace("__CSS__", css)
        .replace("__BAR__", bar)
        .replace("__BAR_EXTRA__", bar_extra)
        .replace("__STATUS_HINT__", status_hint)
        .replace("__EDITOR__", editor)
        .replace("__PREVIEW__", preview)
        .replace("__SCRIPT_OPEN__", script_open)
        .replace("__IMPORT__", import_js)
        .replace("__REFS__", refs)
        .replace("__SETUP__", setup)
        .replace("__RENDER_JS__", render_js)
        .replace("__INIT_JS__", init_js)
        .replace("__INPUT_HOOK__", input_hook)
        .replace("__DISK_HOOK__", disk_hook)
        .replace("__FOOTER__", footer)
        .replace("__KIND__", kind)
    )


def start_live_server(
    config: LiveConfig,
    path: Path,
    preferred_port: int | None = None,
) -> tuple[ThreadingHTTPServer, int, Event]:
    done = Event()
    src_path = path
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
                payload = json.dumps({"text": src_path.read_text(), "mtime": src_path.stat().st_mtime})
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
            html = config.html.replace("__INITIAL_JSON__", _initial_json(src_path.read_text())).replace(
                "__FILE_KEY__", state_file(config, src_path).stem
            )
            self._send(200, html, "text/html; charset=utf-8")

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            route = self.path.split("?", 1)[0]
            if route == "/save":
                try:
                    text = body.decode()
                    existing = src_path.read_text() if src_path.is_file() else ""
                    if not text.strip() and existing.strip():
                        self._send(
                            409,
                            json.dumps({"ok": False, "error": "refusing empty overwrite"}),
                            "application/json; charset=utf-8",
                        )
                        return
                    src_path.write_text(text)
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
            last = src_path.read_text()
        except OSError:
            last = ""
        while not done.wait(timeout=0.2):
            try:
                text = src_path.read_text()
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


def state_dir(config: LiveConfig) -> Path:
    raw = os.environ.get(config.state_dir_env)
    return Path(raw) if raw else Path.home() / ".anno" / config.state_subdir


def state_file(config: LiveConfig, path: Path) -> Path:
    key = hashlib.sha1(str(path.resolve()).encode()).hexdigest()[:16]
    return state_dir(config) / f"{key}.json"


def write_state(config: LiveConfig, path: Path, port: int) -> None:
    state = state_file(config, path)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"pid": os.getpid(), "port": port, "file": str(path.resolve())}))


def clear_state(config: LiveConfig, path: Path) -> None:
    state_file(config, path).unlink(missing_ok=True)


def stale_port(config: LiveConfig, path: Path) -> int | None:
    state = state_file(config, path)
    if not state.is_file():
        return None
    try:
        port = json.loads(state.read_text()).get("port")
    except json.JSONDecodeError:
        return None
    return port if isinstance(port, int) else None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def preview_url_if_running(config: LiveConfig, path: Path) -> str | None:
    state = state_file(config, path)
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


def running_live_paths(config: LiveConfig) -> list[Path]:
    """Files whose live sidecar for this format is still up."""
    folder = state_dir(config)
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
        if path.is_file() and preview_url_if_running(config, path):
            found.append(path)
    return found


def serve_until_done(config: LiveConfig, path: Path) -> str:
    httpd, port, done = start_live_server(config, path, preferred_port=stale_port(config, path))
    url = f"http://127.0.0.1:{port}/"
    write_state(config, path, port)
    print(f"preview: {url}", flush=True)
    webbrowser.open(url)
    try:
        done.wait()
    finally:
        clear_state(config, path)
        httpd.shutdown()
        httpd.server_close()
    return url


def run_live_editor(config: LiveConfig, path: Path) -> bool:
    """Open (or reuse) a detached live preview. Returns immediately."""
    if not has_browser():
        return False
    path = path.resolve()
    url = preview_url_if_running(config, path)
    if url:
        webbrowser.open(url)
        print(f"preview: {url}  (already running; disk edits rerender)")
        return True
    subprocess.Popen(
        [sys.executable, "-m", config.module, str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        url = preview_url_if_running(config, path)
        if url:
            print(f"preview: {url}  (stays open; disk edits rerender)")
            return True
        time.sleep(0.05)
    return False
