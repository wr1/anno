import os
import shlex
import subprocess
from datetime import datetime
from pathlib import Path

import paraview.servermanager as sm
import paraview.simple as pvs

# Persisted across macro re-execs via the (process-global) environment, since the
# installed macro stub re-imports this module fresh on every trigger.
SESSION_ENV_KEY = "ANNO_ARRAY_COMMENTS_FILE"


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


def _qt_get_comment(array_label):
    """Pop a modal multi-line input dialog. Return the comment, or None if cancelled."""
    qtwidgets = None
    for modname in ("PySide6.QtWidgets", "PySide2.QtWidgets", "PyQt5.QtWidgets"):
        try:
            qtwidgets = __import__(modname, fromlist=["QtWidgets"])
            break
        except Exception:
            continue
    if qtwidgets is None:
        print("ERROR: No Qt bindings available in ParaView for the comment dialog.")
        return None

    app = qtwidgets.QApplication.instance()
    if app is None:  # should not happen inside the running GUI, but be safe
        app = qtwidgets.QApplication([])

    title = "Anno — Array Comment"
    prompt = f"Comment on coloring array:\n\n{array_label}"
    text, ok = qtwidgets.QInputDialog.getMultiLineText(None, title, prompt, "")
    if not ok:
        return None
    text = text.strip()
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

    comment = _qt_get_comment(array_label)
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

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    md_path = Path(notes_dir) / f"paraview_selection_{timestamp}.md"

    source = pvs.GetActiveSource()
    if not source:
        print("ERROR: No active data source!")
        return

    # Make current interactive selection permanent
    extract = pvs.ExtractSelection(registrationName="AnnoExtract", Input=source)
    pvs.Show(extract)
    pvs.Render()

    data = sm.Fetch(extract)
    n_cells = data.GetNumberOfCells()

    # Overlay annotation on viewport, screenshot, then remove
    annotation = pvs.PythonAnnotation(Input=extract)
    annotation.Expression = f'"{n_cells} cells — {timestamp}"'
    pvs.Show(annotation)
    pvs.Render()

    screenshot_path = Path(notes_dir) / f"paraview_screenshot_{timestamp}.png"
    pvs.SaveScreenshot(str(screenshot_path), pvs.GetActiveView())

    pvs.Hide(annotation)
    pvs.Delete(annotation)
    pvs.Render()

    # Build markdown
    md = [f"# ParaView Selection — {timestamp}\n"]
    md.append(f"**Source file:** {getattr(source, 'FileName', source.GetClassName())}\n")
    md.append("**Filter:** ExtractSelection\n")
    md.append(f"![viewport]({screenshot_path})\n")

    cell_data = data.GetCellData()
    array_names = [cell_data.GetArray(i).GetName() for i in range(cell_data.GetNumberOfArrays())]
    header = "| Cell ID | Center X | Center Y | Center Z | " + " | ".join(array_names) + " |"
    md.append(header)
    md.append("|" + "---|" * (4 + len(array_names)))

    # Cell centers
    cell_centers = pvs.CellCenters(Input=extract)
    centers_data = sm.Fetch(cell_centers)

    for i in range(data.GetNumberOfCells()):
        orig_id = (
            data.GetCellData().GetArray("vtkOriginalCellIds").GetValue(i)
            if data.GetCellData().HasArray("vtkOriginalCellIds")
            else i
        )
        center = centers_data.GetPoint(i)

        values = [f"{cell_data.GetArray(a_idx).GetValue(i):.6g}" for a_idx in range(cell_data.GetNumberOfArrays())]

        md.append(f"| {orig_id} | {center[0]:.6f} | {center[1]:.6f} | {center[2]:.6f} | " + " | ".join(values) + " |")

    md.append("\n---\n*Exported via Anno macro*")

    # Write file
    md_path.parent.mkdir(parents=True, exist_ok=True)
    with open(md_path, "w") as f:
        f.write("\n".join(md))

    # Open in gvim; on close copy full md content to clipboard
    p = shlex.quote(str(md_path))
    subprocess.Popen(["bash", "-c", f"gvim --nofork {p} ; xclip -selection clipboard < {p}"])

    print(f"Saved & opened in gvim: {md_path}")
