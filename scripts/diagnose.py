#!/usr/bin/env python3
"""Read-only, dependency-free foundation diagnostic; not Claude CLI validation."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

MANIFEST = Path(".claude-plugin/plugin.json")
SKILL = Path("skills/diagnose/SKILL.md")
HOOKS = Path("hooks/hooks.json")
MARKETPLACE = Path(".claude-plugin/marketplace.json")
NAME = "ssrs-report-workbench"
MAX_BYTES = 1024 * 1024


def read_local_file(root: Path, relative: Path) -> str:
    root = root.resolve()
    path = root / relative
    if path.is_symlink():
        raise ValueError("Refusing a symlink")
    if not path.is_file():
        raise FileNotFoundError("Required file is missing")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError("File resolves outside plugin root")
    if resolved.stat().st_size > MAX_BYTES:
        raise ValueError("File is unexpectedly large")
    return resolved.read_text(encoding="utf-8-sig")


def check_manifest(root: Path) -> dict[str, Any]:
    try:
        data = json.loads(read_local_file(root, MANIFEST))
        if not isinstance(data, dict):
            raise ValueError("Manifest must be a JSON object")
        if data.get("name") != NAME:
            raise ValueError("Unexpected plugin name")
        if not isinstance(data.get("version"), str) or not re.fullmatch(r"\d+\.\d+\.\d+", data["version"]):
            raise ValueError("Expected semantic version MAJOR.MINOR.PATCH")
        if not isinstance(data.get("description"), str) or not data["description"].strip():
            raise ValueError("Missing description")
        author = data.get("author")
        if not isinstance(author, dict) or not isinstance(author.get("name"), str) or not author["name"].strip():
            raise ValueError("Missing author.name")
        return {"id": "manifest", "status": "PASS", "path": str(MANIFEST)}
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {"id": "manifest", "status": "FAIL", "path": str(MANIFEST), "detail": str(exc)}


def check_diagnostic_skill(root: Path) -> dict[str, Any]:
    try:
        content = read_local_file(root, SKILL)
        if not content.startswith("---\n"):
            raise ValueError("Skill requires YAML frontmatter")
        parts = content.split("---\n", 2)
        if len(parts) != 3:
            raise ValueError("Unterminated frontmatter")
        header = parts[1]
        if not re.search(r"^name:\s*diagnose\s*$", header, flags=re.MULTILINE):
            raise ValueError("Incorrect skill name")
        if not re.search(r"^description:\s*\S", header, flags=re.MULTILINE):
            raise ValueError("Missing description")
        if not parts[2].strip():
            raise ValueError("Empty skill instructions")
        return {"id": "diagnostic-skill", "status": "PASS", "path": str(SKILL)}
    except (OSError, UnicodeError, ValueError) as exc:
        return {"id": "diagnostic-skill", "status": "FAIL", "path": str(SKILL), "detail": str(exc)}


def check_skills(root: Path) -> dict[str, Any]:
    names: list[str] = []
    bad: list[str] = []
    skills_dir = root / "skills"
    files = sorted(skills_dir.glob("*/SKILL.md")) if skills_dir.is_dir() else []
    for path in files:
        rel = path.relative_to(root)
        try:
            content = read_local_file(root, rel)
            parts = content.split("---\n", 2)
            if not content.startswith("---\n") or len(parts) != 3:
                raise ValueError("bad frontmatter")
            if not re.search(r"^name:\s*\S", parts[1], flags=re.MULTILINE):
                raise ValueError("missing name")
            if not re.search(r"^description:\s*\S", parts[1], flags=re.MULTILINE):
                raise ValueError("missing description")
            names.append(path.parent.name)
        except (OSError, UnicodeError, ValueError):
            bad.append(rel.as_posix())
    if not files:
        return {"id": "skills", "status": "FAIL", "path": "skills", "detail": "No skills/*/SKILL.md found"}
    if bad:
        return {"id": "skills", "status": "FAIL", "path": "skills", "detail": "Invalid skills: " + ", ".join(bad)}
    return {"id": "skills", "status": "PASS", "path": "skills", "detail": "Skills: " + ", ".join(names)}


def check_hooks(root: Path) -> dict[str, Any]:
    path = str(HOOKS)
    try:
        try:
            data = json.loads(read_local_file(root, HOOKS))
        except FileNotFoundError:
            raise ValueError("hooks/hooks.json missing")
        if not isinstance(data, dict) or not isinstance(data.get("hooks"), dict):
            raise ValueError("Expected top-level 'hooks' object")
        for event, groups in data["hooks"].items():
            for group in groups if isinstance(groups, list) else []:
                for handler in group.get("hooks", []) if isinstance(group, dict) else []:
                    if not isinstance(handler, dict) or handler.get("type") != "command" or "args" in handler:
                        continue
                    command = handler.get("command", "")
                    if not isinstance(command, str):
                        raise ValueError(f"{event}: command must be a string")
                    for match in re.finditer(r"\$\{CLAUDE_PLUGIN_ROOT\}", command):
                        if match.start() == 0 or command[match.start() - 1] != '"':
                            raise ValueError(f"{event}: ${{CLAUDE_PLUGIN_ROOT}} must be wrapped in double quotes")
        return {"id": "hooks", "status": "PASS", "path": path}
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {"id": "hooks", "status": "FAIL", "path": path, "detail": str(exc)}


def check_marketplace(root: Path) -> dict[str, Any]:
    path = str(MARKETPLACE)
    try:
        data = json.loads(read_local_file(root, MARKETPLACE))
        if not isinstance(data, dict):
            raise ValueError("Marketplace must be a JSON object")
        if not isinstance(data.get("name"), str) or not data["name"].strip():
            raise ValueError("Missing name")
        owner = data.get("owner")
        if not isinstance(owner, dict) or not isinstance(owner.get("name"), str) or not owner["name"].strip():
            raise ValueError("Missing owner.name")
        plugins = data.get("plugins")
        if not isinstance(plugins, list) or not plugins or not isinstance(plugins[0], dict):
            raise ValueError("Missing plugins[0]")
        manifest = json.loads(read_local_file(root, MANIFEST))
        if plugins[0].get("name") != manifest.get("name"):
            raise ValueError("plugins[0].name does not match plugin manifest name")
        if plugins[0].get("source") != "./":
            raise ValueError("plugins[0].source must be './'")
        return {"id": "marketplace", "status": "PASS", "path": path}
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {"id": "marketplace", "status": "FAIL", "path": path, "detail": str(exc)}


def diagnose(root: Path) -> dict[str, Any]:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    checks = [check_manifest(root), check_diagnostic_skill(root), check_skills(root),
              check_hooks(root), check_marketplace(root)]
    return {
        "tool": "ssrs-report-workbench-foundation-diagnostic",
        "root": str(root),
        "status": "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL",
        "scope": "Foundation and PR-03 packaging checks only; not RDL/X++/Claude runtime validation",
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = diagnose(args.root)
    except (OSError, ValueError) as exc:
        result = {"tool": "ssrs-report-workbench-foundation-diagnostic", "status": "FAIL", "checks": [], "error": str(exc)}
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"{result['status']}: {result['tool']}")
        for item in result["checks"]:
            print(f"  {item['status']} {item['id']}: {item['path']}" + (f" ({item['detail']})" if "detail" in item else ""))
        if "error" in result:
            print(result["error"])
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
