"""Tests for Inkscape SVG stubs."""

import shutil
import struct
import subprocess
from pathlib import Path

from anno.ink import INKSCAPE_NS, SODIPODI_NS, _embed_image_into_svg, _make_blank_svg, _svg_document


def _tiny_png(path: Path) -> None:
    # Signature + dummy IHDR so _image_dimensions reads width/height at 16:24.
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x00IHDR" + struct.pack(">II", 1, 1))


def test_svg_document_uses_inkscape_sodipodi_uri():
    text = _svg_document(100, 50)
    assert f'xmlns:sodipodi="{SODIPODI_NS}"' in text
    assert f'xmlns:inkscape="{INKSCAPE_NS}"' in text
    assert "sodipodi-0.0.dtd" not in text
    assert 'sodipodi:namedview id="namedview1" inkscape:document-units="px"' in text
    assert 'width="100" height="50" viewBox="0 0 100 50"' in text


def test_make_blank_svg_writes_inkscape_namespace(tmp_path: Path):
    svg = tmp_path / "blank.svg"
    _make_blank_svg(svg)
    text = svg.read_text()
    assert SODIPODI_NS in text
    assert "sodipodi-0.0.dtd" not in text


def test_embed_image_into_svg_writes_inkscape_namespace(tmp_path: Path):
    png = tmp_path / "dot.png"
    _tiny_png(png)
    svg = tmp_path / "dot.svg"
    _embed_image_into_svg(png, svg)
    text = svg.read_text()
    assert SODIPODI_NS in text
    assert "sodipodi-0.0.dtd" not in text
    assert 'xmlns:xlink="http://www.w3.org/1999/xlink"' in text
    assert "xlink:href=" in text


def test_blank_svg_inkscape_does_not_warn_unknown_namedview(tmp_path: Path):
    if not shutil.which("inkscape"):
        return
    svg = tmp_path / "blank.svg"
    png = tmp_path / "blank.png"
    _make_blank_svg(svg)
    result = subprocess.run(
        [
            "inkscape",
            "--export-type=png",
            f"--export-filename={png}",
            str(svg),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "sodipodi0:namedview" not in result.stderr
    assert "unknown type" not in result.stderr
    assert png.is_file()
