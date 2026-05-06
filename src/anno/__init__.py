import base64
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from treeparse import argument, cli, color_config, command, group, option
from treeparse.utils.color_config import ColorTheme

DEFAULT_NOTES_DIR = Path("notes") / "draw"
DEFAULT_SCREENSHOTS_DIR = Path.home() / "Pictures" / "Screenshots"
DEFAULT_MIND_DIR = Path("notes") / "mind"
DEFAULT_LOG_FILE = Path.home() / ".anno" / "log.jsonl"
DEFAULT_PARA_NOTES_DIR = Path("notes") / "para"
MINDER = "com.github.phase1geo.minder"

EXPORT_DPI = 300
DEFAULT_FONT_SIZE = 30

# Force X11 backend to avoid Inkscape SIGSEGV on Wayland (known bug in 1.2.x)
_INKSCAPE_ENV = {**os.environ, "GDK_BACKEND": "x11"}


# --- activity log ---


def _log(action: str, path: Path) -> None:
    DEFAULT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "action": action,
        "file": str(path.resolve()),
        "type": path.suffix.lstrip("."),
    }
    with DEFAULT_LOG_FILE.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


# --- image helpers ---


def _image_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", data[16:24])
        return w, h
    if data[:2] == b"\xff\xd8":  # JPEG
        i = 2
        while i + 4 < len(data):
            if data[i] != 0xFF:
                break
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB):
                h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                return w, h
            length = struct.unpack(">H", data[i + 2 : i + 4])[0]
            i += 2 + length
    return 800, 600


def _embed_image_into_svg(img_path: Path, svg_path: Path) -> None:
    data = base64.b64encode(img_path.read_bytes()).decode()
    w, h = _image_dimensions(img_path)
    mime = "image/jpeg" if img_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:xlink="http://www.w3.org/1999/xlink"
     xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <sodipodi:namedview inkscape:document-units="px"/>
  <style>
    text, tspan {{ font-size: {DEFAULT_FONT_SIZE}px; }}
  </style>
  <image xlink:href="data:{mime};base64,{data}" x="0" y="0" width="{w}" height="{h}"/>
</svg>"""
    svg_path.write_text(svg)


def _export_png(svg_path: Path) -> Path:
    out = svg_path.with_suffix(".png")
    subprocess.run(
        [
            "inkscape",
            "--export-type=png",
            f"--export-dpi={EXPORT_DPI}",
            f"--export-filename={out}",
            str(svg_path),
        ],
        check=True,
        stderr=subprocess.DEVNULL,
        env=_INKSCAPE_ENV,
    )
    return out


def _run_inkscape_and_export(svg: Path) -> None:
    svg = svg.resolve()
    result = subprocess.run(["inkscape", str(svg)], env=_INKSCAPE_ENV)
    if result.returncode not in (0, -11):  # -11 = SIGSEGV (known on some builds on close)
        sys.exit(f"inkscape exited with code {result.returncode}")
    _log("ink_export", svg)
    out_png = _export_png(svg)
    _copy_to_clipboard(out_png)
    print(f"saved  : {svg}")
    print(f"saved  : {out_png}")
    print("copied : PNG to clipboard")


def _copy_to_clipboard(png_path: Path) -> None:
    if shutil.which("xclip"):
        subprocess.run(
            [
                "xclip",
                "-selection",
                "clipboard",
                "-t",
                "image/png",
                "-i",
                str(png_path),
            ],
            check=True,
        )
    elif sys.platform == "darwin":
        subprocess.run(
            [
                "osascript",
                "-e",
                f'set the clipboard to (read (POSIX file "{png_path}") as \xab class PNGf\xbb)',
            ],
            check=True,
        )
    else:
        print("clipboard copy not supported on this platform", file=sys.stderr)


def _copy_text_to_clipboard(text: str) -> None:
    if shutil.which("xclip"):
        subprocess.run(["xclip", "-selection", "clipboard"], input=text, text=True, check=True)
    elif sys.platform == "darwin":
        subprocess.run(["pbcopy"], input=text, text=True, check=True)
    else:
        print("clipboard copy not supported on this platform", file=sys.stderr)


# --- ink callbacks ---


def _make_blank_svg(path: Path, w: int = 1920, h: int = 1080) -> None:
    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <sodipodi:namedview inkscape:document-units="px"/>
  <style>
    text, tspan {{ font-size: {DEFAULT_FONT_SIZE}px; }}
  </style>
</svg>"""
    path.write_text(svg)


