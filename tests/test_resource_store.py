import tempfile
import unittest
from pathlib import Path

from lumentp.resource_store import FileResourceStore


class FileResourceStoreTests(unittest.TestCase):
    def test_submit_fetch_replace_remove_persists_data_and_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileResourceStore(temp_dir)

            created = store.submit(
                "/doc",
                b"hello",
                "text/plain",
                cache_control="max-age=10",
                metadata={"category": "note"},
            )
            self.assertTrue(created)
            self.assertEqual(store.size(), 1)

            record = store.fetch("/doc")
            self.assertIsNotNone(record)
            self.assertEqual(record.body, b"hello")
            self.assertEqual(record.content_type, "text/plain")
            self.assertEqual(record.cache_control, "max-age=10")
            self.assertEqual(record.metadata, {"category": "note"})
            self.assertTrue(record.etag.startswith('"'))
            self.assertEqual(record.version, 1)
            self.assertEqual(record.size, 5)

            replaced = store.replace("/doc", b"updated", "text/plain")
            self.assertFalse(replaced)
            updated = store.fetch("/doc")
            self.assertEqual(updated.body, b"updated")
            self.assertEqual(updated.version, 2)
            self.assertNotEqual(updated.etag, record.etag)
            self.assertEqual(updated.metadata, {"category": "note"})
            self.assertTrue(updated.last_modified.endswith("Z"))

            removed = store.remove("/doc")
            self.assertTrue(removed)
            self.assertIsNone(store.fetch("/doc"))

    def test_patch_metadata_updates_version_and_allows_removal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileResourceStore(temp_dir)
            store.submit("/doc", b"hello", "text/plain", metadata={"a": "1", "b": "2"})
            original = store.fetch("/doc")

            patched = store.patch_metadata(
                "/doc",
                content_type="text/markdown",
                cache_control="no-store",
                metadata_updates={"a": "updated", "b": None, "c": "3"},
            )

            self.assertIsNotNone(patched)
            self.assertEqual(patched.content_type, "text/markdown")
            self.assertEqual(patched.cache_control, "no-store")
            self.assertEqual(patched.metadata, {"a": "updated", "c": "3"})
            self.assertEqual(patched.version, 2)
            self.assertNotEqual(patched.etag, original.etag)

    def test_data_survives_new_store_instance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first = FileResourceStore(temp_dir)
            first.submit("/persist", b"value", "application/octet-stream", cache_control="max-age=5", metadata={"kind": "bin"})

            second = FileResourceStore(Path(temp_dir))
            record = second.fetch("/persist")
            self.assertEqual(record.body, b"value")
            self.assertEqual(record.version, 1)
            self.assertEqual(record.cache_control, "max-age=5")
            self.assertEqual(record.metadata, {"kind": "bin"})

    def test_list_records_applies_prefix_limit_and_offset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileResourceStore(temp_dir)
            store.submit("/docs/a", b"a", "text/plain")
            store.submit("/docs/b", b"b", "text/plain")
            store.submit("/images/c", b"c", "image/png")

            self.assertEqual(store.count_records("/docs"), 2)
            records = store.list_records(prefix="/docs", limit=1, offset=1)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].target, "/docs/b")

    def test_remove_missing_returns_false(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileResourceStore(temp_dir)
            self.assertFalse(store.remove("/missing"))
