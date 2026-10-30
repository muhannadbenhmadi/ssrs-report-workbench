"""Standard-library-only foundation checks."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from scripts.diagnose import check_diagnostic_skill, check_manifest, diagnose

PROJECT = Path(__file__).resolve().parents[1]


class FoundationDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".claude-plugin").mkdir()
        (self.root / "skills/diagnose").mkdir(parents=True)
        (self.root / ".claude-plugin/plugin.json").write_text(
            json.dumps({"name": "ssrs-report-workbench", "version": "0.1.0",
                        "description": "Example", "author": {"name": "Contributors"}}), encoding="utf-8")
        (self.root / "skills/diagnose/SKILL.md").write_text(
            "---\nname: diagnose\ndescription: Read-only diagnosis\n---\n\nDo checks.\n", encoding="utf-8")

    def test_fixture_valid(self):
        self.assertEqual(diagnose(self.root)["status"], "PASS")

    def test_repo_valid(self):
        self.assertEqual(diagnose(PROJECT)["status"], "PASS")

    def test_read_only(self):
        paths = [self.root / ".claude-plugin/plugin.json", self.root / "skills/diagnose/SKILL.md"]
        before = [p.read_bytes() for p in paths]
        diagnose(self.root)
        self.assertEqual(before, [p.read_bytes() for p in paths])

    def test_manifest_missing(self):
        (self.root / ".claude-plugin/plugin.json").unlink()
        self.assertEqual(check_manifest(self.root)["status"], "FAIL")

    def test_invalid_json(self):
        (self.root / ".claude-plugin/plugin.json").write_text("{ broken", encoding="utf-8")
        self.assertEqual(diagnose(self.root)["status"], "FAIL")

    def test_invalid_version(self):
        p = self.root / ".claude-plugin/plugin.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["version"] = "broken"
        p.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(check_manifest(self.root)["status"], "FAIL")

    def test_skill_missing_description(self):
        (self.root / "skills/diagnose/SKILL.md").write_text(
            "---\nname: diagnose\n---\nDo checks.\n", encoding="utf-8")
        self.assertEqual(check_diagnostic_skill(self.root)["status"], "FAIL")

    def test_skill_missing(self):
        (self.root / "skills/diagnose/SKILL.md").unlink()
        self.assertEqual(check_diagnostic_skill(self.root)["status"], "FAIL")

    def test_cli_pass(self):
        proc = subprocess.run([sys.executable, str(PROJECT / "scripts/diagnose.py"),
                               "--root", str(self.root), "--json"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], "PASS")

    def test_cli_failure(self):
        (self.root / ".claude-plugin/plugin.json").unlink()
        proc = subprocess.run([sys.executable, str(PROJECT / "scripts/diagnose.py"),
                               "--root", str(self.root), "--json"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)["status"], "FAIL")

    def test_large_manifest(self):
        (self.root / ".claude-plugin/plugin.json").write_bytes(b"x" * (1024 * 1024 + 1))
        self.assertEqual(check_manifest(self.root)["status"], "FAIL")

    def test_missing_root(self):
        proc = subprocess.run([sys.executable, str(PROJECT / "scripts/diagnose.py"),
                               "--root", str(self.root / "missing")], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)

    def test_symlink_rejected(self):
        target = self.root / "other.json"
        target.write_text("{}", encoding="utf-8")
        p = self.root / ".claude-plugin/plugin.json"
        p.unlink()
        try:
            p.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks not available")
        self.assertEqual(check_manifest(self.root)["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
