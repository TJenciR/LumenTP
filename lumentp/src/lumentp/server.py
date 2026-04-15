"""Reference server implementation for LumenTP/1.1."""

from __future__ import annotations

import json
import socket
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Thread

from .constants import (
    ALLOWED_METHODS,
    AUTH_SCHEME,
    BODY_METHODS,
    DEFAULT_BINARY_TYPE,
    DEFAULT_TEXT_TYPE,
    DEFAULT_TIMEOUT_SECONDS,
    PROBLEM_JSON_TYPE,
    STATUS_REASONS,
)
from .errors import LumenTPError, ParseError
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
        resource_store: FileResourceStore | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds
        self.max_workers = max_workers
        self.token = token
        self.resource_store = resource_store or FileResourceStore(data_dir)
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
                    conn, _addr = server_socket.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                self._executor.submit(self._handle_connection, conn)

    def _handle_connection(self, conn: socket.socket) -> None:
        buffer = b""
        with conn:
            conn.settimeout(self.timeout_seconds)
            while not self._stop_event.is_set():
                try:
                    message_bytes, buffer = read_message_bytes(conn, buffer)
                except socket.timeout:
                    break
                except ParseError as exc:
                    response = self._error_response(400, str(exc))
                    conn.sendall(response.to_bytes())
                    break
                except OSError:
                    break

                if message_bytes is None:
                    break

                request: Request | None = None
                try:
                    request = parse_request(message_bytes)
                    response = self._dispatch(request)
                except ParseError as exc:
                    response = self._error_response(400, str(exc))
                except Exception:
                    response = self._error_response(500, "unexpected server failure")

                try:
                    conn.sendall(response.to_bytes())
                except OSError:
                    break

                if self._should_close(request, response):
                    break

    def _dispatch(self, request: Request) -> Response:
        if request.method not in ALLOWED_METHODS:
            return self._error_response(405, f"method {request.method} is not allowed", request)

        if request.method in BODY_METHODS and request.headers.get("Content-Length") is None:
            return self._error_response(411, "Content-Length is required for this method", request)

        if self.token is not None and request.method != "PING":
            expected = f"{AUTH_SCHEME} {self.token}"
            if request.headers.get("Authorization") != expected:
                headers = HeaderMap.from_pairs([("WWW-Authenticate", AUTH_SCHEME)])
                return self._error_response(401, "missing or invalid token", request, headers=headers)

        if request.method == "PING":
            headers = HeaderMap.from_pairs(
                [("Content-Type", DEFAULT_TEXT_TYPE), ("Connection", self._response_connection_mode(request))]
            )
            return Response(status_code=200, headers=headers, body=b"pong")

        if request.method == "FETCH":
            return self._handle_fetch(request)
        if request.method == "SUBMIT":
            return self._handle_write(request, mode="submit")
        if request.method == "REPLACE":
            return self._handle_write(request, mode="replace")
        if request.method == "REMOVE":
            removed = self.resource_store.remove(request.target)
            if not removed:
                return self._error_response(404, f"resource {request.target} was not found", request)
            headers = HeaderMap.from_pairs([("Connection", self._response_connection_mode(request))])
            return Response(status_code=204, headers=headers)

        return self._error_response(500, "request dispatch fell through", request)

    def _handle_fetch(self, request: Request) -> Response:
        record = self.resource_store.fetch(request.target)
        if record is None:
            return self._error_response(404, f"resource {request.target} was not found", request)
        accept_value = request.headers.get("Accept")
        if not _media_type_matches(accept_value, record.content_type):
            return self._error_response(
                406,
                f"resource type {record.content_type} does not satisfy Accept",
                request,
            )
        headers = HeaderMap.from_pairs(
            [
                ("Content-Type", record.content_type),
                ("Connection", self._response_connection_mode(request)),
            ]
        )
        return Response(status_code=200, headers=headers, body=record.body)

    def _handle_write(self, request: Request, mode: str) -> Response:
        content_type = request.headers.get("Content-Type", DEFAULT_BINARY_TYPE)
        if mode == "submit":
            created = self.resource_store.submit(request.target, request.body, content_type)
        else:
            created = self.resource_store.replace(request.target, request.body, content_type)
        status = 201 if created else 200
        body = json.dumps(
            {"target": request.target, "stored": True, "content_type": content_type},
            sort_keys=True,
        ).encode("utf-8")
        headers = HeaderMap.from_pairs(
            [
                ("Content-Type", PROBLEM_JSON_TYPE),
                ("Connection", self._response_connection_mode(request)),
            ]
        )
        return Response(status_code=status, headers=headers, body=body)

    def _error_response(
        self,
        status_code: int,
        detail: str,
        request: Request | None = None,
        headers: HeaderMap | None = None,
    ) -> Response:
        response_headers = headers or HeaderMap()
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
                response_headers = response_headers.with_replaced(
                    "Connection", self._response_connection_mode(request)
                )
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


def _media_type_matches(accept_header: str | None, content_type: str) -> bool:
    if not accept_header:
        return True
    available = _base_media_type(content_type)
    for item in accept_header.split(","):
        pattern = _base_media_type(item.strip())
        if not pattern:
            continue
        if pattern == "*/*":
            return True
        if pattern.endswith("/*"):
            if available.startswith(pattern[:-1]):
                return True
        elif pattern == available:
            return True
    return False


def _prefers_problem_json(accept_header: str | None) -> bool:
    return accept_header is None or _media_type_matches(accept_header, PROBLEM_JSON_TYPE)


def _base_media_type(value: str) -> str:
    return value.split(";", 1)[0].strip().lower()
