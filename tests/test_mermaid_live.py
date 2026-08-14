"""Tests for the local mermaid.js live editor sidecar."""

import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from anno.mermaid_live import LIVE_HTML, _write_state, preview_url_if_running, start_live_server


def test_live_html_is_an_editor_page():
    assert "mermaid" in LIVE_HTML
    assert "textarea" in LIVE_HTML
    assert "/save" in LIVE_HTML
    assert "/done" in LIVE_HTML
    assert "/content" in LIVE_HTML
    assert "/events" in LIVE_HTML
    assert "pagehide" not in LIVE_HTML
    assert "softenComments" not in LIVE_HTML
    assert "extractSources" in LIVE_HTML
    assert "renderSoon" in LIVE_HTML
    assert "lastGood" in LIVE_HTML
    assert "src.value !== lastDisk" in LIVE_HTML
    assert 'id="gutter"' in LIVE_HTML
    assert "col-resize" in LIVE_HTML
    assert "anno-mermaid-split" in LIVE_HTML
    assert 'id="saveNow"' in LIVE_HTML
    assert 'id="reconnect"' in LIVE_HTML
    assert "__FILE_KEY__" in LIVE_HTML
    assert "Text is kept" in LIVE_HTML


def test_live_server_serves_saves_and_dones(tmp_path: Path):
    path = tmp_path / "pipe.md"
    path.write_text("# pipe\n\n```mermaid\nflowchart LR\n  a --> b\n```\n")
    httpd, port, done = start_live_server(path)
    base = f"http://127.0.0.1:{port}"
    try:
        page = urlopen(f"{base}/", timeout=2).read().decode()
        assert "textarea" in page
        assert "flowchart LR" in page
        raw = urlopen(Request(f"{base}/save", data=b"# edited\n", method="POST"), timeout=2).read()
        assert json.loads(raw)["ok"] is True
        assert path.read_text() == "# edited\n"
        payload = json.loads(urlopen(f"{base}/content", timeout=2).read().decode())
        assert payload["text"] == "# edited\n"
        path.write_text("# from agent\n")
        payload = json.loads(urlopen(f"{base}/content", timeout=2).read().decode())
        assert payload["text"] == "# from agent\n"
        urlopen(Request(f"{base}/done", data=b"", method="POST"), timeout=2)
        assert done.wait(timeout=1)
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_live_server_rejects_non_localhost_save_is_local_only(tmp_path: Path):
    path = tmp_path / "pipe.md"
    path.write_text("x\n")
    httpd, port, _done = start_live_server(path)
    try:
        urlopen(Request(f"http://127.0.0.1:{port}/nope", data=b"y", method="POST"), timeout=2)
    except HTTPError as exc:
        assert exc.code == 404
    else:
        raise AssertionError("expected 404")
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_server_stays_alive_without_ping_or_done(tmp_path: Path):
    path = tmp_path / "pipe.md"
    path.write_text("x\n")
    httpd, port, done = start_live_server(path)
    try:
        urlopen(f"http://127.0.0.1:{port}/", timeout=2)
        assert not done.is_set()
        urlopen(f"http://127.0.0.1:{port}/content", timeout=2)
        assert not done.is_set()
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_save_refuses_empty_overwrite(tmp_path: Path):
    path = tmp_path / "pipe.md"
    path.write_text("# keep\n")
    httpd, port, _done = start_live_server(path)
    try:
        urlopen(Request(f"http://127.0.0.1:{port}/save", data=b"\n", method="POST"), timeout=2)
    except HTTPError as exc:
        assert exc.code == 409
        assert json.loads(exc.read().decode())["ok"] is False
        assert path.read_text() == "# keep\n"
    else:
        raise AssertionError("expected 409")
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_save_write_error_returns_json_error(tmp_path: Path):
    path = tmp_path / "pipe.md"
    path.write_text("x\n")
    path.chmod(0o444)
    httpd, port, _done = start_live_server(path)
    try:
        urlopen(Request(f"http://127.0.0.1:{port}/save", data=b"y\n", method="POST"), timeout=2)
    except HTTPError as exc:
        assert exc.code == 500
        body = json.loads(exc.read().decode())
        assert body["ok"] is False
        assert "error" in body
    else:
        raise AssertionError("expected 500")
    finally:
        path.chmod(0o644)
        httpd.shutdown()
        httpd.server_close()


def test_preferred_port_reused_when_free(tmp_path: Path):
    path = tmp_path / "pipe.md"
    path.write_text("x\n")
    httpd, port, _done = start_live_server(path)
    httpd.shutdown()
    httpd.server_close()
    httpd2, port2, _done2 = start_live_server(path, preferred_port=port)
    try:
        assert port2 == port
    finally:
        httpd2.shutdown()
        httpd2.server_close()


def test_preview_url_if_running_reads_state(tmp_path: Path, monkeypatch):

    monkeypatch.setenv("ANNO_MERMAID_LIVE_DIR", str(tmp_path / "state"))
    path = tmp_path / "x.md"
    path.write_text("x\n")
    httpd, port, _done = start_live_server(path)
    try:
        _write_state(path, port)
        assert preview_url_if_running(path) == f"http://127.0.0.1:{port}/"
    finally:
        httpd.shutdown()
        httpd.server_close()
