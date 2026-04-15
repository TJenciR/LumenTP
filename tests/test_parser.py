import unittest

from lumentp.constants import VERSION
from lumentp.errors import ParseError
from lumentp.parser import parse_request, parse_response, read_message_bytes


class FakeSocket:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def recv(self, _size):
        if self._chunks:
            return self._chunks.pop(0)
        return b""


class ParserTests(unittest.TestCase):
    def test_parse_request_success(self):
        data = f"FETCH /doc {VERSION}\r\nHost: localhost\r\n\r\n".encode("utf-8")
        request = parse_request(data)
        self.assertEqual(request.method, "FETCH")
        self.assertEqual(request.target, "/doc")

    def test_parse_request_bad_target_raises(self):
        data = f"FETCH doc {VERSION}\r\n\r\n".encode("utf-8")
        with self.assertRaises(ParseError):
            parse_request(data)

    def test_parse_response_success(self):
        data = f"{VERSION} 200 OK\r\nContent-Length: 4\r\n\r\npong".encode("utf-8")
        response = parse_response(data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, b"pong")

    def test_parse_response_invalid_status_code_raises(self):
        data = f"{VERSION} nope OK\r\n\r\n".encode("utf-8")
        with self.assertRaises(ParseError):
            parse_response(data)

    def test_read_message_bytes_handles_leftover_bytes_for_keep_alive(self):
        first = f"{VERSION} 200 OK\r\nContent-Length: 4\r\n\r\npong".encode("utf-8")
        second = f"{VERSION} 204 NO CONTENT\r\nContent-Length: 0\r\n\r\n".encode("utf-8")
        fake_socket = FakeSocket([first + second])
        data, leftover = read_message_bytes(fake_socket)
        self.assertEqual(data, first)
        self.assertEqual(leftover, second)

    def test_read_message_bytes_uses_initial_buffer(self):
        message = f"{VERSION} 204 NO CONTENT\r\nContent-Length: 0\r\n\r\n".encode("utf-8")
        data, leftover = read_message_bytes(FakeSocket([]), initial=message)
        self.assertEqual(data, message)
        self.assertEqual(leftover, b"")

    def test_read_message_bytes_rejects_invalid_content_length(self):
        fake_socket = FakeSocket([f"FETCH /doc {VERSION}\r\nContent-Length: xx\r\n\r\n".encode("utf-8")])
        with self.assertRaises(ParseError):
            read_message_bytes(fake_socket)

    def test_read_message_bytes_returns_none_on_clean_close(self):
        data, leftover = read_message_bytes(FakeSocket([]))
        self.assertIsNone(data)
        self.assertEqual(leftover, b"")
