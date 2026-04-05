import base64
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from treeparse import argument, cli, color_config, command, option
from treeparse.utils.color_config import ColorTheme

DEFAULT_NOTES_DIR = Path("notes") / "draw"
DEFAULT_SCREENSHOTS_DIR = Path.home() / "Pictures" / "Screenshots"
DEFAULT_MIND_DIR = Path("notes") / "mind"
MINDER = "com.github.phase1geo.minder"


EXPORT_DPI = 300
DEFAULT_FONT_SIZE = 30


def _embed_png_into_svg(png_path: Path, svg_path: Path) -> None:
    data = base64.b64encode(png_path.read_bytes()).decode()
    w, h = _png_dimensions(png_path)
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
  <image xlink:href="data:image/png;base64,{data}" x="0" y="0" width="{w}" height="{h}"/>
</svg>"""
    svg_path.write_text(svg)


def _png_dimensions(png_path: Path) -> tuple[int, int]:
    """Read width/height from PNG header (bytes 16-24)."""
    data = png_path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return 800, 600
    import struct
    w, h = struct.unpack(">II", data[16:24])
    return w, h


def _export_png(svg_path: Path) -> Path:
    tmp = Path(tempfile.mktemp(suffix=".png"))
    subprocess.run(
        ["inkscape", "--export-type=png", f"--export-dpi={EXPORT_DPI}", f"--export-filename={tmp}", str(svg_path)],
        check=True,
        capture_output=True,
    )
    return tmp


def _copy_text_to_clipboard(text: str) -> None:
    if shutil.which("xclip"):
        subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=text,
            text=True,
            check=True,
        )
    elif sys.platform == "darwin":
        subprocess.run(["pbcopy"], input=text, text=True, check=True)
    else:
        print("clipboard copy not supported on this platform", file=sys.stderr)


def _copy_to_clipboard(png_path: Path) -> None:
    if shutil.which("xclip"):
        subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "image/png", "-i", str(png_path)],
            check=True,
        )
    elif sys.platform == "darwin":
        subprocess.run(
            ["osascript", "-e",
             f'set the clipboard to (read (POSIX file "{png_path}") as \xab class PNGf\xbb)'],
            check=True,
        )
    else:
        print("clipboard copy not supported on this platform", file=sys.stderr)


# --- command callbacks ---

def cmd_open(png: str, notes_dir: str = str(DEFAULT_NOTES_DIR)) -> None:
    png_path = Path(png).resolve()
    if not png_path.exists():
        sys.exit(f"File not found: {png_path}")

    out_dir = Path(notes_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = png_path.stem
    svg = out_dir / f"{stem}_{ts}.svg"

    _embed_png_into_svg(png_path, svg)
    print(f"opening {svg}")

    subprocess.run(["inkscape", str(svg)], check=True)

    out_png = _export_png(svg)
    _copy_to_clipboard(out_png)
    out_png.unlink(missing_ok=True)

    print(f"saved  : {svg}")
    print("copied : PNG to clipboard")


def _kill_minder() -> bool:
    result = subprocess.run(["pgrep", "-f", MINDER], capture_output=True, text=True)
    pids = result.stdout.strip().splitlines()
    if pids:
        subprocess.run(["pkill", "-f", MINDER])
        time.sleep(1)
        return True
    return False


def _make_minder_file(path: Path, title: str) -> None:
    path.write_text(
        f'<minder version="1.0"><theme name="Default" style=""/>'
        f"<layouts><layout name=\"Default\"/></layouts>"
        f'<nodes><node id="0" posx="0" posy="0" side="right" fold="false" task="-1" hide_note="true" image-pos="8">'
        f"<nodename>{title}</nodename></node></nodes></minder>"
    )


def cmd_mind(note: str = "", mind_dir: str = str(DEFAULT_MIND_DIR)) -> None:
    out_dir = Path(mind_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = note.replace(" ", "_") if note else f"mm_{ts}"
    minder_file = out_dir / f"{stem}.minder"
    md_file = out_dir / f"{stem}.md"

    title = note if note else "New Map"
    _make_minder_file(minder_file, title)

    _kill_minder()
    subprocess.run([MINDER, str(minder_file)], check=True)
    _kill_minder()

    result = subprocess.run(
        [MINDER, str(minder_file), "--export=markdown"],
        capture_output=True,
        text=True,
    )
    md = result.stdout or ""
    md_file.write_text(md)
    _copy_text_to_clipboard(md)

    print(f"saved  : {minder_file}")
    print(f"saved  : {md_file}")
    print("copied : markdown to clipboard")


def cmd_screen(notes_dir: str = str(DEFAULT_NOTES_DIR), screenshots_dir: str = str(DEFAULT_SCREENSHOTS_DIR)) -> None:
    scr_dir = Path(screenshots_dir)
    pngs = sorted(scr_dir.glob("*.png"), key=lambda p: p.stat().st_mtime)
    if not pngs:
        sys.exit(f"No PNGs found in {scr_dir}")
    latest = pngs[-1]
    print(f"latest : {latest.name}")
    cmd_open(str(latest), notes_dir)


def cmd_list(notes_dir: str = str(DEFAULT_NOTES_DIR)) -> None:
    out_dir = Path(notes_dir)
    if not out_dir.exists():
        print(f"No annotations found (directory does not exist: {out_dir})")
        return

    svgs = sorted(out_dir.glob("*.svg"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not svgs:
        print(f"No SVGs in {out_dir}")
        return

    print(f"Annotations in {out_dir}:\n")
    for svg in svgs:
        mtime = datetime.fromtimestamp(svg.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        size_kb = svg.stat().st_size // 1024
        print(f"  {mtime}  {svg.name}  ({size_kb} KB)")


# --- CLI definition ---

app = cli(
    name="anno",
    help="Annotate PNGs in Inkscape, save SVGs, copy result to clipboard.",
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

open_cmd = command(
    name="open",
    help="Open a PNG in Inkscape for annotation, save SVG, copy result to clipboard.",
    callback=cmd_open,
    arguments=[
        argument(name="png", arg_type=str, sort_key=0),
    ],
    options=[_notes_option],
)
app.commands.append(open_cmd)

_screenshots_option = option(
    flags=["--screenshots-dir", "-s"],
    dest="screenshots_dir",
    arg_type=str,
    default=str(DEFAULT_SCREENSHOTS_DIR),
    help="Directory to search for screenshots",
    sort_key=11,
)

screen_cmd = command(
    name="screen",
    help="Annotate the latest screenshot PNG.",
    callback=cmd_screen,
    options=[_notes_option, _screenshots_option],
)
app.commands.append(screen_cmd)

_mind_dir_option = option(
    flags=["--mind-dir", "-m"],
    dest="mind_dir",
    arg_type=str,
    default=str(DEFAULT_MIND_DIR),
    help="Directory to save mind maps",
    sort_key=10,
)

mind_cmd = command(
    name="mind",
    help="Open a new mind map in Minder, export markdown to clipboard on exit.",
    callback=cmd_mind,
    arguments=[
        argument(name="note", arg_type=str, sort_key=0, optional=True),
    ],
    options=[_mind_dir_option],
)
app.commands.append(mind_cmd)

list_cmd = command(
    name="list",
    help="List saved annotation SVGs.",
    callback=cmd_list,
    options=[_notes_option],
)
app.commands.append(list_cmd)


def main() -> None:
    app.run()


if __name__ == "__main__":
    main()
