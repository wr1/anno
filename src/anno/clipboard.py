import shutil
import subprocess
import sys
from pathlib import Path


def copy_png_to_clipboard(png_path: Path) -> None:
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


def copy_text_to_clipboard(text: str) -> None:
    if shutil.which("xclip"):
        subprocess.run(["xclip", "-selection", "clipboard"], input=text, text=True, check=True)
    elif sys.platform == "darwin":
        subprocess.run(["pbcopy"], input=text, text=True, check=True)
    else:
        print("clipboard copy not supported on this platform", file=sys.stderr)
