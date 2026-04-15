import json
import unittest
from unittest.mock import patch

from lumentp.client import (
    LumenTPClient,
    _auth_accept_request_headers,
    _auth_and_type_headers,
    _build_patch_body,
    _metadata_headers,
    _request_id_headers,
)
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

    def test_metadata_headers_and_patch_body_helpers(self):
        self.assertEqual(_metadata_headers({"kind": "note"}), [("X-Meta-kind", "note")])
        payload = json.loads(_build_patch_body(content_type="text/plain", cache_control="no-store", metadata={"a": "1"}, remove_metadata_keys=["b"]).decode("utf-8"))
        self.assertEqual(payload["content_type"], "text/plain")
        self.assertEqual(payload["cache_control"], "no-store")
        self.assertEqual(payload["metadata"], {"a": "1", "b": None})

    @patch("lumentp.client.LumenTPClient.request")
    def test_fetch_passes_accept_token_if_none_match_and_range(self, mock_request):
        mock_request.return_value = Response(status_code=200)
        client = LumenTPClient("127.0.0.1", 8091)
        client.fetch("/doc", accept="text/plain", token="abc", if_none_match='"tag"', byte_range="bytes=0-3", request_id="req-1")
        _args, kwargs = mock_request.call_args
        self.assertEqual(
            kwargs["headers"],
            [
                ("Accept", "text/plain"),
                ("Authorization", "Token abc"),
                ("X-Request-Id", "req-1"),
                ("If-None-Match", '"tag"'),
                ("Range", "bytes=0-3"),
            ],
        )

    @patch("lumentp.client.LumenTPClient.request")
    def test_inspect_passes_headers(self, mock_request):
        mock_request.return_value = Response(status_code=200)
        client = LumenTPClient("127.0.0.1", 8091)
        client.inspect("/docs/a", accept="text/*", token="reader", if_none_match='"tag"', request_id="req-3")
        _args, kwargs = mock_request.call_args
        self.assertEqual(
            kwargs["headers"],
            [
                ("Accept", "text/*"),
                ("Authorization", "Token reader"),
                ("X-Request-Id", "req-3"),
                ("If-None-Match", '"tag"'),
            ],
        )

    @patch("lumentp.client.LumenTPClient.request")
    def test_list_passes_paging_and_filter_headers(self, mock_request):
        mock_request.return_value = Response(status_code=200)
        client = LumenTPClient("127.0.0.1", 8091)
        client.list(
            "/docs",
            token="reader",
            accept="application/json",
            limit=25,
            offset=10,
            contains="report",
            filter_content_type="text/*",
            sort="version",
            descending=True,
            request_id="req-2",
        )
        _args, kwargs = mock_request.call_args
        self.assertEqual(
            kwargs["headers"],
            [
                ("Accept", "application/json"),
                ("Authorization", "Token reader"),
                ("X-Request-Id", "req-2"),
                ("Limit", "25"),
                ("Offset", "10"),
                ("Contains", "report"),
                ("Filter-Content-Type", "text/*"),
                ("Sort", "version"),
                ("Descending", "true"),
            ],
        )

    @patch("lumentp.client.LumenTPClient.request")
    def test_submit_passes_content_type_token_conditions_and_metadata(self, mock_request):
        mock_request.return_value = Response(status_code=201)
        client = LumenTPClient("127.0.0.1", 8091)
        client.submit(
            "/doc",
            b"body",
            content_type="text/plain",
            token="abc",
            if_none_match="*",
            if_match='"tag"',
            cache_control="max-age=30",
            metadata={"kind": "note"},
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
                ("Cache-Control", "max-age=30"),
                ("X-Meta-kind", "note"),
            ],
        )

    @patch("lumentp.client.LumenTPClient.request")
    def test_patch_builds_json_request(self, mock_request):
        mock_request.return_value = Response(status_code=200)
        client = LumenTPClient("127.0.0.1", 8091)
        client.patch(
            "/doc",
            content_type="text/markdown",
            cache_control="no-store",
            metadata={"a": "1"},
            remove_metadata_keys=["b"],
            token="writer",
            if_match='"tag"',
            request_id="req-9",
        )
        args, kwargs = mock_request.call_args
        self.assertEqual(args[:2], ("PATCH", "/doc"))
        self.assertEqual(
            kwargs["headers"],
            [
                ("Content-Type", "application/json"),
                ("Authorization", "Token writer"),
                ("X-Request-Id", "req-9"),
                ("If-Match", '"tag"'),
            ],
        )
        payload = json.loads(kwargs["body"].decode("utf-8"))
        self.assertEqual(payload["content_type"], "text/markdown")
        self.assertEqual(payload["metadata"], {"a": "1", "b": None})

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
