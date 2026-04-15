import unittest
from unittest.mock import patch

from lumentp.client import LumenTPClient, _auth_accept_request_headers, _auth_and_type_headers, _request_id_headers
from lumentp.message import Response


class ClientTests(unittest.TestCase):
    def test_helper_builds_auth_accept_and_request_id_headers(self):
        headers = _auth_accept_request_headers(token="secret", accept="text/plain", request_id="req-1")
        self.assertIn(("Accept", "text/plain"), headers)
        self.assertIn(("Authorization", "Token secret"), headers)
        self.assertIn(("X-Request-Id", "req-1"), headers)

    def test_helper_builds_auth_and_type_headers(self):
        headers = _auth_and_type_headers(token="secret", content_type="text/plain", request_id="req-1")
        self.assertIn(("Content-Type", "text/plain"), headers)
        self.assertIn(("Authorization", "Token secret"), headers)
        self.assertIn(("X-Request-Id", "req-1"), headers)

    def test_request_id_headers_empty_when_missing(self):
        self.assertEqual(_request_id_headers(None), [])

    @patch("lumentp.client.LumenTPClient.request")
    def test_fetch_passes_accept_token_and_if_none_match(self, mock_request):
        mock_request.return_value = Response(status_code=200)
        client = LumenTPClient("127.0.0.1", 8091)
        client.fetch("/doc", accept="text/plain", token="abc", if_none_match='"tag"', request_id="req-1")
        _args, kwargs = mock_request.call_args
        self.assertEqual(
            kwargs["headers"],
            [("Accept", "text/plain"), ("Authorization", "Token abc"), ("X-Request-Id", "req-1"), ("If-None-Match", '"tag"')],
        )

    @patch("lumentp.client.LumenTPClient.request")
    def test_submit_passes_content_type_token_and_conditions(self, mock_request):
        mock_request.return_value = Response(status_code=201)
        client = LumenTPClient("127.0.0.1", 8091)
        client.submit(
            "/doc",
            b"body",
            content_type="text/plain",
            token="abc",
            if_none_match="*",
            if_match='"tag"',
            request_id="req-1",
        )
        _args, kwargs = mock_request.call_args
        self.assertEqual(
            kwargs["headers"],
            [
                ("Content-Type", "text/plain"),
                ("Authorization", "Token abc"),
                ("X-Request-Id", "req-1"),
                ("If-None-Match", "*"),
                ("If-Match", '"tag"'),
            ],
        )

    @patch("lumentp.client.LumenTPClient.request")
    def test_remove_passes_token_if_match_and_request_id(self, mock_request):
        mock_request.return_value = Response(status_code=204)
        client = LumenTPClient("127.0.0.1", 8091)
        client.remove("/doc", token="abc", if_match='"tag"', request_id="req-1")
        _args, kwargs = mock_request.call_args
        self.assertEqual(
            kwargs["headers"],
            [("Authorization", "Token abc"), ("X-Request-Id", "req-1"), ("If-Match", '"tag"')],
        )
