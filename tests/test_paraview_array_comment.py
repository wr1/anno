"""Tests for the ParaView array-comment macro logic.

ParaView's `paraview.simple` / `paraview.servermanager` modules only exist inside
ParaView, so they are stubbed in sys.modules before loading export.py. The Qt
dialog and the active-coloring lookup are then patched per test, letting us cover
the real session/append/Solid-Color/cancel logic without a live ParaView GUI.

Runs standalone (`python tests/test_paraview_array_comment.py`) or under pytest.
"""

import importlib.util
import os
import sys
import tempfile
import types
from pathlib import Path

_EXPORT_PY = Path(__file__).resolve().parent.parent / "src" / "anno" / "paraview" / "export.py"


def _load_export_module():
    """Load export.py with stubbed paraview modules; return the module object."""
    pkg = types.ModuleType("paraview")
    simple = types.ModuleType("paraview.simple")
    sm = types.ModuleType("paraview.servermanager")
    pkg.simple = simple
    pkg.servermanager = sm
    sys.modules["paraview"] = pkg
    sys.modules["paraview.simple"] = simple
    sys.modules["paraview.servermanager"] = sm

    spec = importlib.util.spec_from_file_location("anno_pv_export_test", _EXPORT_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MOD = _load_export_module()

# Capture the real implementations: the full-flow tests monkeypatch these names
# on MOD, so the unit tests below call the originals directly.
_ORIG_GET = MOD._get_active_color_array
_ORIG_QT = MOD._qt_get_comment


def _fresh_session(tmp):
    """Reset env so the next comment is treated as the first of a session."""
    os.environ["ANNO_NOTES_DIR"] = str(tmp)
    os.environ.pop(MOD.SESSION_ENV_KEY, None)


def _comment_files(tmp):
    return sorted(Path(tmp).glob("array_comments_*.md"))


def test_first_comment_creates_file_with_header():
    with tempfile.TemporaryDirectory() as tmp:
        _fresh_session(tmp)
        MOD._get_active_color_array = lambda: ("POINTS", "Displacement_Z")
        MOD._qt_get_comment = lambda label: "looks suspicious near the root"

        MOD.anno_array_comment()

        files = _comment_files(tmp)
        assert len(files) == 1, files
        name = files[0].name
        # array_comments_YYYY-MM-DD_HHMMSS.md — time portion has no dashes.
        assert name.startswith("array_comments_") and name.endswith(".md")
        ts = name[len("array_comments_") : -len(".md")]
        date_part, time_part = ts.split("_")
        assert len(date_part.split("-")) == 3 and "-" not in time_part and len(time_part) == 6
        text = files[0].read_text()
        assert text.count("# ParaView Array Comments — session") == 1
        assert "## Displacement_Z [POINTS]" in text
        assert "looks suspicious near the root" in text
        assert os.environ.get(MOD.SESSION_ENV_KEY) == str(files[0])
    print("ok: first comment creates file with header")


def test_second_comment_appends_to_same_file():
    with tempfile.TemporaryDirectory() as tmp:
        _fresh_session(tmp)
        MOD._get_active_color_array = lambda: ("POINTS", "Displacement_Z")
        MOD._qt_get_comment = lambda label: "first comment"
        MOD.anno_array_comment()

        MOD._get_active_color_array = lambda: ("CELLS", "von_Mises")
        MOD._qt_get_comment = lambda label: "second comment"
        MOD.anno_array_comment()

        files = _comment_files(tmp)
        assert len(files) == 1, files  # appended, not a new file
        text = files[0].read_text()
        assert text.count("# ParaView Array Comments — session") == 1  # header only once
        assert "## Displacement_Z [POINTS]" in text
        assert "## von_Mises [CELLS]" in text
        assert "first comment" in text and "second comment" in text
    print("ok: second comment appends to same file")


def test_solid_color_label():
    with tempfile.TemporaryDirectory() as tmp:
        _fresh_session(tmp)
        MOD._get_active_color_array = lambda: (None, None)
        MOD._qt_get_comment = lambda label: "no array selected here"
        MOD.anno_array_comment()

        text = _comment_files(tmp)[0].read_text()
        assert "## (Solid Color / no active array)" in text
        assert "no array selected here" in text
    print("ok: solid color labelled")


def test_cancel_creates_no_file():
    with tempfile.TemporaryDirectory() as tmp:
        _fresh_session(tmp)
        MOD._get_active_color_array = lambda: ("POINTS", "Displacement_Z")
        MOD._qt_get_comment = lambda label: None  # user cancelled
        MOD.anno_array_comment()

        assert _comment_files(tmp) == []
        assert MOD.SESSION_ENV_KEY not in os.environ
    print("ok: cancel creates no file")


def test_missing_notes_dir_is_noop():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ.pop("ANNO_NOTES_DIR", None)
        os.environ.pop(MOD.SESSION_ENV_KEY, None)
        MOD._get_active_color_array = lambda: ("POINTS", "X")
        MOD._qt_get_comment = lambda label: "x"
        MOD.anno_array_comment()  # must not raise
        assert _comment_files(tmp) == []
    print("ok: missing ANNO_NOTES_DIR is a no-op")


def test_get_active_color_array_accessor_and_solid():
    class Can:
        def __init__(self, assoc, name):
            self._assoc, self._name = assoc, name

        def GetArrayName(self):
            return self._name

        def GetAssociation(self):
            return self._assoc

    class Rep:
        def __init__(self, can):
            self.ColorArrayName = can

    src = object()
    MOD.pvs.GetActiveSource = lambda: src

    MOD.pvs.GetDisplayProperties = lambda s: Rep(Can(0, "Temp"))
    assert _ORIG_GET() == ("POINTS", "Temp")

    MOD.pvs.GetDisplayProperties = lambda s: Rep(Can(1, "Stress"))
    assert _ORIG_GET() == ("CELLS", "Stress")

    # Empty name == Solid Color
    MOD.pvs.GetDisplayProperties = lambda s: Rep(Can(0, ""))
    assert _ORIG_GET() == (None, None)

    # No active source
    MOD.pvs.GetActiveSource = lambda: None
    assert _ORIG_GET() == (None, None)
    print("ok: _get_active_color_array accessor + solid + no-source")


def test_get_active_color_array_sequence_fallback():
    class SeqCan(list):
        # No GetArrayName/GetAssociation -> forces the list() fallback path.
        pass

    class Rep:
        def __init__(self, can):
            self.ColorArrayName = can

    MOD.pvs.GetActiveSource = lambda: object()
    MOD.pvs.GetDisplayProperties = lambda s: Rep(SeqCan(["CELLS", "Pressure"]))
    assert _ORIG_GET() == ("CELLS", "Pressure")
    print("ok: _get_active_color_array sequence fallback")


def test_qt_get_comment_with_stubbed_binding():
    # Inject a fake PySide6.QtWidgets so the try-import chain resolves.
    captured = {}

    class FakeApp:
        @staticmethod
        def instance():
            return object()

    class FakeInputDialog:
        ret = ("  hello world  ", True)

        @staticmethod
        def getMultiLineText(parent, title, prompt, text):
            captured["prompt"] = prompt
            return FakeInputDialog.ret

    qtw = types.ModuleType("PySide6.QtWidgets")
    qtw.QApplication = FakeApp
    qtw.QInputDialog = FakeInputDialog
    pkg = types.ModuleType("PySide6")
    pkg.QtWidgets = qtw
    sys.modules["PySide6"] = pkg
    sys.modules["PySide6.QtWidgets"] = qtw
    try:
        assert _ORIG_QT("Arr [POINTS]") == "hello world"  # stripped
        assert "Arr [POINTS]" in captured["prompt"]
        FakeInputDialog.ret = ("ignored", False)  # cancelled
        assert _ORIG_QT("Arr") is None
        FakeInputDialog.ret = ("   ", True)  # empty after strip
        assert _ORIG_QT("Arr") is None
    finally:
        del sys.modules["PySide6.QtWidgets"]
        del sys.modules["PySide6"]
    print("ok: _qt_get_comment with stubbed Qt binding")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"\nAll {len(tests)} tests passed.")
