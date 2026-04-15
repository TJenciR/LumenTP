"""Client helpers for LumenTP/1.2."""

from __future__ import annotations

import socket
from contextlib import closing

from .constants import AUTH_SCHEME, DEFAULT_TIMEOUT_SECONDS, REQUEST_ID_HEADER
from .message import HeaderMap, Request, Response
from .parser import parse_response, read_message_bytes


class LumenTPConnection:
    """Persistent client connection for multiple sequential requests."""

    def __init__(self, host: str, port: int, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds
        self._socket = socket.create_connection((host, port), timeout=timeout_seconds)
        self._socket.settimeout(timeout_seconds)
        self._buffer = b""

    def close(self) -> None:
        self._socket.close()

    def request(
        self,
        method: str,
        target: str,
        body: bytes = b"",
        headers: list[tuple[str, str]] | None = None,
    ) -> Response:
        request_headers = HeaderMap.from_pairs(headers)
        if request_headers.get("Host") is None:
            request_headers.add("Host", self.host)
        request = Request(method=method, target=target, headers=request_headers, body=body)
        self._socket.sendall(request.to_bytes())
        data, self._buffer = read_message_bytes(self._socket, self._buffer)
        if data is None:
            raise RuntimeError("server closed connection before sending a response")
        return parse_response(data)


class LumenTPClient:
    """Convenience client that opens one connection per request."""

    def __init__(self, host: str, port: int, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds

    def request(
        self,
        method: str,
        target: str,
        body: bytes = b"",
        headers: list[tuple[str, str]] | None = None,
    ) -> Response:
        with closing(LumenTPConnection(self.host, self.port, self.timeout_seconds)) as conn:
            return conn.request(method, target, body=body, headers=headers)

    def ping(self, request_id: str | None = None) -> Response:
        return self.request("PING", "/", headers=_request_id_headers(request_id))

    def fetch(
        self,
        target: str,
        accept: str | None = None,
        token: str | None = None,
        if_none_match: str | None = None,
        request_id: str | None = None,
    ) -> Response:
        headers = _auth_accept_request_headers(token=token, accept=accept, request_id=request_id)
        if if_none_match:
            headers.append(("If-None-Match", if_none_match))
        return self.request("FETCH", target, headers=headers)

    def submit(
        self,
        target: str,
        body: bytes,
        content_type: str | None = None,
        token: str | None = None,
        if_none_match: str | None = None,
        if_match: str | None = None,
        request_id: str | None = None,
    ) -> Response:
        headers = _auth_and_type_headers(token=token, content_type=content_type, request_id=request_id)
        if if_none_match:
            headers.append(("If-None-Match", if_none_match))
        if if_match:
            headers.append(("If-Match", if_match))
        return self.request("SUBMIT", target, body=body, headers=headers)

    def replace(
        self,
        target: str,
        body: bytes,
        content_type: str | None = None,
        token: str | None = None,
        if_match: str | None = None,
        request_id: str | None = None,
    ) -> Response:
        headers = _auth_and_type_headers(token=token, content_type=content_type, request_id=request_id)
        if if_match:
            headers.append(("If-Match", if_match))
        return self.request("REPLACE", target, body=body, headers=headers)

    def remove(self, target: str, token: str | None = None, if_match: str | None = None, request_id: str | None = None) -> Response:
        headers = _auth_accept_request_headers(token=token, request_id=request_id)
        if if_match:
            headers.append(("If-Match", if_match))
        return self.request("REMOVE", target, headers=headers)


def _auth_and_type_headers(
    token: str | None = None,
    content_type: str | None = None,
    request_id: str | None = None,
) -> list[tuple[str, str]]:
    headers: list[tuple[str, str]] = []
    if content_type:
        headers.append(("Content-Type", content_type))
    if token:
        headers.append(("Authorization", f"{AUTH_SCHEME} {token}"))
    headers.extend(_request_id_headers(request_id))
    return headers


def _auth_accept_request_headers(
    token: str | None = None,
    accept: str | None = None,
    request_id: str | None = None,
) -> list[tuple[str, str]]:
    headers: list[tuple[str, str]] = []
    if accept:
        headers.append(("Accept", accept))
    if token:
        headers.append(("Authorization", f"{AUTH_SCHEME} {token}"))
    headers.extend(_request_id_headers(request_id))
    return headers


def _request_id_headers(request_id: str | None = None) -> list[tuple[str, str]]:
    if not request_id:
        return []
    return [(REQUEST_ID_HEADER, request_id)]
