import os
import shlex
import subprocess
from datetime import datetime
from pathlib import Path

import paraview.servermanager as sm
import paraview.simple as pvs


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
