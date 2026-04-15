import tempfile
import unittest
from pathlib import Path

from lumentp.resource_store import FileResourceStore


class FileResourceStoreTests(unittest.TestCase):
    def test_submit_fetch_replace_remove_persists_data_and_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileResourceStore(temp_dir)

            created = store.submit("/doc", b"hello", "text/plain")
            self.assertTrue(created)
            self.assertEqual(store.size(), 1)

            record = store.fetch("/doc")
            self.assertIsNotNone(record)
            self.assertEqual(record.body, b"hello")
            self.assertEqual(record.content_type, "text/plain")
            self.assertTrue(record.etag.startswith('"'))
            self.assertEqual(record.version, 1)

            replaced = store.replace("/doc", b"updated", "text/plain")
            self.assertFalse(replaced)
            updated = store.fetch("/doc")
            self.assertEqual(updated.body, b"updated")
            self.assertEqual(updated.version, 2)
            self.assertNotEqual(updated.etag, record.etag)
            self.assertTrue(updated.last_modified.endswith("Z"))

            removed = store.remove("/doc")
            self.assertTrue(removed)
            self.assertIsNone(store.fetch("/doc"))

    def test_data_survives_new_store_instance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first = FileResourceStore(temp_dir)
            first.submit("/persist", b"value", "application/octet-stream")

            second = FileResourceStore(Path(temp_dir))
            record = second.fetch("/persist")
            self.assertEqual(record.body, b"value")
            self.assertEqual(record.version, 1)

    def test_remove_missing_returns_false(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileResourceStore(temp_dir)
            self.assertFalse(store.remove("/missing"))
