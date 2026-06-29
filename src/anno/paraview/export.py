import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import paraview.servermanager as sm
import paraview.simple as pvs

# Per-session output files persisted across macro re-execs via the (process-global)
# environment, since the installed macro stub re-imports this module fresh on every
# trigger (so module-level globals reset, but os.environ survives for the process).
SESSION_ENV_KEY = "ANNO_ARRAY_COMMENTS_FILE"
SELECTION_ENV_KEY = "ANNO_SELECTION_FILE"


def _dataset_has_cell_data(data) -> bool:
    try:
        return data.GetCellData() is not None
    except AttributeError:
        return False


def _flatten_for_sampling(extract, timestamp: str):
    """Return ``(sample_source, vtk_data, merge_filter_or_None)`` for cell export.

    Composite extractions (Exodus/IOSS, .vtm, …) fetch as vtkMultiBlockDataSet
    without flat cell arrays; flatten through MergeBlocks when needed.
    """
    data = sm.Fetch(extract)
    if _dataset_has_cell_data(data):
        return extract, data, None

    merge = pvs.MergeBlocks(registrationName=f"AnnoMerge_{timestamp}", Input=extract)
    data = sm.Fetch(merge)
    if not _dataset_has_cell_data(data):
        pvs.Delete(merge)
        raise RuntimeError(
            "Could not flatten the selection for cell export: MergeBlocks did not produce a dataset with cell data."
        )
    return merge, data, merge


def _get_active_color_array():
    """Return (association, array_name) for the active coloring, or (None, None).

    (None, None) means Solid Color, no active source/representation, or the
    coloring could not be determined.
    """
    source = pvs.GetActiveSource()
    if source is None:
        return None, None
    try:
        rep = pvs.GetDisplayProperties(source)
    except Exception:
        return None, None
    if rep is None:
        return None, None

    can = getattr(rep, "ColorArrayName", None)
    if can is None:
        return None, None

    assoc, name = None, None
    # Preferred: explicit accessors on the ColorArrayName proxy.
    try:
        name = can.GetArrayName()
        assoc = can.GetAssociation()
    except Exception:
        pass
    # Fallback: the property is sequence-like [association, name].
    if not name:
        try:
            seq = list(can)
            if len(seq) >= 2:
                assoc, name = seq[0], seq[1]
            elif len(seq) == 1:
                name = seq[0]
        except Exception:
            pass

    if not name:  # empty string == Solid Color
        return None, None

    assoc_str = {0: "POINTS", 1: "CELLS", 2: "FIELD"}.get(assoc, assoc)
    return assoc_str, name


def _prompt_comment(prompt):
    """Prompt for a comment via an EXTERNAL process. Return text, or None if cancelled.

    `prompt` is the label shown in the dialog. We deliberately never import an
    in-process Qt binding: ParaView's bundled Python may not ship a binding matching
    the GUI's Qt major version, and loading a mismatched one (e.g. Qt5 PySide2/PyQt5
    into a Qt6 ParaView) hard-crashes the application at the native level. An external
    dialog runs in its own process, so it cannot clash.
    """
    if shutil.which("zenity"):
        try:
            res = subprocess.run(
                [
                    "zenity",
                    "--entry",
                    "--title=Anno — Comment",
                    f"--text={prompt}",
                    "--width=420",
                ],
                capture_output=True,
                text=True,
            )
        except Exception as exc:
            print(f"zenity dialog failed ({exc}); falling back to editor.")
        else:
            if res.returncode != 0:
                return None  # cancelled / closed
            text = res.stdout.strip()
            return text or None
    return _comment_via_editor()


def _comment_via_editor():
    """Fallback: capture a comment by editing a temp file in gvim (blocks until close)."""
    fd, tmp = tempfile.mkstemp(suffix=".md", prefix="anno_comment_")
    os.close(fd)
    try:
        subprocess.run(["gvim", "--nofork", tmp])
        with open(tmp) as f:
            text = f.read().strip()
    except Exception as exc:
        print(f"editor comment capture failed: {exc}")
        text = ""
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return text or None


