import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from anno.constants import DEFAULT_LOG_FILE, DEFAULT_PARA_NOTES_DIR
from anno.log_util import log_activity


def _launch_paraview(mesh_paths: list[Path], notes_dir: str) -> None:
    notes_path = Path(notes_dir)
    notes_path.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["ANNO_NOTES_DIR"] = str(notes_path.resolve())
    env["ANNO_MESH_FILES"] = ":".join(str(p) for p in mesh_paths)

    pv_dir = Path(__file__).parent / "paraview"
    env["ANNO_EXPORT_PY"] = str(pv_dir / "export.py")

    subprocess.Popen(["paraview", "--pyscript", str(pv_dir / "startup.py")], env=env)
    for p in mesh_paths:
        log_activity("para_open", p)
        print(f"ParaView launched  : {p}")
    print(f"ANNO_NOTES_DIR     : {env['ANNO_NOTES_DIR']}")


def _last_para_mesh(name: Optional[str] = None) -> Optional[Path]:
    if not DEFAULT_LOG_FILE.exists():
        return None
    entries = [json.loads(line) for line in DEFAULT_LOG_FILE.read_text().splitlines() if line.strip()]
    para = [e for e in entries if e.get("action") == "para_open"]
    if name:
        para = [e for e in para if Path(e["file"]).stem == name]
    return Path(para[-1]["file"]) if para else None


def cmd_para_new(files, notes_dir: str = str(DEFAULT_PARA_NOTES_DIR)) -> None:
    if not shutil.which("paraview"):
        sys.exit("para requires 'paraview' on PATH")
    mesh_paths = []
    for f in files:
        p = Path(f).resolve()
        if not p.exists():
            sys.exit(f"File not found: {p}")
        mesh_paths.append(p)
    _launch_paraview(mesh_paths, notes_dir)


def cmd_para_open(name: Optional[str] = None, notes_dir: str = str(DEFAULT_PARA_NOTES_DIR)) -> None:
    if not shutil.which("paraview"):
        sys.exit("para requires 'paraview' on PATH")
    mesh_path = _last_para_mesh(name)
    if mesh_path is None:
        msg = f"No para session found for {name!r}" if name else "No previous para session in log"
        sys.exit(msg)
    if not mesh_path.exists():
        sys.exit(f"Mesh no longer exists: {mesh_path}")
    _launch_paraview([mesh_path], notes_dir)
