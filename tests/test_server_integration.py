import json
import socket
import tempfile
import unittest
from pathlib import Path

from lumentp.client import LumenTPClient, LumenTPConnection
from lumentp.server import LumenTPServer


class ServerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_path = Path(self.temp_dir.name) / "server.log"
        self.server = LumenTPServer(port=0, data_dir=self.temp_dir.name, log_file=self.log_path, cache_max_age=90)
        self.server.start()
        self.client = LumenTPClient("127.0.0.1", self.server.actual_port())

    def tearDown(self):
        self.server.stop()
        self.temp_dir.cleanup()

    def test_ping_round_trip(self):
        response = self.client.ping(request_id="ping-1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, b"pong")
        self.assertEqual(response.headers.get("X-Request-Id"), "ping-1")

    def test_submit_fetch_replace_remove_flow_with_content_type_and_etag(self):
        created = self.client.submit("/item", b"first", content_type="text/plain", request_id="req-1")
        self.assertEqual(created.status_code, 201)
        payload = json.loads(created.body.decode("utf-8"))
        etag = payload["etag"]

        fetched = self.client.fetch("/item", accept="text/plain", request_id="req-2")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.body, b"first")
        self.assertEqual(fetched.headers.get("Content-Type"), "text/plain")
        self.assertEqual(fetched.headers.get("Cache-Control"), "max-age=90")
        self.assertEqual(fetched.headers.get("ETag"), etag)

        unchanged = self.client.fetch("/item", if_none_match=etag, request_id="req-3")
        self.assertEqual(unchanged.status_code, 304)
        self.assertEqual(unchanged.body, b"")

        updated = self.client.replace("/item", b"second", content_type="text/plain", if_match=etag, request_id="req-4")
        self.assertEqual(updated.status_code, 200)

        removed = self.client.remove("/item", request_id="req-5")
        self.assertEqual(removed.status_code, 204)

        missing = self.client.fetch("/item")
        self.assertEqual(missing.status_code, 404)

    def test_unknown_method_returns_405(self):
        response = self.client.request("WHATEVER", "/x")
        self.assertEqual(response.status_code, 405)

    def test_persistent_connection_can_handle_multiple_requests(self):
        conn = LumenTPConnection("127.0.0.1", self.server.actual_port())
        try:
            first = conn.request("PING", "/")
            second = conn.request("SUBMIT", "/doc", body=b"hello", headers=[("Content-Type", "text/plain")])
            third = conn.request("FETCH", "/doc", headers=[("Accept", "text/plain")])
        finally:
            conn.close()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(third.body, b"hello")

    def test_connection_close_header_closes_exchange(self):
        with socket.create_connection(("127.0.0.1", self.server.actual_port()), timeout=5.0) as sock:
            sock.settimeout(5.0)
            request = b"PING / LumenTP/1.2\r\nConnection: close\r\n\r\n"
            sock.sendall(request)
            data = sock.recv(4096)
            self.assertIn(b"Connection: close", data)
            self.assertEqual(sock.recv(4096), b"")

    def test_token_authentication_round_trip(self):
        self.server.stop()
        self.server = LumenTPServer(port=0, data_dir=self.temp_dir.name, token="secret", log_file=self.log_path)
        self.server.start()
        self.client = LumenTPClient("127.0.0.1", self.server.actual_port())

        denied = self.client.fetch("/locked", accept="application/problem+json")
        self.assertEqual(denied.status_code, 401)
        payload = json.loads(denied.body.decode("utf-8"))
        self.assertEqual(payload["reason"], "UNAUTHORIZED")

        created = self.client.submit("/locked", b"ok", content_type="text/plain", token="secret")
        self.assertEqual(created.status_code, 201)

        fetched = self.client.fetch("/locked", accept="text/plain", token="secret")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.body, b"ok")

    def test_structured_logs_are_written(self):
        self.client.ping(request_id="trace-1")
        content = self.log_path.read_text(encoding="utf-8")
        self.assertIn('"request_id": "trace-1"', content)
        self.assertIn('"status": 200', content)
