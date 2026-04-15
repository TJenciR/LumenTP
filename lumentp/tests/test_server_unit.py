import json
import tempfile
import unittest

from lumentp.message import HeaderMap, Request
from lumentp.server import LumenTPServer, _media_type_matches, _prefers_problem_json


class ServerUnitTests(unittest.TestCase):
    def test_actual_port_before_start_raises(self):
        server = LumenTPServer(port=0)
        with self.assertRaises(RuntimeError):
            server.actual_port()

    def test_dispatch_submit_without_content_length_returns_411(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir)
            request = Request(method="SUBMIT", target="/doc", headers=HeaderMap(), body=b"")
            response = server._dispatch(request)
            self.assertEqual(response.status_code, 411)

    def test_auth_required_returns_401(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir, token="secret")
            request = Request(method="FETCH", target="/doc", headers=HeaderMap.from_pairs([("Accept", "application/problem+json")]))
            response = server._dispatch(request)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.headers.get("WWW-Authenticate"), "Token")
            payload = json.loads(response.body.decode("utf-8"))
            self.assertEqual(payload["status"], 401)

    def test_fetch_accept_mismatch_returns_406(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir)
            server.resource_store.submit("/doc", b"hello", "text/plain")
            request = Request(
                method="FETCH",
                target="/doc",
                headers=HeaderMap.from_pairs([("Accept", "application/json")]),
            )
            response = server._dispatch(request)
            self.assertEqual(response.status_code, 406)

    def test_fetch_returns_stored_content_type(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir)
            server.resource_store.submit("/doc", b"hello", "text/plain")
            request = Request(method="FETCH", target="/doc", headers=HeaderMap())
            response = server._dispatch(request)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("Content-Type"), "text/plain")

    def test_error_response_can_fall_back_to_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = LumenTPServer(port=0, data_dir=temp_dir)
            request = Request(
                method="FETCH",
                target="/doc",
                headers=HeaderMap.from_pairs([("Accept", "text/plain")]),
            )
            response = server._error_response(404, "not here", request)
            self.assertEqual(response.headers.get("Content-Type"), "text/plain; charset=utf-8")
            self.assertIn(b"404 NOT FOUND", response.body)

    def test_media_type_matcher_supports_wildcards(self):
        self.assertTrue(_media_type_matches("text/*", "text/plain; charset=utf-8"))
        self.assertTrue(_media_type_matches("*/*", "application/json"))
        self.assertFalse(_media_type_matches("application/json", "text/plain"))

    def test_problem_json_preference_default(self):
        self.assertTrue(_prefers_problem_json(None))
        self.assertFalse(_prefers_problem_json("text/plain"))
