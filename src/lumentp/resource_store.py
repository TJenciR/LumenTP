"""Durable file-backed resource storage for the reference server."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from typing import Any

from .constants import DEFAULT_BINARY_TYPE


@dataclass(slots=True)
class ResourceRecord:
    target: str
    body: bytes
    content_type: str = DEFAULT_BINARY_TYPE
    etag: str = ""
    last_modified: str = ""
    version: int = 1
    cache_control: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def size(self) -> int:
        return len(self.body)


class FileResourceStore:
    """Small thread-safe store that persists resources under a directory."""

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def fetch(self, target: str) -> ResourceRecord | None:
        with self._lock:
            return self._fetch_unlocked(target)

    def list_records(self, prefix: str = "/", limit: int = 100, offset: int = 0) -> list[ResourceRecord]:
        with self._lock:
            records: list[ResourceRecord] = []
            for meta_path in sorted(self.root_dir.glob("*.json")):
                record = self._record_from_metadata_path(meta_path)
                if record is None:
                    continue
                if not record.target.startswith(prefix):
                    continue
                records.append(record)
            return records[offset : offset + limit]

    def count_records(self, prefix: str = "/") -> int:
        with self._lock:
            count = 0
            for meta_path in self.root_dir.glob("*.json"):
                record = self._record_from_metadata_path(meta_path)
                if record is not None and record.target.startswith(prefix):
                    count += 1
            return count

    def submit(
        self,
        target: str,
        body: bytes,
        content_type: str = DEFAULT_BINARY_TYPE,
        cache_control: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> bool:
        return self._write(target, body, content_type, cache_control=cache_control, metadata=metadata)

    def replace(
        self,
        target: str,
        body: bytes,
        content_type: str = DEFAULT_BINARY_TYPE,
        cache_control: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> bool:
        return self._write(target, body, content_type, cache_control=cache_control, metadata=metadata)

    def patch_metadata(
        self,
        target: str,
        content_type: str | None = None,
        cache_control: str | None = None,
        metadata_updates: dict[str, str | None] | None = None,
    ) -> ResourceRecord | None:
        with self._lock:
            existing = self._fetch_unlocked(target)
            if existing is None:
                return None
            next_metadata = dict(existing.metadata)
            if metadata_updates:
                for key, value in metadata_updates.items():
                    if value is None:
                        next_metadata.pop(key, None)
                    else:
                        next_metadata[key] = value
            next_content_type = content_type or existing.content_type
            next_cache_control = existing.cache_control if cache_control is None else cache_control
            version = existing.version + 1
            record = self._build_record(
                target=target,
                body=existing.body,
                content_type=next_content_type,
                version=version,
                cache_control=next_cache_control,
                metadata=next_metadata,
            )
            self._persist_record(record)
            return record

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

    def _write(
        self,
        target: str,
        body: bytes,
        content_type: str,
        cache_control: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> bool:
        with self._lock:
            existing = self._fetch_unlocked(target)
            created = existing is None
            version = 1 if existing is None else existing.version + 1
            next_cache_control = cache_control if cache_control is not None else (existing.cache_control if existing else "")
            next_metadata = dict(existing.metadata) if existing is not None else {}
            if metadata is not None:
                next_metadata = dict(metadata)
            record = self._build_record(
                target=target,
                body=body,
                content_type=content_type,
                version=version,
                cache_control=next_cache_control,
                metadata=next_metadata,
            )
            self._persist_record(record)
            return created

    def _build_record(
        self,
        target: str,
        body: bytes,
        content_type: str,
        version: int,
        cache_control: str,
        metadata: dict[str, str],
    ) -> ResourceRecord:
        last_modified = _utc_now_text()
        etag = _build_etag(target, body, content_type, version, cache_control, metadata)
        return ResourceRecord(
            target=target,
            body=body,
            content_type=content_type,
            etag=etag,
            last_modified=last_modified,
            version=version,
            cache_control=cache_control,
            metadata=dict(metadata),
        )

    def _persist_record(self, record: ResourceRecord) -> None:
        base = self._base_path(record.target)
        body_path = base.with_suffix(".data")
        meta_path = base.with_suffix(".json")
        metadata = {
            "target": record.target,
            "content_type": record.content_type,
            "version": record.version,
            "last_modified": record.last_modified,
            "etag": record.etag,
            "cache_control": record.cache_control,
            "metadata": record.metadata,
        }
        self._atomic_write_bytes(body_path, record.body)
        self._atomic_write_text(meta_path, json.dumps(metadata, sort_keys=True))

    def _fetch_unlocked(self, target: str) -> ResourceRecord | None:
        base = self._base_path(target)
        return self._record_from_paths(base.with_suffix(".data"), base.with_suffix(".json"))

    def _record_from_metadata_path(self, meta_path: Path) -> ResourceRecord | None:
        return self._record_from_paths(meta_path.with_suffix(".data"), meta_path)

    def _record_from_paths(self, body_path: Path, meta_path: Path) -> ResourceRecord | None:
        if not body_path.exists() or not meta_path.exists():
            return None
        metadata: dict[str, Any] = json.loads(meta_path.read_text(encoding="utf-8"))
        version = int(metadata.get("version", 1))
        body = body_path.read_bytes()
        content_type = str(metadata.get("content_type", DEFAULT_BINARY_TYPE))
        cache_control = str(metadata.get("cache_control", ""))
        record_metadata = metadata.get("metadata", {}) or {}
        if not isinstance(record_metadata, dict):
            record_metadata = {}
        clean_metadata = {str(key): str(value) for key, value in record_metadata.items()}
        etag = metadata.get("etag") or _build_etag(metadata["target"], body, content_type, version, cache_control, clean_metadata)
        return ResourceRecord(
            target=str(metadata["target"]),
            body=body,
            content_type=content_type,
            etag=str(etag),
            last_modified=str(metadata.get("last_modified", "")),
            version=version,
            cache_control=cache_control,
            metadata=clean_metadata,
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


def _build_etag(
    target: str,
    body: bytes,
    content_type: str,
    version: int,
    cache_control: str,
    metadata: dict[str, str],
) -> str:
    digest = hashlib.sha256()
    digest.update(target.encode("utf-8"))
    digest.update(b"\0")
    digest.update(content_type.encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(version).encode("ascii"))
    digest.update(b"\0")
    digest.update(cache_control.encode("utf-8"))
    digest.update(b"\0")
    digest.update(json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    digest.update(b"\0")
    digest.update(body)
    return '"' + digest.hexdigest()[:16] + '"'


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
