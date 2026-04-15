"""Protocol message models and serializers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .constants import BODY_METHODS, CRLF, DEFAULT_BINARY_TYPE, STATUS_REASONS, VERSION
from .errors import ValidationError


@dataclass(slots=True)
class HeaderMap:
    """Simple ordered header store with case-insensitive lookup."""

    items: list[tuple[str, str]] = field(default_factory=list)

    def add(self, name: str, value: str) -> None:
        if not name or ":" in name or "\r" in name or "\n" in name:
            raise ValidationError("invalid header name")
        if "\r" in value or "\n" in value:
            raise ValidationError("invalid header value")
        self.items.append((name, value))

    def get(self, name: str, default: str | None = None) -> str | None:
        lowered = name.lower()
        for key, value in reversed(self.items):
            if key.lower() == lowered:
                return value
        return default

    def with_replaced(self, name: str, value: str) -> "HeaderMap":
        replaced = False
        new_items: list[tuple[str, str]] = []
        for key, existing_value in self.items:
            if key.lower() == name.lower() and not replaced:
                new_items.append((key, value))
                replaced = True
            elif key.lower() != name.lower():
                new_items.append((key, existing_value))
        if not replaced:
            new_items.append((name, value))
        return HeaderMap.from_pairs(new_items)

    def without(self, name: str) -> "HeaderMap":
        return HeaderMap.from_pairs([(k, v) for k, v in self.items if k.lower() != name.lower()])

    def to_lines(self) -> list[str]:
        return [f"{name}: {value}" for name, value in self.items]

    @classmethod
    def from_pairs(cls, pairs: Iterable[tuple[str, str]] | None) -> "HeaderMap":
        header_map = cls()
        if pairs is None:
            return header_map
        for name, value in pairs:
            header_map.add(name, value)
        return header_map


@dataclass(slots=True)
class Request:
    method: str
    target: str
    headers: HeaderMap = field(default_factory=HeaderMap)
    body: bytes = b""
    version: str = VERSION

    def __post_init__(self) -> None:
        self._validate()
        self._ensure_content_length()

    def _validate(self) -> None:
        if self.version != VERSION:
            raise ValidationError("unsupported protocol version")
        if not self.method or " " in self.method:
            raise ValidationError("invalid method")
        if not self.target.startswith("/") or " " in self.target:
            raise ValidationError("invalid target")

    def _ensure_content_length(self) -> None:
        if self.body or self.method in BODY_METHODS:
            self.headers = self.headers.with_replaced("Content-Length", str(len(self.body)))

    def to_bytes(self) -> bytes:
        start_line = f"{self.method} {self.target} {self.version}".encode("utf-8")
        header_block = CRLF.join(line.encode("utf-8") for line in self.headers.to_lines())
        if header_block:
            return start_line + CRLF + header_block + CRLF + CRLF + self.body
        return start_line + CRLF + CRLF + self.body


@dataclass(slots=True)
class Response:
    status_code: int
    headers: HeaderMap = field(default_factory=HeaderMap)
    body: bytes = b""
    version: str = VERSION
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.version != VERSION:
            raise ValidationError("unsupported protocol version")
        if self.reason is None:
            self.reason = STATUS_REASONS.get(self.status_code, "UNKNOWN")
        self._ensure_content_headers()

    def _ensure_content_headers(self) -> None:
        self.headers = self.headers.with_replaced("Content-Length", str(len(self.body)))
        if self.body and self.headers.get("Content-Type") is None:
            self.headers = self.headers.with_replaced("Content-Type", DEFAULT_BINARY_TYPE)

    def to_bytes(self) -> bytes:
        start_line = f"{self.version} {self.status_code} {self.reason}".encode("utf-8")
        header_block = CRLF.join(line.encode("utf-8") for line in self.headers.to_lines())
        if header_block:
            return start_line + CRLF + header_block + CRLF + CRLF + self.body
        return start_line + CRLF + CRLF + self.body
