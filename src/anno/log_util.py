import json
from datetime import datetime
from pathlib import Path

from anno.constants import DEFAULT_LOG_FILE


def log_activity(action: str, path: Path) -> None:
    DEFAULT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "action": action,
        "file": str(path.resolve()),
        "type": path.suffix.lstrip("."),
    }
    with DEFAULT_LOG_FILE.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")
