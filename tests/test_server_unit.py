import json
import tempfile
import unittest
from pathlib import Path

from lumentp.message import HeaderMap, Request
from lumentp.server import (
    LumenTPServer,
    _extract_metadata_headers,
    _matches_etag,
    _media_type_matches,
    _parse_bool_header,
    _parse_byte_range,
    _parse_non_negative_int_header,
    _parse_patch_body,
    _parse_sort_field,
    _prefers_problem_json,
    _precondition_matches,
    _record_matches_list_filters,
)


class ServerUnitTests(unittest.TestCase):
    def test_actual_port_before_start_raises(self):
        server = LumenTPServer(port=0)
        with self.assertRaises(RuntimeError):
            server.actual_port()

    def test_dispatch_submit_without_content_length_returns_411(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir)
            request = Request(method="SUBMIT", target="/doc", headers=HeaderMap(), body=b"")
            request.headers = request.headers.without("Content-Length")
            response = server._dispatch(request)
            self.assertEqual(response.status_code, 411)

    def test_auth_required_returns_401(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir, token="secret")
            request = Request(method="FETCH", target="/doc", headers=HeaderMap.from_pairs([("Accept", "application/problem+json")]))
            response = server._dispatch(request, request_id="req-1")
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.headers.get("WWW-Authenticate"), "Token")
            self.assertEqual(response.headers.get("X-Request-Id"), "req-1")
            payload = json.loads(response.body.decode("utf-8"))
            self.assertEqual(payload["status"], 401)

    def test_role_auth_allows_read_and_blocks_write(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir, read_token="reader", write_token="writer", admin_token="admin")
            server.resource_store.submit("/doc", b"hello", "text/plain")
            request = Request(method="INSPECT", target="/doc", headers=HeaderMap.from_pairs([("Authorization", "Token reader")]))
            self.assertEqual(server._dispatch(request).status_code, 200)

            denied = Request(method="PATCH", target="/doc", body=b"{}", headers=HeaderMap.from_pairs([("Authorization", "Token reader"), ("Content-Type", "application/json")]))
            self.assertEqual(server._dispatch(denied).status_code, 401)

    def test_fetch_accept_mismatch_returns_406(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir)
            server.resource_store.submit("/doc", b"hello", "text/plain")
            request = Request(method="FETCH", target="/doc", headers=HeaderMap.from_pairs([("Accept", "application/json")]))
            response = server._dispatch(request)
            self.assertEqual(response.status_code, 406)

    def test_fetch_returns_stored_headers_and_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir, cache_max_age=120)
            server.resource_store.submit("/doc", b"hello", "text/plain", metadata={"kind": "note"}, cache_control="no-store")
            request = Request(method="FETCH", target="/doc", headers=HeaderMap.from_pairs([("X-Request-Id", "req-1")]))
            response = server._dispatch(request)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("Content-Type"), "text/plain")
            self.assertEqual(response.headers.get("Accept-Ranges"), "bytes")
            self.assertIsNotNone(response.headers.get("ETag"))
            self.assertEqual(response.headers.get("Cache-Control"), "no-store")
            self.assertEqual(response.headers.get("X-Meta-kind"), "note")
            self.assertEqual(response.headers.get("X-Request-Id"), "req-1")

    def test_inspect_returns_headers_without_body(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir)
            server.resource_store.submit("/doc", b"hello", "text/plain")
            response = server._dispatch(Request(method="INSPECT", target="/doc"))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.body, b"")
            self.assertEqual(response.headers.get("Content-Type"), "text/plain")

    def test_fetch_if_none_match_returns_304(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir)
            server.resource_store.submit("/doc", b"hello", "text/plain")
            record = server.resource_store.fetch("/doc")
            request = Request(
                method="FETCH",
                target="/doc",
                headers=HeaderMap.from_pairs([("If-None-Match", record.etag)]),
            )
            response = server._dispatch(request)
            self.assertEqual(response.status_code, 304)
            self.assertEqual(response.body, b"")

    def test_fetch_range_returns_partial_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir)
            server.resource_store.submit("/doc", b"hello world", "text/plain")
            request = Request(method="FETCH", target="/doc", headers=HeaderMap.from_pairs([("Range", "bytes=0-4")]))
            response = server._dispatch(request)
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response.body, b"hello")
            self.assertEqual(response.headers.get("Content-Range").strip(), "bytes 0-4/11")

    def test_fetch_invalid_range_returns_400(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir)
            server.resource_store.submit("/doc", b"hello world", "text/plain")
            request = Request(method="FETCH", target="/doc", headers=HeaderMap.from_pairs([("Range", "items=0-4")]))
            response = server._dispatch(request)
            self.assertEqual(response.status_code, 400)

    def test_fetch_unsatisfied_range_returns_416(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir)
            server.resource_store.submit("/doc", b"hello", "text/plain")
            request = Request(method="FETCH", target="/doc", headers=HeaderMap.from_pairs([("Range", "bytes=99-100")]))
            response = server._dispatch(request)
            self.assertEqual(response.status_code, 416)
            self.assertEqual(response.headers.get("Content-Range"), "bytes */5")

    def test_list_returns_json_page_with_filters(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir)
            server.resource_store.submit("/docs/a-report", b"a", "text/plain")
            server.resource_store.submit("/docs/b-note", b"bb", "text/plain")
            server.resource_store.submit("/docs/c-image", b"ccc", "image/png")
            request = Request(
                method="LIST",
                target="/docs",
                headers=HeaderMap.from_pairs([
                    ("Limit", "1"),
                    ("Offset", "0"),
                    ("Contains", "note"),
                    ("Filter-Content-Type", "text/*"),
                    ("Sort", "size"),
                    ("Descending", "true"),
                ]),
            )
            response = server._dispatch(request)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("Content-Type"), "application/json")
            payload = json.loads(response.body.decode("utf-8"))
            self.assertEqual(payload["total"], 1)
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["items"][0]["target"], "/docs/b-note")

    def test_list_rejects_bad_accept(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir)
            request = Request(method="LIST", target="/docs", headers=HeaderMap.from_pairs([("Accept", "text/plain")]))
            response = server._dispatch(request)
            self.assertEqual(response.status_code, 406)

    def test_list_rejects_bad_paging_headers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir)
            request = Request(method="LIST", target="/docs", headers=HeaderMap.from_pairs([("Limit", "nope")]))
            response = server._dispatch(request)
            self.assertEqual(response.status_code, 400)

    def test_replace_if_match_mismatch_returns_412(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir)
            server.resource_store.submit("/doc", b"hello", "text/plain")
            request = Request(
                method="REPLACE",
                target="/doc",
                body=b"updated",
                headers=HeaderMap.from_pairs([("If-Match", '"nope"'), ("Content-Type", "text/plain")]),
            )
            response = server._dispatch(request)
            self.assertEqual(response.status_code, 412)

    def test_submit_if_none_match_star_blocks_existing_resource(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir)
            server.resource_store.submit("/doc", b"hello", "text/plain")
            request = Request(
                method="SUBMIT",
                target="/doc",
                body=b"updated",
                headers=HeaderMap.from_pairs([("If-None-Match", "*"), ("Content-Type", "text/plain")]),
            )
            response = server._dispatch(request)
            self.assertEqual(response.status_code, 412)

    def test_patch_updates_metadata_and_content_type(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir)
            server.resource_store.submit("/doc", b"hello", "text/plain", metadata={"kind": "note"})
            record = server.resource_store.fetch("/doc")
            request = Request(
                method="PATCH",
                target="/doc",
                body=b'{"content_type": "text/markdown", "metadata": {"kind": null, "tag": "draft"}}',
                headers=HeaderMap.from_pairs([("Content-Type", "application/json"), ("If-Match", record.etag)]),
            )
            response = server._dispatch(request)
            self.assertEqual(response.status_code, 200)
            payload = json.loads(response.body.decode("utf-8"))
            self.assertEqual(payload["content_type"], "text/markdown")
            self.assertEqual(payload["metadata"], {"tag": "draft"})

    def test_error_response_can_fall_back_to_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir)
            request = Request(method="FETCH", target="/doc", headers=HeaderMap.from_pairs([("Accept", "text/plain")]))
            response = server._error_response(404, "not here", request, request_id="req-1")
            self.assertEqual(response.headers.get("Content-Type"), "text/plain; charset=utf-8")
            self.assertEqual(response.headers.get("X-Request-Id"), "req-1")
            self.assertIn(b"404 NOT FOUND", response.body)

    def test_log_event_writes_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "server.log"
            server = LumenTPServer(port=0, data_dir=temp_dir, log_file=log_path)
            request = Request(method="PING", target="/")
            response = server._dispatch(request, request_id="req-1")
            server._log_event(("127.0.0.1", 9999), "req-1", request, response, 0.0)
            content = log_path.read_text(encoding="utf-8")
            self.assertIn('"request_id": "req-1"', content)
            self.assertIn('"status": 200', content)

    def test_helper_parsers_and_matchers(self):
        class Record:
            etag = '"tag"'
            target = '/docs/tag'
            content_type = 'text/plain'

        self.assertTrue(_media_type_matches("text/*", "text/plain; charset=utf-8"))
        self.assertTrue(_media_type_matches("*/*", "application/json"))
        self.assertFalse(_media_type_matches("application/json", "text/plain"))
        self.assertTrue(_prefers_problem_json(None))
        self.assertFalse(_prefers_problem_json("text/plain"))
        self.assertTrue(_matches_etag('"tag"', '"tag"'))
        self.assertTrue(_matches_etag('*', '"tag"'))
        self.assertFalse(_matches_etag('"other"', '"tag"'))
        self.assertTrue(_precondition_matches('"tag"', Record()))
        self.assertFalse(_precondition_matches('"other"', Record()))
        self.assertFalse(_precondition_matches('"tag"', None))
        self.assertEqual(_parse_byte_range("bytes=2-", 5), (2, 4))
        self.assertEqual(_parse_byte_range("bytes=-2", 5), (3, 4))
        self.assertIsNone(_parse_byte_range("bytes=9-10", 5))
        with self.assertRaises(ValueError):
            _parse_byte_range("bytes=1-2,3-4", 10)
        self.assertEqual(_parse_non_negative_int_header(None, 3), 3)
        self.assertEqual(_parse_non_negative_int_header("8", 1), 8)
        with self.assertRaises(ValueError):
            _parse_non_negative_int_header("-1", 0)
        self.assertTrue(_parse_bool_header("true"))
        self.assertFalse(_parse_bool_header("false", default=True))
        with self.assertRaises(ValueError):
            _parse_bool_header("maybe")
        self.assertEqual(_parse_sort_field(None), "target")
        self.assertEqual(_parse_sort_field("size"), "size")
        with self.assertRaises(ValueError):
            _parse_sort_field("bad")
        self.assertEqual(_extract_metadata_headers(HeaderMap.from_pairs([("X-Meta-kind", "note"), ("Other", "x")])), {"kind": "note"})
        self.assertEqual(_parse_patch_body(b"{}"), {})
        self.assertTrue(_record_matches_list_filters(Record(), contains="tag", filter_content_type="text/*"))
