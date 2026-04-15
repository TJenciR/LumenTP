"""Small JSONL logger for the reference server."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock


class JsonLineLogger:
    """Append-only structured logger using JSON lines."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def log(self, event: dict[str, object]) -> None:
        line = json.dumps(event, sort_keys=True)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.write("\n")