def cmd_ink_new(name: str = "", notes_dir: str = str(DEFAULT_NOTES_DIR)) -> None:
    out_dir = Path(notes_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if name:
        svg = out_dir / f"{Path(name).stem}.svg"
        if svg.exists():
            sys.exit(f"Already exists: {svg}")
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        svg = out_dir / f"fig_{ts}.svg"
    _make_blank_svg(svg)
    print(f"opening {svg}")
    _run_inkscape_and_export(svg)


def cmd_ink_open(name: str, notes_dir: str = str(DEFAULT_NOTES_DIR)) -> None:
    out_dir = Path(notes_dir)
    svg = out_dir / f"{Path(name).stem}.svg"
    if not svg.exists():
        sys.exit(f"Not found: {svg}")
    print(f"opening {svg}")
    _run_inkscape_and_export(svg)


def cmd_ink_fig(file: Optional[str] = None, notes_dir: str = str(DEFAULT_NOTES_DIR)) -> None:
    if file is None:
        scr_dir = DEFAULT_SCREENSHOTS_DIR
        pngs = sorted(scr_dir.glob("*.png"), key=lambda p: p.stat().st_mtime)
        if not pngs:
            sys.exit(f"No PNGs found in {scr_dir}")
        img_path = pngs[-1].resolve()
        print(f"latest : {img_path.name}")
    else:
        img_path = Path(file).resolve()
        if not img_path.exists():
            sys.exit(f"File not found: {img_path}")

    out_dir = Path(notes_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = img_path.stem.lower().replace(" ", "_")
    svg = out_dir / f"{stem}_{ts}.svg"

    _embed_image_into_svg(img_path, svg)
    print(f"opening {svg}")
    _run_inkscape_and_export(svg)


def cmd_ink_screen(
    notes_dir: str = str(DEFAULT_NOTES_DIR),
    screenshots_dir: str = str(DEFAULT_SCREENSHOTS_DIR),
) -> None:
    scr_dir = Path(screenshots_dir)
    pngs = sorted(scr_dir.glob("*.png"), key=lambda p: p.stat().st_mtime)
    if not pngs:
        sys.exit(f"No PNGs found in {scr_dir}")
    latest = pngs[-1]
    print(f"latest : {latest.name}")
    cmd_ink_fig(str(latest), notes_dir)


# --- minder helpers ---

_STYLE_COMMON = (
    ' branchmargin="100" branchradius="25" linktype="straight" linkwidth="4" linkarrow="false"'
    ' linkdash="solid" nodeborder="underlined" nodewidth="200" nodeborderwidth="4" nodefill="false"'
    ' nodemargin="8" nodepadding="6" nodefont="Sans 11" nodemarkup="true" connectiondash="dotted"'
    ' connectionlwidth="2" connectionarrow="fromto" connectionpadding="3" connectionfont="Sans 10"'
    ' connectiontwidth="100" calloutfont="Sans 12" calloutpadding="5" calloutptrwidth="20"'
    ' calloutptrlength="20"'
)
_STYLES = (
    '<style level="0" isset="false" branchmargin="100" branchradius="25" linktype="straight"'
    ' linkwidth="4" linkarrow="false" linkdash="solid" nodeborder="rounded" nodewidth="200"'
    ' nodeborderwidth="4" nodefill="false" nodemargin="10" nodepadding="10" nodefont="Sans 11"'
    ' nodemarkup="true" connectiondash="dotted" connectionlwidth="2" connectionarrow="fromto"'
    ' connectionpadding="3" connectionfont="Sans 10" connectiontwidth="100" calloutfont="Sans 12"'
    ' calloutpadding="5" calloutptrwidth="20" calloutptrlength="20"/>'
    + "".join(f'<style level="{i}" isset="false"{_STYLE_COMMON}/>' for i in range(1, 11))
)


def _make_minder_file(path: Path) -> None:
    path.write_text(
        '<?xml version="1.0"?>\n'
        '<minder version="1.16.2" parent-etag="0" etag="0">\n'
        '  <theme name="dark" label="Dark" index="1"/>\n'
        f"  <styles>{_STYLES}</styles>\n"
        "  <images/>\n"
        "  <nodes/>\n"
        "  <selected-nodes/>\n"
        "  <groups/>\n"
        "  <stickers/>\n"
        '  <nodelinks id="0"/>\n'
        "</minder>\n"
    )


# Wrap each Minder launch in its own dbus-run-session so GApplication's
# singleton lock can't route this invocation to an already-running window;
# this lets multiple `anno mind …` sessions coexist.
def _run_minder(minder_file: Path, md_file: Path) -> None:
    subprocess.run(
        ["dbus-run-session", "--", MINDER, str(minder_file)],
        check=True,
    )
    _log("mind_export", minder_file)
    subprocess.run(
        ["dbus-run-session", "--", MINDER, str(minder_file), "--export=markdown", str(md_file)],
        capture_output=True,
    )
    md = md_file.read_text() if md_file.exists() else ""
    _copy_text_to_clipboard(md)
    print(f"saved  : {minder_file}")
    print(f"saved  : {md_file}")
    print("copied : markdown to clipboard")


# --- mind callbacks ---


def cmd_mind_new(name: str = "", mind_dir: str = str(DEFAULT_MIND_DIR)) -> None:
    out_dir = Path(mind_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if name:
        minder_file = out_dir / f"{Path(name).stem}.minder"
        if minder_file.exists():
            sys.exit(f"Already exists: {minder_file}")
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = f"mm_{ts}"
        minder_file = out_dir / f"{stem}.minder"
    md_file = minder_file.with_suffix(".md")
    _make_minder_file(minder_file)
    _run_minder(minder_file, md_file)


def cmd_mind_open(name: str, mind_dir: str = str(DEFAULT_MIND_DIR)) -> None:
    out_dir = Path(mind_dir).resolve()
    minder_file = out_dir / f"{Path(name).stem}.minder"
    if not minder_file.exists():
        sys.exit(f"Not found: {minder_file}")
    md_file = minder_file.with_suffix(".md")
    _run_minder(minder_file, md_file)


# --- list callback ---


def cmd_list(notes_dir: str = str(DEFAULT_NOTES_DIR), mind_dir: str = str(DEFAULT_MIND_DIR)) -> None:
    from rich.console import Console
    from rich.table import Table

    svgs = (
        sorted(Path(notes_dir).glob("*.svg"), key=lambda p: p.stat().st_mtime, reverse=True)
        if Path(notes_dir).exists()
        else []
    )
    minders = (
        sorted(
            Path(mind_dir).glob("*.minder"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if Path(mind_dir).exists()
        else []
    )

    if not svgs and not minders:
        print("No annotations found.")
        return

    console = Console()

    def _render(label: str, files: list) -> None:
        if not files:
            return
        t = Table(title=label, show_header=False, box=None, padding=(0, 2))
        t.add_column("mtime", style="rgb(139,148,158)")
        t.add_column("name", style="rgb(165,214,255)")
        t.add_column("size", style="rgb(139,148,158)")
        for f in files:
            st = f.stat()
            mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
            size_kb = st.st_size // 1024
            uri = f.resolve().as_uri()
            t.add_row(mtime, f"[link={uri}]{f.name}[/link]", f"{size_kb} KB")
        console.print(t)

    _render(f"Annotations  {notes_dir}", svgs)
    _render(f"Mind maps    {mind_dir}", minders)


# --- log callback ---


def cmd_log(
    date: Optional[str] = None,
    log_file: str = str(DEFAULT_LOG_FILE),
) -> None:
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    from rich.console import Console
    from rich.table import Table

    log_path = Path(log_file)
    if not log_path.exists():
        print("No activity log found.")
        return

    entries = []
    for raw in log_path.read_text().splitlines():
        try:
            e = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if e.get("ts", "").startswith(date):
            entries.append(e)

    console = Console()

    if not entries:
        console.print(f"No activity on {date}.")
        return

    t = Table(title=f"Activity  {date}", show_header=True, box=None, padding=(0, 2))
    t.add_column("time", style="rgb(139,148,158)")
    t.add_column("action", style="rgb(165,214,255)")
    t.add_column("file", style="rgb(204,204,204)")
    for e in entries:
        time_part = e["ts"].split("T")[-1] if "T" in e["ts"] else e["ts"]
        file_path = Path(e.get("file", ""))
        uri = file_path.as_uri()
        md_path = file_path.with_suffix(".md")
        if file_path.suffix == ".minder" and md_path.exists():
            cell = f"[link={uri}]{file_path.stem}[/link]  [link={md_path.as_uri()}].md[/link]"
        else:
            cell = f"[link={uri}]{file_path.stem}[/link]"
        t.add_row(time_part, e.get("action", ""), cell)
    console.print(t)


# --- cam callback ---


def cmd_cam(notes_dir: str = str(DEFAULT_NOTES_DIR)) -> None:
    for tool in ("ffplay", "ffmpeg", "convert"):
        if not shutil.which(tool):
            sys.exit(f"cam requires {tool!r} on PATH (install ffmpeg + imagemagick)")

    device = "/dev/video0"
    print("Webcam preview open — press any key or click to capture.")
    subprocess.run(
        [
            "ffplay",
            "-loglevel",
            "error",
            "-f",
            "v4l2",
            "-input_format",
            "mjpeg",
            "-video_size",
            "1920x1080",
            "-i",
            device,
            "-window_title",
            "anno cam — any key / click to capture",
            "-exitonkeydown",
            "-exitonmousedown",
        ],
        stderr=subprocess.DEVNULL,
    )

    out_dir = Path(notes_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    orig_path = out_dir / f"cam_{ts}.jpg"

    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "v4l2",
            "-input_format",
            "mjpeg",
            "-video_size",
            "1920x1080",
            "-i",
            device,
            "-frames:v",
            "1",
            "-y",
            str(orig_path),
        ],
        check=True,
    )
    _log("cam_capture", orig_path)
    print(f"saved  : {orig_path}")

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        subprocess.run(
            [
                "convert",
                str(orig_path),
                "-normalize",
                "-fuzz",
                "5%",
                "-trim",
                "+repage",
                str(tmp_path),
            ],
            check=True,
        )
        _copy_to_clipboard(tmp_path)
        print("copied : enhanced PNG to clipboard")
    finally:
        tmp_path.unlink(missing_ok=True)


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
        _log("para_open", p)
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


# --- CLI definition ---

app = cli(
    name="anno",
    help=(
        "Quick CLI for annotating figures in Inkscape, building mind maps in Minder, "
        "capturing from webcam, and annotating 3D meshes in ParaView."
    ),
    line_connect=True,
    show_types=False,
    show_defaults=True,
    theme=ColorTheme.GITHUB,
    colors=color_config.from_theme(ColorTheme.GITHUB),
)

_notes_option = option(
    flags=["--notes-dir", "-d"],
    dest="notes_dir",
    arg_type=str,
    default=str(DEFAULT_NOTES_DIR),
    help="Directory to save SVGs",
    sort_key=10,
)
_screenshots_option = option(
    flags=["--screenshots-dir", "-s"],
    dest="screenshots_dir",
    arg_type=str,
    default=str(DEFAULT_SCREENSHOTS_DIR),
    help="Directory to search for screenshots",
    sort_key=11,
)
_mind_dir_option = option(
    flags=["--mind-dir", "-m"],
    dest="mind_dir",
    arg_type=str,
    default=str(DEFAULT_MIND_DIR),
    help="Directory for mind maps",
    sort_key=10,
)
_para_notes_option = option(
    flags=["--notes-dir", "-d"],
    dest="notes_dir",
    arg_type=str,
    default=str(DEFAULT_PARA_NOTES_DIR),
    help="Directory to save ParaView exports",
    sort_key=10,
)
_log_option = option(
    flags=["--log-file", "-l"],
    dest="log_file",
    arg_type=str,
    default=str(DEFAULT_LOG_FILE),
    help="Path to the JSONL activity log",
    sort_key=12,
)

# ink group
ink_group = group(
    name="ink",
    help="Annotate figures with Inkscape. On close: saves SVG, copies result as PNG to clipboard.",
)
ink_group.commands.append(
    command(
        name="new",
        help="Open a new blank SVG in Inkscape.",
        callback=cmd_ink_new,
        arguments=[argument(name="name", arg_type=str, nargs="?", default=None, sort_key=0)],
        options=[_notes_option],
    )
)
ink_group.commands.append(
    command(
        name="open",
        help="Open an existing SVG annotation in Inkscape.",
        callback=cmd_ink_open,
        arguments=[argument(name="name", arg_type=str, sort_key=0)],
        options=[_notes_option],
    )
)
ink_group.commands.append(
    command(
        name="fig",
        help="Open a figure (PNG or JPG) in Inkscape.",
        callback=cmd_ink_fig,
        arguments=[argument(name="file", arg_type=str, nargs="?", default=None, sort_key=0)],
        options=[_notes_option],
    )
)
ink_group.commands.append(
    command(
        name="screen",
        help="Open the latest screenshot in Inkscape.",
        callback=cmd_ink_screen,
        options=[_notes_option, _screenshots_option],
    )
)
app.subgroups.append(ink_group)

# mind group
mind_group = group(
    name="mind",
    help="Mind maps with Minder. On close: exports markdown, copies to clipboard.",
)
mind_group.commands.append(
    command(
        name="new",
        help="Open a new blank mind map in Minder.",
        callback=cmd_mind_new,
        arguments=[argument(name="name", arg_type=str, nargs="?", default=None, sort_key=0)],
        options=[_mind_dir_option],
    )
)
mind_group.commands.append(
    command(
        name="open",
        help="Open an existing mind map by name.",
        callback=cmd_mind_open,
        arguments=[argument(name="name", arg_type=str, sort_key=0)],
        options=[_mind_dir_option],
    )
)
app.subgroups.append(mind_group)

# cam
app.commands.append(
    command(
        name="cam",
        help=(
            "Capture from webcam. Any key/click in preview window shoots; saves original, "
            "copies enhanced PNG to clipboard. Requires ffmpeg + imagemagick."
        ),
        callback=cmd_cam,
        options=[_notes_option],
    )
)

# para group
para_group = group(
    name="para",
    help="3D mesh annotation in ParaView. Exports selections as Markdown + screenshot to notes/para/.",
)
para_group.commands.append(
    command(
        name="new",
        help="Open one or more meshes in ParaView.",
        callback=cmd_para_new,
        arguments=[argument(name="files", nargs="+", sort_key=0)],
        options=[_para_notes_option],
    )
)
para_group.commands.append(
    command(
        name="open",
        help="Reopen last (or named) mesh from activity log.",
        callback=cmd_para_open,
        arguments=[argument(name="name", arg_type=str, nargs="?", default=None, sort_key=0)],
        options=[_para_notes_option],
    )
)
app.subgroups.append(para_group)

# list
app.commands.append(
    command(
        name="list",
        help="List saved annotations and mind maps.",
        callback=cmd_list,
        options=[_notes_option, _mind_dir_option],
    )
)

# log
app.commands.append(
    command(
        name="log",
        help="Show activity log for a given date (default: today).",
        callback=cmd_log,
        arguments=[argument(name="date", arg_type=str, nargs="?", default=None, sort_key=0)],
        options=[_log_option],
    )
)


def main() -> None:
    app.run()


if __name__ == "__main__":
    main()
