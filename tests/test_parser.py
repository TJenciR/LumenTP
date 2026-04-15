import unittest

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
        data = b"FETCH /doc LumenTP/1.2\r\nHost: localhost\r\n\r\n"
        request = parse_request(data)
        self.assertEqual(request.method, "FETCH")
        self.assertEqual(request.target, "/doc")

    def test_parse_request_bad_target_raises(self):
        data = b"FETCH doc LumenTP/1.2\r\n\r\n"
        with self.assertRaises(ParseError):
            parse_request(data)

    def test_parse_response_success(self):
        data = b"LumenTP/1.2 200 OK\r\nContent-Length: 4\r\n\r\npong"
        response = parse_response(data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, b"pong")

    def test_parse_response_invalid_status_code_raises(self):
        data = b"LumenTP/1.2 nope OK\r\n\r\n"
        with self.assertRaises(ParseError):
            parse_response(data)

    def test_read_message_bytes_handles_leftover_bytes_for_keep_alive(self):
        first = b"LumenTP/1.2 200 OK\r\nContent-Length: 4\r\n\r\npong"
        second = b"LumenTP/1.2 204 NO CONTENT\r\nContent-Length: 0\r\n\r\n"
        fake_socket = FakeSocket([first + second])
        data, leftover = read_message_bytes(fake_socket)
        self.assertEqual(data, first)
        self.assertEqual(leftover, second)

    def test_read_message_bytes_uses_initial_buffer(self):
        message = b"LumenTP/1.2 204 NO CONTENT\r\nContent-Length: 0\r\n\r\n"
        data, leftover = read_message_bytes(FakeSocket([]), initial=message)
        self.assertEqual(data, message)
        self.assertEqual(leftover, b"")

    def test_read_message_bytes_rejects_invalid_content_length(self):
        fake_socket = FakeSocket([b"FETCH /doc LumenTP/1.2\r\nContent-Length: xx\r\n\r\n"])
        with self.assertRaises(ParseError):
            read_message_bytes(fake_socket)

    def test_read_message_bytes_returns_none_on_clean_close(self):
        data, leftover = read_message_bytes(FakeSocket([]))
        self.assertIsNone(data)
        self.assertEqual(leftover, b"")
