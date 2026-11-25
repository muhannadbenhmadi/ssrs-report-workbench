"""Documentation tests for the validate-rdl skill, references and rdl-reviewer agent."""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

from scripts.rdl_validate import RULES

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skills" / "validate-rdl"
SKILL = SKILL_DIR / "SKILL.md"
RULES_MD = SKILL_DIR / "references" / "rules.md"
RULES_RTL_MD = SKILL_DIR / "references" / "rules-rtl.md"
STRUCTURE_MD = SKILL_DIR / "references" / "rdl-structure.md"
AGENT = ROOT / "agents" / "rdl-reviewer.md"
NEUTRAL_PATHS = ("tests", "skills", "docs", "scripts", "README.md", "agents")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class SkillDocsTests(unittest.TestCase):
    def test_rules_md_covers_catalog(self) -> None:
        text = read(RULES_MD)
        missing = [rule_id for rule_id in RULES if rule_id not in text]
        self.assertEqual(missing, [])

    def test_skill_frontmatter(self) -> None:
        text = read(SKILL)
        self.assertTrue(text.startswith("---\n"))
        head = text.split("\n---\n", 1)[0]
        self.assertIn("name: validate-rdl", head)
        self.assertIn("description:", head)

    def test_agent_frontmatter(self) -> None:
        text = read(AGENT)
        self.assertTrue(text.startswith("---\n"))
        head = text.split("\n---\n", 1)[0]
        self.assertIn("name: rdl-reviewer", head)
        self.assertIn("description:", head)
        self.assertIn("tools:", head)

    def test_references_exist(self) -> None:
        for path in (RULES_MD, RULES_RTL_MD, STRUCTURE_MD):
            self.assertTrue(path.is_file(), path)
        body = read(SKILL)
        self.assertIn("references/rules.md", body)
        self.assertIn("references/rdl-structure.md", body)
        self.assertIn("references/rules-rtl.md", body)

    def test_length_limits(self) -> None:
        self.assertLess(len(read(SKILL).splitlines()), 120)
        for path in (RULES_MD, RULES_RTL_MD, STRUCTURE_MD):
            self.assertLess(len(read(path).splitlines()), 200, path)

    def test_project_neutral(self) -> None:
        # The tool serves any report project: no consumer's names, parameters or labels in shipped files.
        deny = ("hrapp", "hrms", "libyana", "ggins", "jobkey", "printedby", "طبع")
        try:
            listed = subprocess.run(["git", "ls-files", "-z", "--", *NEUTRAL_PATHS], cwd=ROOT,
                                    capture_output=True, text=True, check=True).stdout.split("\0")
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("not a git checkout")
        self_path = Path(__file__).resolve().relative_to(ROOT).as_posix()
        hits = []
        for name in filter(None, listed):
            if name == self_path or not (ROOT / name).is_file():
                continue
            # Arabic combining marks are dropped so a diacritised spelling still matches.
            text = re.sub("[ً-ٰٟ]", "", (ROOT / name).read_text(encoding="utf-8", errors="ignore"))
            hits += [f"{name}: {word}" for word in deny if word in text.casefold()]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
