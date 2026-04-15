import unittest

from lumentp.constants import VERSION
from lumentp.errors import ValidationError
from lumentp.message import HeaderMap, Request, Response


class HeaderMapTests(unittest.TestCase):
    def test_get_is_case_insensitive_and_last_one_wins(self):
        headers = HeaderMap.from_pairs([("X-Test", "a"), ("x-test", "b")])
        self.assertEqual(headers.get("X-Test"), "b")

    def test_invalid_header_name_raises(self):
        headers = HeaderMap()
        with self.assertRaises(ValidationError):
            headers.add("Bad:Name", "x")

    def test_with_replaced_updates_existing_header(self):
        headers = HeaderMap.from_pairs([("Content-Length", "1")]).with_replaced("Content-Length", "3")
        self.assertEqual(headers.get("content-length"), "3")


class MessageTests(unittest.TestCase):
    def test_request_sets_content_length_when_body_exists(self):
        request = Request(method="SUBMIT", target="/doc", body=b"abc")
        self.assertEqual(request.headers.get("Content-Length"), "3")
        self.assertIn(b"SUBMIT /doc", request.to_bytes())

    def test_request_rejects_wrong_version(self):
        with self.assertRaises(ValidationError):
            Request(method="FETCH", target="/doc", version="bad/1.0")

    def test_response_defaults_reason_and_content_headers(self):
        response = Response(status_code=200, body=b"hello")
        self.assertEqual(response.reason, "OK")
        self.assertEqual(response.headers.get("Content-Length"), "5")
        self.assertEqual(response.headers.get("Content-Type"), "application/octet-stream")
        self.assertIn(VERSION.encode("utf-8"), response.to_bytes())

    def test_response_zero_body_gets_zero_length(self):
        response = Response(status_code=204)
        self.assertEqual(response.headers.get("Content-Length"), "0")
