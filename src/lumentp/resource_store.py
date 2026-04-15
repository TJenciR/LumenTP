"""Durable file-backed resource storage for the reference server."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock

from .constants import DEFAULT_BINARY_TYPE


@dataclass(slots=True)
class ResourceRecord:
    target: str
    body: bytes
    content_type: str = DEFAULT_BINARY_TYPE
    etag: str = ""
    last_modified: str = ""
    version: int = 1


class FileResourceStore:
    """Small thread-safe store that persists resources under a directory."""

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def fetch(self, target: str) -> ResourceRecord | None:
        with self._lock:
            return self._fetch_unlocked(target)

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
            existing = self._fetch_unlocked(target)
            created = existing is None
            version = 1 if existing is None else existing.version + 1
            metadata = {
                "target": target,
                "content_type": content_type,
                "version": version,
                "last_modified": _utc_now_text(),
            }
            metadata["etag"] = _build_etag(target, body, content_type, version)
            self._persist(target, body, metadata)
            return created

    def _persist(self, target: str, body: bytes, metadata: dict[str, object]) -> None:
        base = self._base_path(target)
        body_path = base.with_suffix(".data")
        meta_path = base.with_suffix(".json")
        self._atomic_write_bytes(body_path, body)
        self._atomic_write_text(meta_path, json.dumps(metadata, sort_keys=True))

    def _fetch_unlocked(self, target: str) -> ResourceRecord | None:
        base = self._base_path(target)
        body_path = base.with_suffix(".data")
        meta_path = base.with_suffix(".json")
        if not body_path.exists() or not meta_path.exists():
            return None
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        version = int(metadata.get("version", 1))
        body = body_path.read_bytes()
        content_type = metadata.get("content_type", DEFAULT_BINARY_TYPE)
        etag = metadata.get("etag") or _build_etag(target, body, content_type, version)
        return ResourceRecord(
            target=metadata["target"],
            body=body,
            content_type=content_type,
            etag=etag,
            last_modified=metadata.get("last_modified", ""),
            version=version,
        )

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


def _build_etag(target: str, body: bytes, content_type: str, version: int) -> str:
    digest = hashlib.sha256()
    digest.update(target.encode("utf-8"))
    digest.update(b"\0")
    digest.update(content_type.encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(version).encode("ascii"))
    digest.update(b"\0")
    digest.update(body)
    return '"' + digest.hexdigest()[:16] + '"'


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
