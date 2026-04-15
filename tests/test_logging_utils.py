import json
import tempfile
import unittest
from pathlib import Path

from lumentp.logging_utils import JsonLineLogger


class JsonLineLoggerTests(unittest.TestCase):
    def test_log_writes_json_line(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "logs" / "server.log"
            logger = JsonLineLogger(path)
            logger.log({"status": 200, "request_id": "abc"})
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            payload = json.loads(lines[0])
            self.assertEqual(payload["status"], 200)
            self.assertEqual(payload["request_id"], "abc")
