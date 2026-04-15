import tempfile
import unittest
from pathlib import Path

from lumentp.resource_store import FileResourceStore


class FileResourceStoreTests(unittest.TestCase):
    def test_submit_fetch_replace_remove_persists_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileResourceStore(temp_dir)

            created = store.submit("/doc", b"hello", "text/plain")
            self.assertTrue(created)
            self.assertEqual(store.size(), 1)

            record = store.fetch("/doc")
            self.assertIsNotNone(record)
            self.assertEqual(record.body, b"hello")
            self.assertEqual(record.content_type, "text/plain")

            replaced = store.replace("/doc", b"updated", "text/plain")
            self.assertFalse(replaced)
            self.assertEqual(store.fetch("/doc").body, b"updated")

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

    def test_remove_missing_returns_false(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileResourceStore(temp_dir)
            self.assertFalse(store.remove("/missing"))
