"""Durable file-backed resource storage for the reference server."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock

from .constants import DEFAULT_BINARY_TYPE


@dataclass(slots=True)
class ResourceRecord:
    target: str
    body: bytes
    content_type: str = DEFAULT_BINARY_TYPE


class FileResourceStore:
    """Small thread-safe store that persists resources under a directory."""

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def fetch(self, target: str) -> ResourceRecord | None:
        with self._lock:
            base = self._base_path(target)
            body_path = base.with_suffix(".data")
            meta_path = base.with_suffix(".json")
            if not body_path.exists() or not meta_path.exists():
                return None
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            return ResourceRecord(
                target=metadata["target"],
                body=body_path.read_bytes(),
                content_type=metadata.get("content_type", DEFAULT_BINARY_TYPE),
            )

    def submit(self, target: str, body: bytes, content_type: str = DEFAULT_BINARY_TYPE) -> bool:
        return self._write(target, body, content_type)

    def replace(self, target: str, body: bytes, content_type: str = DEFAULT_BINARY_TYPE) -> bool:
        return self._write(target, body, content_type)

    def remove(self, target: str) -> bool:
        with self._lock:
            base = self._base_path(target)
            body_path = base.with_suffix(".data")
            meta_path = base.with_suffix(".json")
            if not body_path.exists() or not meta_path.exists():
                return False
            body_path.unlink(missing_ok=True)
            meta_path.unlink(missing_ok=True)
            return True

    def size(self) -> int:
        with self._lock:
            return len(list(self.root_dir.glob("*.json")))

    def _write(self, target: str, body: bytes, content_type: str) -> bool:
        with self._lock:
            base = self._base_path(target)
            body_path = base.with_suffix(".data")
            meta_path = base.with_suffix(".json")
            created = not body_path.exists() or not meta_path.exists()
            self._atomic_write_bytes(body_path, body)
            metadata = {"target": target, "content_type": content_type}
            self._atomic_write_text(meta_path, json.dumps(metadata, sort_keys=True))
            return created

    def _base_path(self, target: str) -> Path:
        key = base64.urlsafe_b64encode(target.encode("utf-8")).decode("ascii").rstrip("=")
        return self.root_dir / key

    def _atomic_write_bytes(self, path: Path, payload: bytes) -> None:
        with NamedTemporaryFile(dir=self.root_dir, delete=False) as handle:
            handle.write(payload)
            temp_path = Path(handle.name)
        temp_path.replace(path)

    def _atomic_write_text(self, path: Path, payload: str) -> None:
        with NamedTemporaryFile(dir=self.root_dir, delete=False, mode="w", encoding="utf-8") as handle:
            handle.write(payload)
            temp_path = Path(handle.name)
        temp_path.replace(path)
