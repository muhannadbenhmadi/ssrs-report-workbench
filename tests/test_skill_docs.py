"""Documentation tests for the validate-rdl skill, references and rdl-reviewer agent."""

from __future__ import annotations

import unittest
from pathlib import Path

from scripts.rdl_validate import RULES

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skills" / "validate-rdl"
SKILL = SKILL_DIR / "SKILL.md"
RULES_MD = SKILL_DIR / "references" / "rules.md"
STRUCTURE_MD = SKILL_DIR / "references" / "rdl-structure.md"
AGENT = ROOT / "agents" / "rdl-reviewer.md"


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
        for path in (RULES_MD, STRUCTURE_MD):
            self.assertTrue(path.is_file(), path)
        body = read(SKILL)
        self.assertIn("references/rules.md", body)
        self.assertIn("references/rdl-structure.md", body)

    def test_length_limits(self) -> None:
        self.assertLess(len(read(SKILL).splitlines()), 120)
        for path in (RULES_MD, STRUCTURE_MD):
            self.assertLess(len(read(path).splitlines()), 200, path)


if __name__ == "__main__":
    unittest.main()
