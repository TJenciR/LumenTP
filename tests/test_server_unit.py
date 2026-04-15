import json
import tempfile
import unittest
from pathlib import Path

from lumentp.message import HeaderMap, Request
from lumentp.server import (
    LumenTPServer,
    _matches_etag,
    _media_type_matches,
    _prefers_problem_json,
    _precondition_matches,
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

    def test_fetch_accept_mismatch_returns_406(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir)
            server.resource_store.submit("/doc", b"hello", "text/plain")
            request = Request(method="FETCH", target="/doc", headers=HeaderMap.from_pairs([("Accept", "application/json")]))
            response = server._dispatch(request)
            self.assertEqual(response.status_code, 406)

    def test_fetch_returns_stored_headers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir, cache_max_age=120)
            server.resource_store.submit("/doc", b"hello", "text/plain")
            request = Request(method="FETCH", target="/doc", headers=HeaderMap.from_pairs([("X-Request-Id", "req-1")]))
            response = server._dispatch(request)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("Content-Type"), "text/plain")
            self.assertIsNotNone(response.headers.get("ETag"))
            self.assertEqual(response.headers.get("Cache-Control"), "max-age=120")
            self.assertEqual(response.headers.get("X-Request-Id"), "req-1")

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

    def test_media_type_matcher_supports_wildcards(self):
        self.assertTrue(_media_type_matches("text/*", "text/plain; charset=utf-8"))
        self.assertTrue(_media_type_matches("*/*", "application/json"))
        self.assertFalse(_media_type_matches("application/json", "text/plain"))

    def test_problem_json_preference_default(self):
        self.assertTrue(_prefers_problem_json(None))
        self.assertFalse(_prefers_problem_json("text/plain"))

    def test_etag_match_helpers(self):
        class Record:
            etag = '"tag"'

        self.assertTrue(_matches_etag('"tag"', '"tag"'))
        self.assertTrue(_matches_etag('*', '"tag"'))
        self.assertFalse(_matches_etag('"other"', '"tag"'))
        self.assertTrue(_precondition_matches('"tag"', Record()))
        self.assertFalse(_precondition_matches('"other"', Record()))
        self.assertFalse(_precondition_matches('"tag"', None))
