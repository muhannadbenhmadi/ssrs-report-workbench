#!/usr/bin/env python3
"""Read-only requirement questions derived from an existing inventory JSON."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def questions(index: dict) -> dict:
    if index.get("schema_version") != 1 or not isinstance(index.get("counts"), dict):
        raise ValueError("Expected a discovery index v1")
    counts = index["counts"]
    rdl = counts.get("rdl", 0)
    rdp = counts.get("rdp", 0)
    supported = [name for name, count in (("rdl", rdl), ("rdp", rdp)) if count > 0]
    return {"schema_version": 1,
            "detected_modules": supported,
            "evidence": "file-extension inventory only; no platform verification",
            "questions": [
                {"id": "target", "text": "Which module should this project use?",
                 "options": ["rdl", "rdp", "both"], "required": True,
                 "suggestion": "both" if len(supported) == 2 else supported[0] if supported else None},
                {"id": "rdl_target", "text": "Which SSRS/PBIRS version should RDL target?",
                 "required_when": "target includes rdl", "suggestion": None},
                {"id": "d365_target", "text": "Which Dynamics 365 F&O platform version?",
                 "required_when": "target includes rdp", "suggestion": None},
                {"id": "language", "text": "Report locale and RTL preference?",
                 "suggestion": None},
                {"id": "runtime", "text": "Is an authorized Dev/Test renderer/compiler available?",
                 "suggestion": "static-only"},
            ],
            "unverified": ["access rights", "runtime versions", "schema compatibility", "database connectivity"]}


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.index.is_symlink() or args.index.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("Unsafe input index")
        index = json.loads(args.index.read_text(encoding="utf-8"))
        print(json.dumps(questions(index), indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run())
