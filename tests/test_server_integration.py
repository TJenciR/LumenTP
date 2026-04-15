import json
import socket
import tempfile
import time
import unittest
from pathlib import Path

from lumentp.client import LumenTPClient, LumenTPConnection
from lumentp.constants import VERSION
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

    def test_submit_fetch_inspect_patch_replace_remove_flow(self):
        created = self.client.submit(
            "/item",
            b"first",
            content_type="text/plain",
            cache_control="max-age=15",
            metadata={"kind": "note"},
            request_id="req-1",
        )
        self.assertEqual(created.status_code, 201)
        payload = json.loads(created.body.decode("utf-8"))
        etag = payload["etag"]

        fetched = self.client.fetch("/item", accept="text/plain", request_id="req-2")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.body, b"first")
        self.assertEqual(fetched.headers.get("Content-Type"), "text/plain")
        self.assertEqual(fetched.headers.get("Cache-Control"), "max-age=15")
        self.assertEqual(fetched.headers.get("X-Meta-kind"), "note")
        self.assertEqual(fetched.headers.get("ETag"), etag)

        inspected = self.client.inspect("/item", accept="text/plain", request_id="req-2b")
        self.assertEqual(inspected.status_code, 200)
        self.assertEqual(inspected.body, b"")
        self.assertEqual(inspected.headers.get("ETag"), etag)

        unchanged = self.client.fetch("/item", if_none_match=etag, request_id="req-3")
        self.assertEqual(unchanged.status_code, 304)
        self.assertEqual(unchanged.body, b"")

        patched = self.client.patch(
            "/item",
            content_type="text/markdown",
            cache_control="no-store",
            metadata={"tag": "draft"},
            remove_metadata_keys=["kind"],
            token=None,
            if_match=etag,
            request_id="req-4",
        )
        self.assertEqual(patched.status_code, 200)
        patch_payload = json.loads(patched.body.decode("utf-8"))
        self.assertEqual(patch_payload["content_type"], "text/markdown")
        self.assertEqual(patch_payload["metadata"], {"tag": "draft"})
        new_etag = patch_payload["etag"]

        updated = self.client.replace("/item", b"second", content_type="text/markdown", if_match=new_etag, request_id="req-5")
        self.assertEqual(updated.status_code, 200)

        removed = self.client.remove("/item", request_id="req-6")
        self.assertEqual(removed.status_code, 204)

        missing = self.client.fetch("/item")
        self.assertEqual(missing.status_code, 404)

    def test_fetch_range_and_list_round_trip(self):
        self.client.submit("/notes/a", b"abcdef", content_type="text/plain")
        self.client.submit("/notes/b-report", b"uvwxyz", content_type="text/plain")
        self.client.submit("/notes/c-image", b"12345", content_type="image/png")
        partial = self.client.fetch("/notes/a", accept="text/plain", byte_range="bytes=1-3", request_id="range-1")
        self.assertEqual(partial.status_code, 206)
        self.assertEqual(partial.body, b"bcd")
        self.assertEqual(partial.headers.get("Content-Range"), "bytes 1-3/6")

        listing = self.client.list("/notes", limit=1, offset=0, contains="report", filter_content_type="text/*", sort="version", descending=True, request_id="list-1")
        self.assertEqual(listing.status_code, 200)
        payload = json.loads(listing.body.decode("utf-8"))
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["target"], "/notes/b-report")

    def test_unknown_method_returns_405(self):
        response = self.client.request("WHATEVER", "/x")
        self.assertEqual(response.status_code, 405)

    def test_persistent_connection_can_handle_multiple_requests(self):
        conn = LumenTPConnection("127.0.0.1", self.server.actual_port())
        try:
            first = conn.request("PING", "/")
            second = conn.request("SUBMIT", "/doc", body=b"hello", headers=[("Content-Type", "text/plain")])
            third = conn.request("INSPECT", "/doc", headers=[("Accept", "text/plain")])
            fourth = conn.request("FETCH", "/doc", headers=[("Accept", "text/plain")])
            fifth = conn.request("LIST", "/", headers=[("Accept", "application/json")])
        finally:
            conn.close()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(third.body, b"")
        self.assertEqual(fourth.body, b"hello")
        self.assertEqual(fifth.status_code, 200)

    def test_connection_close_header_closes_exchange(self):
        with socket.create_connection(("127.0.0.1", self.server.actual_port()), timeout=5.0) as sock:
            sock.settimeout(5.0)
            request = f"PING / {VERSION}\r\nConnection: close\r\n\r\n".encode("utf-8")
            sock.sendall(request)
            data = sock.recv(4096)
            self.assertIn(b"Connection: close", data)
            self.assertEqual(sock.recv(4096), b"")

    def test_token_authentication_round_trip(self):
        self.server.stop()
        self.server = LumenTPServer(port=0, data_dir=self.temp_dir.name, read_token="reader", write_token="writer", admin_token="admin", log_file=self.log_path)
        self.server.start()
        self.client = LumenTPClient("127.0.0.1", self.server.actual_port())

        denied = self.client.fetch("/locked", accept="application/problem+json")
        self.assertEqual(denied.status_code, 401)
        payload = json.loads(denied.body.decode("utf-8"))
        self.assertEqual(payload["reason"], "UNAUTHORIZED")

        created = self.client.submit("/locked", b"ok", content_type="text/plain", token="writer")
        self.assertEqual(created.status_code, 201)

        inspected = self.client.inspect("/locked", accept="text/plain", token="reader")
        self.assertEqual(inspected.status_code, 200)
        self.assertEqual(inspected.body, b"")

        blocked = self.client.patch("/locked", metadata={"kind": "secret"}, token="reader")
        self.assertEqual(blocked.status_code, 401)

        removed = self.client.remove("/locked", token="admin")
        self.assertEqual(removed.status_code, 204)

    def test_structured_logs_are_written(self):
        self.client.ping(request_id="trace-1")
        content = ""
        for _ in range(20):
            if self.log_path.exists():
                content = self.log_path.read_text(encoding="utf-8")
                if '"request_id": "trace-1"' in content:
                    break
            time.sleep(0.02)
        self.assertIn('"request_id": "trace-1"', content)
        self.assertIn('"status": 200', content)
