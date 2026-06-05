import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from anno.constants import DEFAULT_LOG_FILE


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
