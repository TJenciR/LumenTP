"""Message parsing helpers for LumenTP."""

from __future__ import annotations

import socket

from .constants import HEADER_TERMINATOR, MAX_HEADER_BYTES, READ_CHUNK_SIZE, VERSION
from .errors import ParseError
from .message import HeaderMap, Request, Response


def read_message_bytes(sock: socket.socket, initial: bytes = b"") -> tuple[bytes | None, bytes]:
    """Read one framed message and return leftover bytes for keep-alive use."""

    buffer = bytearray(initial)
    while HEADER_TERMINATOR not in buffer:
        chunk = sock.recv(READ_CHUNK_SIZE)
        if not chunk:
            if buffer:
                raise ParseError("connection closed before header terminator")
            return None, b""
        buffer.extend(chunk)
        if len(buffer) > MAX_HEADER_BYTES and HEADER_TERMINATOR not in buffer:
            raise ParseError("header block too large")

    header_end = bytes(buffer).index(HEADER_TERMINATOR)
    header_section = bytes(buffer[:header_end])
    remainder = bytes(buffer[header_end + len(HEADER_TERMINATOR) :])
    content_length = _content_length_from_header_section(header_section)

    while len(remainder) < content_length:
        chunk = sock.recv(READ_CHUNK_SIZE)
        if not chunk:
            raise ParseError("body shorter than Content-Length")
        remainder += chunk

    body = remainder[:content_length]
    leftover = remainder[content_length:]
    return header_section + HEADER_TERMINATOR + body, leftover


def parse_request(data: bytes) -> Request:
    start_line, headers, body = _split_message(data)
    parts = start_line.split(" ")
    if len(parts) != 3:
        raise ParseError("invalid request line")

    method, target, version = parts
    if version != VERSION:
        raise ParseError("unsupported version")
    if not target.startswith("/") or " " in target:
        raise ParseError("invalid target")

    return Request(method=method, target=target, headers=headers, body=body, version=version)


def parse_response(data: bytes) -> Response:
    start_line, headers, body = _split_message(data)
    parts = start_line.split(" ", 2)
    if len(parts) != 3:
        raise ParseError("invalid response line")

    version, status_code_text, reason = parts
    if version != VERSION:
        raise ParseError("unsupported version")

    try:
        status_code = int(status_code_text)
    except ValueError as exc:
        raise ParseError("invalid status code") from exc

    return Response(status_code=status_code, headers=headers, body=body, version=version, reason=reason)


def _split_message(data: bytes) -> tuple[str, HeaderMap, bytes]:
    if HEADER_TERMINATOR not in data:
        raise ParseError("missing header terminator")

    header_bytes, body = data.split(HEADER_TERMINATOR, 1)
    try:
        header_text = header_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParseError("headers are not valid UTF-8") from exc

    lines = header_text.split("\r\n")
    if not lines or not lines[0]:
        raise ParseError("missing start line")

    headers = _parse_headers(lines[1:])
    declared_length = headers.get("Content-Length")
    if declared_length is not None:
        try:
            length = int(declared_length)
        except ValueError as exc:
            raise ParseError("invalid Content-Length") from exc
        if length < 0:
            raise ParseError("negative Content-Length")
        if len(body) != length:
            raise ParseError("body length mismatch")

    return lines[0], headers, body


def _parse_headers(lines: list[str]) -> HeaderMap:
    headers = HeaderMap()
    for line in lines:
        if not line:
            continue
        if ":" not in line:
            raise ParseError("invalid header line")
        name, value = line.split(":", 1)
        headers.add(name.strip(), value.lstrip(" "))
    return headers


def _content_length_from_header_section(header_section: bytes) -> int:
    try:
        header_text = header_section.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParseError("headers are not valid UTF-8") from exc

    for line in header_text.split("\r\n")[1:]:
        if not line:
            continue
        if ":" not in line:
            raise ParseError("invalid header line")
        name, value = line.split(":", 1)
        if name.strip().lower() == "content-length":
            try:
                length = int(value.strip())
            except ValueError as exc:
                raise ParseError("invalid Content-Length") from exc
            if length < 0:
                raise ParseError("negative Content-Length")
            return length
    return 0
