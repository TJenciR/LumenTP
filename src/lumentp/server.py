"""Reference server implementation for LumenTP/1.4."""

from __future__ import annotations

import json
import socket
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Thread
from typing import Any

from .constants import (
    ACCEPT_RANGES_VALUE,
    ALLOWED_METHODS,
    AUTH_SCHEME,
    BODY_METHODS,
    DEFAULT_BINARY_TYPE,
    DEFAULT_CACHE_MAX_AGE,
    DEFAULT_TEXT_TYPE,
    DEFAULT_TIMEOUT_SECONDS,
    JSON_TYPE,
    LIST_SORT_FIELDS,
    METADATA_HEADER_PREFIX,
    PROBLEM_JSON_TYPE,
    REQUEST_ID_HEADER,
    STATUS_REASONS,
)
from .errors import ParseError
from .logging_utils import JsonLineLogger
from .message import HeaderMap, Request, Response
from .parser import parse_request, read_message_bytes
from .resource_store import FileResourceStore, ResourceRecord


class LumenTPServer:
    """Minimal TCP server for LumenTP requests."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8091,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_workers: int = 8,
        data_dir: str | Path = ".runtime/store",
        token: str | None = None,
        read_token: str | None = None,
        write_token: str | None = None,
        admin_token: str | None = None,
        resource_store: FileResourceStore | None = None,
        cache_max_age: int = DEFAULT_CACHE_MAX_AGE,
        log_file: str | Path | None = ".runtime/logs/lumentp.log",
    ) -> None:
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds
        self.max_workers = max_workers
        self.token = token
        self.read_token = read_token
        self.write_token = write_token
        self.admin_token = admin_token
        self.cache_max_age = cache_max_age
        self.resource_store = resource_store or FileResourceStore(data_dir)
        self.logger = JsonLineLogger(log_file) if log_file else None
        self._stop_event = Event()
        self._ready_event = Event()
        self._server_socket: socket.socket | None = None
        self._thread: Thread | None = None
        self._executor: ThreadPoolExecutor | None = None

    def start(self) -> None:
        self._thread = Thread(target=self._serve_forever, daemon=True)
        self._thread.start()
        self._ready_event.wait(timeout=self.timeout_seconds)
        if not self._ready_event.is_set():
            raise RuntimeError("server did not start in time")

    def stop(self) -> None:
        self._stop_event.set()
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=self.timeout_seconds)
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=True)

    def actual_port(self) -> int:
        if self._server_socket is None:
            raise RuntimeError("server is not running")
        return int(self._server_socket.getsockname()[1])

    def _serve_forever(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((self.host, self.port))
            server_socket.listen()
            server_socket.settimeout(0.2)
            self._server_socket = server_socket
            self._ready_event.set()

            while not self._stop_event.is_set():
                try:
                    conn, addr = server_socket.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                self._executor.submit(self._handle_connection, conn, addr)

    def _handle_connection(self, conn: socket.socket, addr: tuple[str, int]) -> None:
        buffer = b""
        with conn:
            conn.settimeout(self.timeout_seconds)
            while not self._stop_event.is_set():
                request = None
                request_id = _new_request_id()
                started = time.perf_counter()
                try:
                    message_bytes, buffer = read_message_bytes(conn, buffer)
                except socket.timeout:
                    break
                except ParseError as exc:
                    response = self._error_response(400, str(exc), request_id=request_id)
                    conn.sendall(response.to_bytes())
                    self._log_event(addr, request_id, None, response, started, str(exc))
                    break
                except OSError:
                    break

                if message_bytes is None:
                    break

                try:
                    request = parse_request(message_bytes)
                    request_id = request.headers.get(REQUEST_ID_HEADER) or request_id
                    response = self._dispatch(request, request_id=request_id)
                except ParseError as exc:
                    response = self._error_response(400, str(exc), request=request, request_id=request_id)
                except Exception:
                    response = self._error_response(500, "unexpected server failure", request=request, request_id=request_id)

                try:
                    conn.sendall(response.to_bytes())
                except OSError:
                    break

                self._log_event(addr, request_id, request, response, started)
                if self._should_close(request, response):
                    break

    def _dispatch(self, request: Request, request_id: str | None = None) -> Response:
        request_id = request_id or request.headers.get(REQUEST_ID_HEADER) or _new_request_id()
        if request.method not in ALLOWED_METHODS:
            return self._error_response(405, f"method {request.method} is not allowed", request, request_id=request_id)

        if request.method in BODY_METHODS and request.headers.get("Content-Length") is None:
            return self._error_response(411, "Content-Length is required for this method", request, request_id=request_id)

        if not self._is_authorized(request):
            headers = HeaderMap.from_pairs([("WWW-Authenticate", AUTH_SCHEME)])
            return self._error_response(401, "missing or invalid token", request, headers=headers, request_id=request_id)

        if request.method == "PING":
            headers = HeaderMap.from_pairs([
                ("Content-Type", DEFAULT_TEXT_TYPE),
                ("Connection", self._response_connection_mode(request)),
                (REQUEST_ID_HEADER, request_id),
            ])
            return Response(status_code=200, headers=headers, body=b"pong")

        if request.method == "FETCH":
            return self._handle_fetch(request, request_id=request_id)
        if request.method == "INSPECT":
            return self._handle_inspect(request, request_id=request_id)
        if request.method == "LIST":
            return self._handle_list(request, request_id=request_id)
        if request.method == "SUBMIT":
            return self._handle_write(request, mode="submit", request_id=request_id)
        if request.method == "REPLACE":
            return self._handle_write(request, mode="replace", request_id=request_id)
        if request.method == "PATCH":
            return self._handle_patch(request, request_id=request_id)
        if request.method == "REMOVE":
            return self._handle_remove(request, request_id=request_id)

        return self._error_response(500, "request dispatch fell through", request, request_id=request_id)

    def _is_authorized(self, request: Request) -> bool:
        if request.method == "PING":
            return True

        auth_header = request.headers.get("Authorization")
        if self.token is not None:
            return auth_header == f"{AUTH_SCHEME} {self.token}"

        configured_tokens = [token for token in (self.read_token, self.write_token, self.admin_token) if token]
        if not configured_tokens:
            return True
        if not auth_header or not auth_header.startswith(f"{AUTH_SCHEME} "):
            return False
        provided_token = auth_header[len(AUTH_SCHEME) + 1 :]
        return provided_token in self._allowed_tokens_for_method(request.method)

    def _allowed_tokens_for_method(self, method: str) -> set[str]:
        allowed: set[str] = set()
        if method in {"FETCH", "INSPECT", "LIST"}:
            allowed.update(token for token in (self.read_token, self.write_token, self.admin_token) if token)
        elif method in {"SUBMIT", "REPLACE", "PATCH"}:
            allowed.update(token for token in (self.write_token, self.admin_token) if token)
        elif method == "REMOVE":
            if self.admin_token is not None:
                allowed.add(self.admin_token)
            else:
                allowed.update(token for token in (self.write_token, self.admin_token) if token)
        return allowed

    def _handle_fetch(self, request: Request, request_id: str) -> Response:
        record = self.resource_store.fetch(request.target)
        if record is None:
            return self._error_response(404, f"resource {request.target} was not found", request, request_id=request_id)
        accept_value = request.headers.get("Accept")
        if not _media_type_matches(accept_value, record.content_type):
            return self._error_response(406, f"resource type {record.content_type} does not satisfy Accept", request, request_id=request_id)
        if _matches_etag(request.headers.get("If-None-Match"), record.etag):
            headers = self._resource_headers(record, request, request_id)
            return Response(status_code=304, headers=headers)
        range_header = request.headers.get("Range")
        if range_header:
            try:
                byte_range = _parse_byte_range(range_header, len(record.body))
            except ValueError as exc:
                return self._error_response(400, str(exc), request, request_id=request_id)
            if byte_range is None:
                headers = self._resource_headers(record, request, request_id).with_replaced("Content-Range", f"bytes */{len(record.body)}")
                return self._error_response(416, "requested range is not satisfiable", request, headers=headers, request_id=request_id)
            start, end = byte_range
            headers = self._resource_headers(record, request, request_id)
            headers = headers.with_replaced("Content-Range", f"bytes {start}-{end}/{len(record.body)}")
            body = record.body[start : end + 1]
            return Response(status_code=206, headers=headers, body=body)
        headers = self._resource_headers(record, request, request_id)
        return Response(status_code=200, headers=headers, body=record.body)

    def _handle_inspect(self, request: Request, request_id: str) -> Response:
        record = self.resource_store.fetch(request.target)
        if record is None:
            return self._error_response(404, f"resource {request.target} was not found", request, request_id=request_id)
        accept_value = request.headers.get("Accept")
        if not _media_type_matches(accept_value, record.content_type):
            return self._error_response(406, f"resource type {record.content_type} does not satisfy Accept", request, request_id=request_id)
        headers = self._resource_headers(record, request, request_id)
        if _matches_etag(request.headers.get("If-None-Match"), record.etag):
            return Response(status_code=304, headers=headers)
        return Response(status_code=200, headers=headers)

    def _handle_list(self, request: Request, request_id: str) -> Response:
        accept_value = request.headers.get("Accept")
        if not _media_type_matches(accept_value, JSON_TYPE):
            return self._error_response(406, f"list responses require Accept compatible with {JSON_TYPE}", request, request_id=request_id)
        try:
            limit = _parse_non_negative_int_header(request.headers.get("Limit"), default=100)
            offset = _parse_non_negative_int_header(request.headers.get("Offset"), default=0)
            sort_field = _parse_sort_field(request.headers.get("Sort"))
            descending = _parse_bool_header(request.headers.get("Descending"), default=False)
        except ValueError as exc:
            return self._error_response(400, str(exc), request, request_id=request_id)

        limit = min(limit, 1000)
        contains = request.headers.get("Contains")
        filter_content_type = request.headers.get("Filter-Content-Type")
        all_records = self.resource_store.list_records(prefix=request.target, limit=100000, offset=0)
        filtered = [
            record
            for record in all_records
            if _record_matches_list_filters(record, contains=contains, filter_content_type=filter_content_type)
        ]
        filtered.sort(key=lambda record: _record_sort_key(record, sort_field), reverse=descending)
        total = len(filtered)
        records = filtered[offset : offset + limit]
        payload = {
            "prefix": request.target,
            "count": len(records),
            "total": total,
            "limit": limit,
            "offset": offset,
            "contains": contains,
            "filter_content_type": filter_content_type,
            "sort": sort_field,
            "descending": descending,
            "items": [
                {
                    "target": record.target,
                    "content_type": record.content_type,
                    "etag": record.etag,
                    "last_modified": record.last_modified,
                    "size": record.size,
                    "version": record.version,
                    "cache_control": record.cache_control or f"max-age={self.cache_max_age}",
                    "metadata": record.metadata,
                }
                for record in records
            ],
        }
        headers = HeaderMap.from_pairs([
            ("Content-Type", JSON_TYPE),
            ("Cache-Control", "no-store"),
            ("Connection", self._response_connection_mode(request)),
            (REQUEST_ID_HEADER, request_id),
            ("X-Total-Count", str(total)),
        ])
        return Response(status_code=200, headers=headers, body=json.dumps(payload, sort_keys=True).encode("utf-8"))

    def _handle_write(self, request: Request, mode: str, request_id: str) -> Response:
        existing = self.resource_store.fetch(request.target)
        if request.headers.get("If-None-Match") == "*" and existing is not None:
            return self._error_response(412, "resource already exists", request, request_id=request_id)
        if request.headers.get("If-Match") and not _precondition_matches(request.headers.get("If-Match"), existing):
            return self._error_response(412, "If-Match precondition failed", request, request_id=request_id)

        content_type = request.headers.get("Content-Type", DEFAULT_BINARY_TYPE)
        cache_control = request.headers.get("Cache-Control")
        metadata = _extract_metadata_headers(request.headers)
        if mode == "submit":
            created = self.resource_store.submit(request.target, request.body, content_type, cache_control=cache_control, metadata=metadata or None)
        else:
            created = self.resource_store.replace(request.target, request.body, content_type, cache_control=cache_control, metadata=metadata or None)
        record = self.resource_store.fetch(request.target)
        status = 201 if created else 200
        payload = _record_payload(record, self.cache_max_age) if record is not None else {"target": request.target, "stored": True}
        headers = self._resource_headers(record, request, request_id) if record else HeaderMap()
        headers = headers.with_replaced("Content-Type", JSON_TYPE)
        return Response(status_code=status, headers=headers, body=json.dumps(payload, sort_keys=True).encode("utf-8"))

    def _handle_patch(self, request: Request, request_id: str) -> Response:
        existing = self.resource_store.fetch(request.target)
        if existing is None:
            return self._error_response(404, f"resource {request.target} was not found", request, request_id=request_id)
        if request.headers.get("If-Match") and not _precondition_matches(request.headers.get("If-Match"), existing):
            return self._error_response(412, "If-Match precondition failed", request, request_id=request_id)
        try:
            patch_data = _parse_patch_body(request.body)
        except ValueError as exc:
            return self._error_response(400, str(exc), request, request_id=request_id)
        record = self.resource_store.patch_metadata(
            request.target,
            content_type=patch_data.get("content_type"),
            cache_control=patch_data.get("cache_control"),
            metadata_updates=patch_data.get("metadata"),
        )
        if record is None:
            return self._error_response(404, f"resource {request.target} was not found", request, request_id=request_id)
        payload = _record_payload(record, self.cache_max_age)
        headers = self._resource_headers(record, request, request_id).with_replaced("Content-Type", JSON_TYPE)
        return Response(status_code=200, headers=headers, body=json.dumps(payload, sort_keys=True).encode("utf-8"))

    def _handle_remove(self, request: Request, request_id: str) -> Response:
        existing = self.resource_store.fetch(request.target)
        if request.headers.get("If-Match") and not _precondition_matches(request.headers.get("If-Match"), existing):
            return self._error_response(412, "If-Match precondition failed", request, request_id=request_id)
        removed = self.resource_store.remove(request.target)
        if not removed:
            return self._error_response(404, f"resource {request.target} was not found", request, request_id=request_id)
        headers = HeaderMap.from_pairs([
            ("Connection", self._response_connection_mode(request)),
            (REQUEST_ID_HEADER, request_id),
        ])
        return Response(status_code=204, headers=headers)

    def _resource_headers(self, record: ResourceRecord, request: Request, request_id: str) -> HeaderMap:
        headers = HeaderMap.from_pairs(
            [
                ("Content-Type", record.content_type),
                ("ETag", record.etag),
                ("Last-Modified", record.last_modified),
                ("Cache-Control", record.cache_control or f"max-age={self.cache_max_age}"),
                ("Accept-Ranges", ACCEPT_RANGES_VALUE),
                ("Connection", self._response_connection_mode(request)),
                (REQUEST_ID_HEADER, request_id),
            ]
        )
        for key, value in sorted(record.metadata.items()):
            headers = headers.with_replaced(f"{METADATA_HEADER_PREFIX}{key}", value)
        return headers

    def _error_response(
        self,
        status_code: int,
        detail: str,
        request: Request | None = None,
        headers: HeaderMap | None = None,
        request_id: str | None = None,
    ) -> Response:
        response_headers = headers or HeaderMap()
        if request_id is not None:
            response_headers = response_headers.with_replaced(REQUEST_ID_HEADER, request_id)
        accept_value = request.headers.get("Accept") if request is not None else None
        if _prefers_problem_json(accept_value):
            payload = json.dumps(
                {
                    "status": status_code,
                    "reason": STATUS_REASONS[status_code],
                    "detail": detail,
                },
                sort_keys=True,
            ).encode("utf-8")
            response_headers = response_headers.with_replaced("Content-Type", PROBLEM_JSON_TYPE)
            if request is not None:
                response_headers = response_headers.with_replaced("Connection", self._response_connection_mode(request))
            return Response(status_code=status_code, headers=response_headers, body=payload)

        text_body = f"{status_code} {STATUS_REASONS[status_code]}: {detail}".encode("utf-8")
        response_headers = response_headers.with_replaced("Content-Type", DEFAULT_TEXT_TYPE)
        if request is not None:
            response_headers = response_headers.with_replaced("Connection", self._response_connection_mode(request))
        return Response(status_code=status_code, headers=response_headers, body=text_body)

    def _response_connection_mode(self, request: Request) -> str:
        return "close" if request.headers.get("Connection", "").lower() == "close" else "keep-alive"

    def _should_close(self, request: Request | None, response: Response) -> bool:
        if request is None:
            return True
        return response.headers.get("Connection", "").lower() == "close"

    def _log_event(
        self,
        addr: tuple[str, int],
        request_id: str,
        request: Request | None,
        response: Response,
        started: float,
        error: str | None = None,
    ) -> None:
        if self.logger is None:
            return
        duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
        event = {
            "client": f"{addr[0]}:{addr[1]}",
            "duration_ms": duration_ms,
            "error": error,
            "method": request.method if request is not None else None,
            "request_id": request_id,
            "response_bytes": len(response.body),
            "status": response.status_code,
            "target": request.target if request is not None else None,
        }
        self.logger.log(event)


def _record_payload(record: ResourceRecord, default_cache_max_age: int) -> dict[str, Any]:
    return {
        "target": record.target,
        "stored": True,
        "content_type": record.content_type,
        "etag": record.etag,
        "version": record.version,
        "last_modified": record.last_modified,
        "cache_control": record.cache_control or f"max-age={default_cache_max_age}",
        "metadata": record.metadata,
        "size": record.size,
    }


def _extract_metadata_headers(headers: HeaderMap) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for name, value in headers.items:
        if name.startswith(METADATA_HEADER_PREFIX) and len(name) > len(METADATA_HEADER_PREFIX):
            metadata[name[len(METADATA_HEADER_PREFIX) :]] = value
    return metadata


def _parse_patch_body(body: bytes) -> dict[str, Any]:
    if not body:
        return {}
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("PATCH body must be valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("PATCH body must be a JSON object")
    allowed_keys = {"content_type", "cache_control", "metadata"}
    unknown = set(payload) - allowed_keys
    if unknown:
        raise ValueError(f"unsupported PATCH keys: {', '.join(sorted(unknown))}")
    metadata_updates = payload.get("metadata")
    if metadata_updates is not None:
        if not isinstance(metadata_updates, dict):
            raise ValueError("metadata patch must be an object")
        clean: dict[str, str | None] = {}
        for key, value in metadata_updates.items():
            if value is not None and not isinstance(value, str):
                raise ValueError("metadata values must be strings or null")
            clean[str(key)] = value
        payload = dict(payload)
        payload["metadata"] = clean
    for field in ("content_type", "cache_control"):
        if field in payload and payload[field] is not None and not isinstance(payload[field], str):
            raise ValueError(f"{field} must be a string")
    return payload


def _record_matches_list_filters(
    record: ResourceRecord,
    contains: str | None = None,
    filter_content_type: str | None = None,
) -> bool:
    if contains and contains not in record.target:
        return False
    if filter_content_type and not _media_type_matches(filter_content_type, record.content_type):
        return False
    return True


def _record_sort_key(record: ResourceRecord, sort_field: str):
    if sort_field == "target":
        return record.target
    if sort_field == "last_modified":
        return record.last_modified
    if sort_field == "size":
        return record.size
    if sort_field == "version":
        return record.version
    if sort_field == "content_type":
        return record.content_type
    return record.target


def _parse_sort_field(header_value: str | None) -> str:
    if header_value is None:
        return "target"
    value = header_value.strip().lower()
    if value not in LIST_SORT_FIELDS:
        raise ValueError("Sort must be one of: content_type, last_modified, size, target, version")
    return value


def _parse_bool_header(header_value: str | None, default: bool = False) -> bool:
    if header_value is None:
        return default
    value = header_value.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError("boolean header must be true/false")


def _media_type_matches(accept_header: str | None, content_type: str) -> bool:
    if not accept_header:
        return True
    actual = content_type.split(";", 1)[0].strip().lower()
    for raw_item in accept_header.split(","):
        candidate = raw_item.split(";", 1)[0].strip().lower()
        if candidate in {"*", "*/*"}:
            return True
        if candidate == actual:
            return True
        if candidate.endswith("/*"):
            prefix = candidate[:-1]
            if actual.startswith(prefix):
                return True
    return False


def _prefers_problem_json(accept_header: str | None) -> bool:
    if not accept_header:
        return True
    return _media_type_matches(accept_header, PROBLEM_JSON_TYPE)


def _matches_etag(header_value: str | None, etag: str) -> bool:
    if not header_value:
        return False
    return any(token.strip() in {etag, "*"} for token in header_value.split(","))


def _precondition_matches(header_value: str | None, record: ResourceRecord | None) -> bool:
    if not header_value:
        return True
    if record is None:
        return False
    return _matches_etag(header_value, record.etag)


def _parse_non_negative_int_header(header_value: str | None, default: int) -> int:
    if header_value is None:
        return default
    try:
        value = int(header_value)
    except ValueError as exc:
        raise ValueError("header value must be an integer") from exc
    if value < 0:
        raise ValueError("header value must be non-negative")
    return value


def _parse_byte_range(header_value: str, total_length: int) -> tuple[int, int] | None:
    value = header_value.strip().lower()
    if not value.startswith("bytes="):
        raise ValueError("only bytes ranges are supported")
    spec = value[6:]
    if "," in spec:
        raise ValueError("multiple ranges are not supported")
    if "-" not in spec:
        raise ValueError("range must contain '-'")
    start_text, end_text = spec.split("-", 1)
    if start_text == "" and end_text == "":
        raise ValueError("range must include a start or end")
    if total_length == 0:
        return None
    if start_text == "":
        suffix = int(end_text)
        if suffix <= 0:
            return None
        start = max(0, total_length - suffix)
        return start, total_length - 1
    start = int(start_text)
    end = total_length - 1 if end_text == "" else int(end_text)
    if start < 0 or end < 0 or start > end or start >= total_length:
        return None
    end = min(end, total_length - 1)
    return start, end


def _new_request_id() -> str:
    return uuid.uuid4().hex
