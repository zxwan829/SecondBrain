import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from secondbrain_core.modules.review_promote import activity_read


def _record(index=1):
    return {
        "event": "promoted",
        "request_id": f"request-{index}",
        "approver_subject": "synthetic-subject",
        "approved_at": "2026-10-23T00:00:00+00:00",
        "recorded_at": f"2026-10-23T00:00:{index % 60:02d}+00:00",
        "review_path": "reviews/synthetic.md",
        "review_sha256": "a" * 64,
        "target_filename": "Synthetic note.md",
        "output_sha256": f"{index:064x}",
    }


class PromoteAuditActivityReadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "audit.jsonl"
        self.store = activity_read.PromoteAuditActivityReadStore(str(self.path))

    def tearDown(self):
        self.temp.cleanup()

    def _write(self, records):
        self.path.write_bytes(b"".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n"
            for record in records
        ))
        self.path.chmod(0o600)

    def test_reads_only_safe_projection_and_creates_nothing_for_missing_ledger(self):
        rows, complete = self.store.read()
        self.assertEqual((rows, complete), ([], True))
        self.assertFalse(self.path.exists())

        self._write([_record()])
        rows, complete = self.store.read()
        self.assertTrue(complete)
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0]), {"activity_id", "kind", "status", "occurred_at"})
        self.assertEqual(rows[0]["kind"], "promote")
        self.assertEqual(rows[0]["status"], "promoted")
        self.assertNotIn("review_path", rows[0])
        self.assertNotIn("target_filename", rows[0])
        self.assertNotIn("approver_subject", rows[0])
        self.assertNotIn("output_sha256", rows[0])

    def test_missing_configured_parent_is_incomplete_not_empty_ledger(self):
        missing_parent = self.root / "missing" / "nested"
        store = activity_read.PromoteAuditActivityReadStore(str(missing_parent / "audit.jsonl"))

        self.assertEqual(store.read(), ([], False))

    def test_malformed_duplicate_keys_and_incomplete_tail_are_partial(self):
        good = json.dumps(_record(), separators=(",", ":")).encode() + b"\n"
        self.path.write_bytes(good + b'{"event":"promoted","event":"promoted"}\n' + b'{"event":')
        self.path.chmod(0o600)
        rows, complete = self.store.read()
        self.assertFalse(complete)
        self.assertEqual(len(rows), 1)

    def test_permissions_symlink_and_nonregular_files_fail_closed(self):
        self._write([_record()])
        self.path.chmod(0o640)
        self.assertEqual(self.store.read(), ([], False))
        self.path.chmod(0o600)
        target = self.root / "target"
        target.write_bytes(self.path.read_bytes())
        target.chmod(0o600)
        self.path.unlink()
        self.path.symlink_to(target)
        self.assertEqual(self.store.read(), ([], False))

    def test_byte_budget_reads_at_most_one_mib_and_returns_partial(self):
        rows = [_record(i) for i in range(1, 7000)]
        self._write(rows)
        self.assertGreater(self.path.stat().st_size, activity_read.MAX_AUDIT_BYTES)
        real_read = os.read
        bytes_read = 0

        def counted_read(fd, size):
            nonlocal bytes_read
            payload = real_read(fd, size)
            bytes_read += len(payload)
            return payload

        with patch.object(activity_read.os, "read", side_effect=counted_read):
            projected, complete = self.store.read()
        self.assertFalse(complete)
        self.assertLessEqual(bytes_read, activity_read.MAX_AUDIT_BYTES)
        self.assertLessEqual(len(projected), activity_read.MAX_AUDIT_ROWS)

    def test_row_budget_is_enforced_independently_of_byte_budget(self):
        self._write([_record(i) for i in range(1, 7000)])
        self.assertLess(self.path.stat().st_size, activity_read.MAX_AUDIT_BYTES * 4)
        with patch.object(activity_read, "MAX_AUDIT_BYTES", activity_read.MAX_AUDIT_BYTES * 4):
            projected, complete = self.store.read()
        self.assertFalse(complete)
        self.assertEqual(len(projected), activity_read.MAX_AUDIT_ROWS)

    def test_path_replacement_during_projection_discards_snapshot(self):
        self._write([_record()])
        original = activity_read._record
        replaced = False

        def replace_after_read(value):
            nonlocal replaced
            result = original(value)
            if not replaced:
                replaced = True
                replacement = self.root / "replacement"
                replacement.write_bytes(self.path.read_bytes())
                replacement.chmod(0o600)
                os.replace(replacement, self.path)
            return result

        with patch.object(activity_read, "_record", side_effect=replace_after_read):
            self.assertEqual(self.store.read(), ([], False))

    def test_parent_directory_replacement_during_projection_discards_snapshot(self):
        state = self.root / "state"
        state.mkdir(mode=0o700)
        nested_path = state / "audit.jsonl"
        nested_path.write_bytes(json.dumps(_record(), separators=(",", ":")).encode() + b"\n")
        nested_path.chmod(0o600)
        store = activity_read.PromoteAuditActivityReadStore(str(nested_path))
        original = activity_read._record
        replaced = False

        def replace_parent_after_read(value):
            nonlocal replaced
            result = original(value)
            if not replaced:
                replaced = True
                os.rename(state, self.root / "old-state")
                state.mkdir(mode=0o700)
            return result

        with patch.object(activity_read, "_record", side_effect=replace_parent_after_read):
            self.assertEqual(store.read(), ([], False))


if __name__ == "__main__":
    unittest.main()
