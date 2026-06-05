from datetime import datetime
from pathlib import Path

from anno.constants import DEFAULT_MIND_DIR, DEFAULT_NOTES_DIR


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
