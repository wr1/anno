import os
from pathlib import Path

DEFAULT_NOTES_DIR = Path("notes") / "draw"
DEFAULT_SCREENSHOTS_DIR = Path.home() / "Pictures" / "Screenshots"
DEFAULT_MIND_DIR = Path("notes") / "mind"
DEFAULT_MERMAID_DIR = Path("notes") / "mermaid"
DEFAULT_LOG_FILE = Path.home() / ".anno" / "log.jsonl"
DEFAULT_PARA_NOTES_DIR = Path("notes") / "para"
DEFAULT_NOTES_ROOT = Path("notes")
DEFAULT_PLANS_DIR = Path("notes") / "plans"
DEFAULT_FS_DEPTH = 3
MINDER = "com.github.phase1geo.minder"

EXPORT_DPI = 300
DEFAULT_FONT_SIZE = 30

# Force X11 backend to avoid Inkscape SIGSEGV on Wayland (known bug in 1.2.x)
INKSCAPE_ENV = {**os.environ, "GDK_BACKEND": "x11"}

MINDER_GUI_MIN_ELAPSED = 2.0