def anno_array_comment():
    notes_dir = os.environ.get("ANNO_NOTES_DIR")
    if not notes_dir:
        print("ERROR: ANNO_NOTES_DIR environment variable not set!")
        return

    assoc, array_name = _get_active_color_array()
    if array_name is None:
        array_label = "(Solid Color / no active array)"
    else:
        array_label = f"{array_name} [{assoc}]"

    comment = _prompt_comment(f"Comment on coloring array:\n{array_label}")
    if comment is None:
        print("Anno array comment cancelled.")
        return

    existing = os.environ.get(SESSION_ENV_KEY)
    if existing:
        md_path = Path(existing)
        first = False
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        md_path = (Path(notes_dir) / f"array_comments_{timestamp}.md").resolve()
        os.environ[SESSION_ENV_KEY] = str(md_path)
        first = True

    entry_time = datetime.now().strftime("%H:%M:%S")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    with open(md_path, "a") as f:
        if first:
            session_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"# ParaView Array Comments — session {session_ts}\n\n")
        f.write(f"## {array_label}\n")
        f.write(f"*{entry_time}*\n\n")
        f.write(f"{comment}\n\n")
        f.write("---\n\n")

    print(f"Array comment {'created' if first else 'appended'}: {md_path}")


def anno_export_selection():
    notes_dir = os.environ.get("ANNO_NOTES_DIR")
    if not notes_dir:
        print("ERROR: ANNO_NOTES_DIR environment variable not set!")
        return

    source = pvs.GetActiveSource()
    if not source:
        print("ERROR: No active data source!")
        return

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    # Make the current interactive selection permanent so it can be sampled.
    extract = pvs.ExtractSelection(registrationName=f"AnnoExtract_{timestamp}", Input=source)
    pvs.Show(extract)
    pvs.Render()

    sample_source, data, merge = _flatten_for_sampling(extract, timestamp)
    n_cells = data.GetNumberOfCells()

    # Ask for a comment (cancel/empty -> export the selection without one).
    comment = _prompt_comment(f"Comment on selection ({n_cells} cells):")

    # Overlay a count annotation on the viewport, screenshot, then remove it.
    annotation = pvs.PythonAnnotation(Input=extract)
    annotation.Expression = f'"{n_cells} cells — {timestamp}"'
    pvs.Show(annotation)
    pvs.Render()

    screenshot_name = f"paraview_screenshot_{timestamp}.png"
    pvs.SaveScreenshot(str(Path(notes_dir) / screenshot_name), pvs.GetActiveView())

    pvs.Hide(annotation)
    pvs.Delete(annotation)
    pvs.Render()

    # Per-session file: created on the first export of the session, appended after.
    existing = os.environ.get(SELECTION_ENV_KEY)
    if existing:
        md_path = Path(existing)
        first = False
    else:
        session_stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        md_path = (Path(notes_dir) / f"paraview_selection_{session_stamp}.md").resolve()
        os.environ[SELECTION_ENV_KEY] = str(md_path)
        first = True

    # Build this selection's entry.
    entry_time = datetime.now().strftime("%H:%M:%S")
    source_name = getattr(source, "FileName", source.GetClassName())
    entry = [f"## Selection {entry_time} — {n_cells} cells\n"]
    if comment:
        entry.append(f"{comment}\n")
    entry.append(f"**Source:** {source_name} · **Filter:** ExtractSelection\n")
    entry.append(f"![viewport]({screenshot_name})\n")

    cell_data = data.GetCellData()
    array_names = [cell_data.GetArray(i).GetName() for i in range(cell_data.GetNumberOfArrays())]
    entry.append("| Cell ID | Center X | Center Y | Center Z | " + " | ".join(array_names) + " |")
    entry.append("|" + "---|" * (4 + len(array_names)))

    cell_centers = pvs.CellCenters(Input=sample_source)
    centers_data = sm.Fetch(cell_centers)
    for i in range(n_cells):
        orig_id = (
            data.GetCellData().GetArray("vtkOriginalCellIds").GetValue(i)
            if data.GetCellData().HasArray("vtkOriginalCellIds")
            else i
        )
        center = centers_data.GetPoint(i)
        values = [f"{cell_data.GetArray(a_idx).GetValue(i):.6g}" for a_idx in range(cell_data.GetNumberOfArrays())]
        row = f"| {orig_id} | {center[0]:.6f} | {center[1]:.6f} | {center[2]:.6f} | "
        entry.append(row + " | ".join(values) + " |")
    entry.append("\n---\n")

    md_path.parent.mkdir(parents=True, exist_ok=True)
    with open(md_path, "a") as f:
        if first:
            session_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"# ParaView Selections — session {session_ts}\n\n")
        f.write("\n".join(entry) + "\n")

    # Tidy the pipeline so repeated exports in one session don't pile up filters.
    pvs.Delete(cell_centers)
    if merge is not None:
        pvs.Delete(merge)
    pvs.Hide(extract)
    pvs.Delete(extract)
    pvs.Render()

    print(f"Selection {'created' if first else 'appended'}: {md_path}")
