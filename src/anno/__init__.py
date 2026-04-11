import base64
import shutil
import struct
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from treeparse import argument, cli, color_config, command, group, option
from treeparse.utils.color_config import ColorTheme

DEFAULT_NOTES_DIR = Path("notes") / "draw"
DEFAULT_SCREENSHOTS_DIR = Path.home() / "Pictures" / "Screenshots"
DEFAULT_MIND_DIR = Path("notes") / "mind"
MINDER = "com.github.phase1geo.minder"

EXPORT_DPI = 300
DEFAULT_FONT_SIZE = 30


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
    )
    return out


def _run_inkscape_and_export(svg: Path) -> None:
    subprocess.run(["inkscape", str(svg)], check=True, stderr=subprocess.DEVNULL)
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
        subprocess.run(
            ["xclip", "-selection", "clipboard"], input=text, text=True, check=True
        )
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


def cmd_ink_fig(file: str, notes_dir: str = str(DEFAULT_NOTES_DIR)) -> None:
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
    + "".join(
        f'<style level="{i}" isset="false"{_STYLE_COMMON}/>' for i in range(1, 11)
    )
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


def _kill_minder() -> bool:
    result = subprocess.run(["pgrep", "-f", MINDER], capture_output=True, text=True)
    pids = result.stdout.strip().splitlines()
    if pids:
        subprocess.run(["pkill", "-f", MINDER])
        time.sleep(1)
        return True
    return False


def _run_minder(minder_file: Path, md_file: Path) -> None:
    _kill_minder()
    subprocess.run([MINDER, str(minder_file)], check=True)
    _kill_minder()
    subprocess.run(
        [MINDER, str(minder_file), "--export=markdown", str(md_file)],
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


def cmd_list(
    notes_dir: str = str(DEFAULT_NOTES_DIR), mind_dir: str = str(DEFAULT_MIND_DIR)
) -> None:
    from rich.console import Console
    from rich.table import Table

    svgs = (
        sorted(
            Path(notes_dir).glob("*.svg"), key=lambda p: p.stat().st_mtime, reverse=True
        )
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
            t.add_row(mtime, f.name, f"{size_kb} KB")
        console.print(t)

    _render(f"Annotations  {notes_dir}", svgs)
    _render(f"Mind maps    {mind_dir}", minders)


# --- CLI definition ---

app = cli(
    name="anno",
    help="Quick CLI for annotating figures in Inkscape and building mind maps in Minder.",
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
        arguments=[
            argument(name="name", arg_type=str, nargs="?", default=None, sort_key=0)
        ],
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
        arguments=[argument(name="file", arg_type=str, sort_key=0)],
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
        arguments=[
            argument(name="name", arg_type=str, nargs="?", default=None, sort_key=0)
        ],
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

# list
app.commands.append(
    command(
        name="list",
        help="List saved annotations and mind maps.",
        callback=cmd_list,
        options=[_notes_option, _mind_dir_option],
    )
)


def main() -> None:
    app.run()


if __name__ == "__main__":
    main()
