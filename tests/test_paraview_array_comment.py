"""Tests for the ParaView array-comment macro logic.

ParaView's `paraview.simple` / `paraview.servermanager` modules only exist inside
ParaView, so they are stubbed in sys.modules before loading export.py. The comment
prompt (an external zenity/gvim process) and the active-coloring lookup are then
patched per test, letting us cover the real session/append/Solid-Color/cancel logic
without a live ParaView GUI.

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
_ORIG_PROMPT = MOD._prompt_comment


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
        MOD._prompt_comment = lambda label: "looks suspicious near the root"

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
        MOD._prompt_comment = lambda label: "first comment"
        MOD.anno_array_comment()

        MOD._get_active_color_array = lambda: ("CELLS", "von_Mises")
        MOD._prompt_comment = lambda label: "second comment"
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
        MOD._prompt_comment = lambda label: "no array selected here"
        MOD.anno_array_comment()

        text = _comment_files(tmp)[0].read_text()
        assert "## (Solid Color / no active array)" in text
        assert "no array selected here" in text
    print("ok: solid color labelled")


def test_cancel_creates_no_file():
    with tempfile.TemporaryDirectory() as tmp:
        _fresh_session(tmp)
        MOD._get_active_color_array = lambda: ("POINTS", "Displacement_Z")
        MOD._prompt_comment = lambda label: None  # user cancelled
        MOD.anno_array_comment()

        assert _comment_files(tmp) == []
        assert MOD.SESSION_ENV_KEY not in os.environ
    print("ok: cancel creates no file")


def test_missing_notes_dir_is_noop():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ.pop("ANNO_NOTES_DIR", None)
        os.environ.pop(MOD.SESSION_ENV_KEY, None)
        MOD._get_active_color_array = lambda: ("POINTS", "X")
        MOD._prompt_comment = lambda label: "x"
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


class _FakeProc:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


def test_prompt_comment_uses_zenity_external_process():
    """Confirm the comment is captured via an external process and NO Qt binding
    is imported (the Qt-into-ParaView mismatch is what crashed the GUI)."""
    real_which, real_run = MOD.shutil.which, MOD.subprocess.run
    captured = {}
    try:
        MOD.shutil.which = lambda name: "/usr/bin/zenity" if name == "zenity" else None

        def fake_run(cmd, capture_output=False, text=False):
            captured["cmd"] = cmd
            return _FakeProc(0, "  a tidy comment \n")

        MOD.subprocess.run = fake_run
        assert _ORIG_PROMPT("Temp [POINTS]") == "a tidy comment"  # stripped
        assert captured["cmd"][0] == "zenity"
        assert any("Temp [POINTS]" in str(a) for a in captured["cmd"])

        MOD.subprocess.run = lambda *a, **k: _FakeProc(1, "ignored")  # cancelled
        assert _ORIG_PROMPT("Temp") is None

        MOD.subprocess.run = lambda *a, **k: _FakeProc(0, "   \n")  # empty
        assert _ORIG_PROMPT("Temp") is None
    finally:
        MOD.shutil.which, MOD.subprocess.run = real_which, real_run
    # No Qt binding should ever have been imported by loading/using the module.
    assert not any(m.startswith(("PySide", "PyQt")) for m in sys.modules)
    print("ok: _prompt_comment uses external zenity, no Qt import")


def test_prompt_comment_editor_fallback_reads_temp_file():
    real_which, real_run = MOD.shutil.which, MOD.subprocess.run
    try:
        MOD.shutil.which = lambda name: None  # no zenity -> gvim fallback

        def fake_run(cmd, *a, **k):
            # cmd == ["gvim", "--nofork", <path>]; simulate the user typing + saving.
            with open(cmd[-1], "w") as f:
                f.write("edited in the editor\n")
            return _FakeProc(0, "")

        MOD.subprocess.run = fake_run
        assert _ORIG_PROMPT("X [CELLS]") == "edited in the editor"
    finally:
        MOD.shutil.which, MOD.subprocess.run = real_which, real_run
    print("ok: _prompt_comment gvim editor fallback")


class _FakeArray:
    def __init__(self, name, values):
        self._name, self._values = name, values

    def GetName(self):
        return self._name

    def GetValue(self, i):
        return self._values[i]


class _FakeCellData:
    def __init__(self, arrays):
        self._arrays = arrays

    def GetNumberOfArrays(self):
        return len(self._arrays)

    def GetArray(self, key):
        if isinstance(key, int):
            return self._arrays[key]
        return next((a for a in self._arrays if a._name == key), None)

    def HasArray(self, name):
        return any(a._name == name for a in self._arrays)


class _FakeData:
    def __init__(self, n, cell_data):
        self._n, self._cd = n, cell_data

    def GetNumberOfCells(self):
        return self._n

    def GetCellData(self):
        return self._cd


class _FakeCenters:
    def GetPoint(self, i):
        return (float(i), float(i) + 0.5, 0.0)


class _FakeMultiBlock:
    """Composite dataset: has cell counts but NO GetCellData (like vtkMultiBlockDataSet)."""

    def __init__(self, n):
        self._n = n

    def GetNumberOfCells(self):
        return self._n


class _FakeFilter:
    def __init__(self, kind):
        self.kind = kind


class _FakeSource:
    FileName = "blade.vtu"

    def GetClassName(self):
        return "vtkUnstructuredGrid"


class _FakeAnnotation:
    Expression = None


def _install_paraview_fakes(
    n_cells=2,
    arrays=(("Temp", (1.0, 2.0)),),
    multiblock=False,
    merge_still_composite=False,
):
    """Install pvs/sm fakes; returns a dict recording filter activity.

    With multiblock=True, fetching the extract yields a composite dataset without
    GetCellData (as vtkMultiBlockDataSet); only a MergeBlocks filter's output is flat.
    With merge_still_composite=True, MergeBlocks runs but still returns a composite.
    """
    data = _FakeData(n_cells, _FakeCellData([_FakeArray(n, v) for n, v in arrays]))
    calls = {"merge_blocks": 0, "deleted": []}

    def make_filter(kind):
        calls.setdefault(kind, 0)
        calls[kind] += 1
        return _FakeFilter(kind)

    MOD.pvs.GetActiveSource = lambda: _FakeSource()
    MOD.pvs.ExtractSelection = lambda registrationName=None, Input=None: make_filter("extract")
    MOD.pvs.CellCenters = lambda Input=None: make_filter("centers")
    MOD.pvs.MergeBlocks = lambda registrationName=None, Input=None: (
        calls.__setitem__("merge_blocks", calls["merge_blocks"] + 1) or _FakeFilter("merged")
    )
    MOD.pvs.PythonAnnotation = lambda Input=None: _FakeAnnotation()
    for noop in ("Show", "Hide", "Render", "GetActiveView", "SaveScreenshot"):
        setattr(MOD.pvs, noop, lambda *a, **k: None)
    MOD.pvs.Delete = lambda obj=None: calls["deleted"].append(getattr(obj, "kind", obj.__class__.__name__))

    def fetch(obj):
        kind = getattr(obj, "kind", None)
        if kind == "centers":
            return _FakeCenters()
        if multiblock:
            if kind == "merged" and not merge_still_composite:
                return data
            return _FakeMultiBlock(n_cells)
        return data

    MOD.sm.Fetch = fetch
    return calls


def test_export_selection_first_creates_with_comment_and_table():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ANNO_NOTES_DIR"] = str(tmp)
        os.environ.pop(MOD.SELECTION_ENV_KEY, None)
        _install_paraview_fakes(n_cells=2)
        MOD._prompt_comment = lambda prompt: "interesting cluster at the root"
        MOD.anno_export_selection()

        files = sorted(Path(tmp).glob("paraview_selection_*.md"))
        assert len(files) == 1, files
        text = files[0].read_text()
        assert text.count("# ParaView Selections — session") == 1
        assert "## Selection" in text and "2 cells" in text
        assert "interesting cluster at the root" in text
        assert "**Source:** blade.vtu" in text
        assert "![viewport](paraview_screenshot_" in text
        assert "| Cell ID | Center X | Center Y | Center Z | Temp |" in text
        assert os.environ.get(MOD.SELECTION_ENV_KEY) == str(files[0])
    print("ok: export selection first creates file with comment + table")


def test_export_selection_appends_and_omits_empty_comment():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ANNO_NOTES_DIR"] = str(tmp)
        os.environ.pop(MOD.SELECTION_ENV_KEY, None)
        _install_paraview_fakes(n_cells=1)

        MOD._prompt_comment = lambda prompt: "first selection"
        MOD.anno_export_selection()
        MOD._prompt_comment = lambda prompt: None  # cancelled -> no comment
        MOD.anno_export_selection()

        files = sorted(Path(tmp).glob("paraview_selection_*.md"))
        assert len(files) == 1, files  # appended to the same session file
        text = files[0].read_text()
        assert text.count("# ParaView Selections — session") == 1  # header once
        assert text.count("## Selection") == 2
        assert "first selection" in text
    print("ok: export selection appends; empty comment omitted")


def test_export_selection_multiblock_source_merges_blocks():
    """Composite (e.g. Exodus/multiblock) sources crash GetCellData unless flattened."""
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ANNO_NOTES_DIR"] = str(tmp)
        os.environ.pop(MOD.SELECTION_ENV_KEY, None)
        calls = _install_paraview_fakes(n_cells=2, multiblock=True)
        MOD._prompt_comment = lambda prompt: "multiblock selection"
        MOD.anno_export_selection()

        files = sorted(Path(tmp).glob("paraview_selection_*.md"))
        assert len(files) == 1, files
        text = files[0].read_text()
        assert "2 cells" in text
        assert "multiblock selection" in text
        assert "| Cell ID | Center X | Center Y | Center Z | Temp |" in text
        assert calls["merge_blocks"] == 1
        assert "merged" in calls["deleted"]  # merge filter cleaned up
    print("ok: export selection flattens multiblock sources via MergeBlocks")


def test_export_selection_flat_source_skips_merge_blocks():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ANNO_NOTES_DIR"] = str(tmp)
        os.environ.pop(MOD.SELECTION_ENV_KEY, None)
        calls = _install_paraview_fakes(n_cells=1)
        MOD._prompt_comment = lambda prompt: None
        MOD.anno_export_selection()

        assert calls["merge_blocks"] == 0
        assert "extract" in calls["deleted"] and "centers" in calls["deleted"]
    print("ok: export selection skips MergeBlocks for flat datasets")


def test_export_selection_merge_failure_raises():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ANNO_NOTES_DIR"] = str(tmp)
        os.environ.pop(MOD.SELECTION_ENV_KEY, None)
        calls = _install_paraview_fakes(n_cells=1, multiblock=True, merge_still_composite=True)
        MOD._prompt_comment = lambda prompt: None
        try:
            MOD.anno_export_selection()
        except RuntimeError as exc:
            assert "MergeBlocks" in str(exc)
            assert calls["merge_blocks"] == 1
            assert "merged" in calls["deleted"]
        else:
            raise AssertionError("expected RuntimeError when MergeBlocks stays composite")
    print("ok: export selection raises when MergeBlocks cannot flatten")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"\nAll {len(tests)} tests passed.")
