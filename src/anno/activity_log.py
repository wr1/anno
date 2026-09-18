import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from anno.constants import DEFAULT_LOG_FILE


def log_activity(action: str, path: Path) -> None:
    """Append one JSONL activity record for `path`."""
    DEFAULT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "action": action,
        "file": str(path.resolve()),
        "type": path.suffix.lstrip("."),
    }
    with DEFAULT_LOG_FILE.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


def read_activity(log_file: Optional[Path] = None) -> list[dict]:
    """Parse the JSONL activity log; missing file and bad lines are skipped."""
    path = log_file or DEFAULT_LOG_FILE
    if not path.exists():
        return []
    entries: list[dict] = []
    for raw in path.read_text().splitlines():
        try:
            entries.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return entries


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

    entries = [e for e in read_activity(log_path) if e.get("ts", "").startswith(date)]

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
