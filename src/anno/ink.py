import base64
import struct
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from anno.clipboard import copy_png_to_clipboard
from anno.constants import (
    DEFAULT_FONT_SIZE,
    DEFAULT_NOTES_DIR,
    DEFAULT_SCREENSHOTS_DIR,
    EXPORT_DPI,
    INKSCAPE_ENV,
)
from anno.log_util import log_activity


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
        env=INKSCAPE_ENV,
    )
    return out


def _run_inkscape_and_export(svg: Path) -> None:
    svg = svg.resolve()
    result = subprocess.run(["inkscape", str(svg)], env=INKSCAPE_ENV)
    if result.returncode not in (0, -11):  # -11 = SIGSEGV (known on some builds on close)
        sys.exit(f"inkscape exited with code {result.returncode}")
    log_activity("ink_export", svg)
    out_png = _export_png(svg)
    copy_png_to_clipboard(out_png)
    print(f"saved  : {svg}")
    print(f"saved  : {out_png}")
    print("copied : PNG to clipboard")


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


def cmd_ink_open(name: str = "", notes_dir: str = str(DEFAULT_NOTES_DIR)) -> None:
    """Find-or-create: open <name>.svg if it exists, create a blank one if it
    doesn't, or open a fresh timestamped scratch SVG when no name is given."""
    out_dir = Path(notes_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if name:
        svg = out_dir / f"{Path(name).stem}.svg"
        if not svg.exists():
            _make_blank_svg(svg)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        svg = out_dir / f"fig_{ts}.svg"
        _make_blank_svg(svg)
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
