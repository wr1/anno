from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from anno.constants import DEFAULT_MERMAID_DIR, DEFAULT_MIND_DIR, DEFAULT_NOTES_DIR

# Distinct hues so ink / mind / mermaid scan as separate types.
_TYPE_STYLE = {
    "ink": "rgb(165,214,255)",
    "mind": "rgb(210,168,255)",
    "mermaid": "rgb(126,231,135)",
}


def listed_files(directory: Path, pattern: str) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)


def open_invocation(sub: str, path: Path) -> str:
    return f"{sub} {path.stem}"


def type_style(sub: str) -> str:
    return _TYPE_STYLE[sub]


@dataclass(frozen=True)
class ListEntry:
    sub: str
    path: Path
    mtime: float

    @property
    def open_cmd(self) -> str:
        return open_invocation(self.sub, self.path)


def collect_entries(notes_dir: str, mind_dir: str, mermaid_dir: str) -> list[ListEntry]:
    entries: list[ListEntry] = []
    for sub, directory, pattern in (
        ("ink", notes_dir, "*.svg"),
        ("mind", mind_dir, "*.minder"),
        ("mermaid", mermaid_dir, "*.md"),
    ):
        for path in listed_files(Path(directory), pattern):
            entries.append(ListEntry(sub, path, path.stat().st_mtime))
    entries.sort(key=lambda e: e.mtime, reverse=True)
    return entries


def cmd_list(
    notes_dir: str = str(DEFAULT_NOTES_DIR),
    mind_dir: str = str(DEFAULT_MIND_DIR),
    mermaid_dir: str = str(DEFAULT_MERMAID_DIR),
) -> None:
    from rich.console import Console
    from rich.table import Table

    entries = collect_entries(notes_dir, mind_dir, mermaid_dir)
    if not entries:
        print("No annotations found.")
        return

    console = Console()
    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_column("mtime", style="rgb(139,148,158)")
    t.add_column("open")
    t.add_column("name")
    t.add_column("size", style="rgb(139,148,158)")
    for e in entries:
        st = e.path.stat()
        mtime = datetime.fromtimestamp(e.mtime).strftime("%Y-%m-%d %H:%M")
        size_kb = st.st_size // 1024
        uri = e.path.resolve().as_uri()
        color = type_style(e.sub)
        t.add_row(
            mtime,
            f"[{color}]{e.open_cmd}[/{color}]",
            f"[link={uri}][{color}]{e.path.name}[/{color}][/link]",
            f"{size_kb} KB",
        )
    console.print(t)
