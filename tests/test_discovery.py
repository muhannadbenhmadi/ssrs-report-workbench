"""Synthetic, offline discovery and wizard regression tests."""
import json
import tempfile
import unittest
from pathlib import Path
from scripts.discovery import inventory
from scripts.requirements_wizard import questions


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "reports").mkdir()
        (self.root / "reports/attendance.rdl").write_text("<Report/>", encoding="utf-8")
        (self.root / "code").mkdir()
        (self.root / "code/provider.xpp").write_text("class Example {}", encoding="utf-8")

    def test_module_isolation(self):
        r = inventory(self.root)
        self.assertEqual(r["counts"]["rdl"], 1)
        self.assertEqual(r["counts"]["rdp"], 1)

    def test_incremental_reuse(self):
        first = inventory(self.root)
        second = inventory(self.root, first)
        self.assertEqual(second["stats"]["reused"], 2)
        self.assertEqual(first["files"], second["files"])

    def test_changed_content_invalidates(self):
        first = inventory(self.root)
        (self.root / "reports/attendance.rdl").write_text("<Changed/>", encoding="utf-8")
        next_index = inventory(self.root, first)
        self.assertEqual(next_index["stats"]["hashed"], 1)

    def test_removed_detected(self):
        first = inventory(self.root)
        (self.root / "code/provider.xpp").unlink()
        self.assertEqual(inventory(self.root, first)["removed"], ["code/provider.xpp"])

    def test_skip_hidden_generated(self):
        (self.root / ".git").mkdir()
        (self.root / ".git/secret.rdl").write_text("secret", encoding="utf-8")
        self.assertEqual(inventory(self.root)["counts"]["rdl"], 1)

    def test_xml_is_candidate(self):
        (self.root / "code/foo.xml").write_text("<x/>", encoding="utf-8")
        self.assertEqual(inventory(self.root)["counts"]["candidate"], 1)

    def test_oversize_skipped(self):
        from scripts.discovery import MAX_FILE_SIZE
        with (self.root / "reports/oversize.rdl").open("wb") as f:
            f.truncate(MAX_FILE_SIZE + 1)
        self.assertEqual(inventory(self.root)["stats"]["skipped_oversize"], 1)

    def test_count_limit(self):
        with self.assertRaises(ValueError):
            inventory(self.root, max_files=1)

    def test_questions_both(self):
        q = questions(inventory(self.root))
        self.assertEqual(q["detected_modules"], ["rdl", "rdp"])
        self.assertEqual(q["questions"][0]["suggestion"], "both")

    def test_questions_undetected(self):
        q = questions({"schema_version": 1, "counts": {}})
        self.assertIsNone(q["questions"][0]["suggestion"])

    def test_reject_old_index(self):
        with self.assertRaises(ValueError):
            questions({"schema_version": 0, "counts": {}})

    def test_no_writes(self):
        before = sorted(x.relative_to(self.root).as_posix() for x in self.root.rglob("*"))
        inventory(self.root)
        after = sorted(x.relative_to(self.root).as_posix() for x in self.root.rglob("*"))
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
