#!/usr/bin/env python3
"""Offline, read-only, bounded report inventory and incremental content-hash index."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

EXTENSIONS = {
    ".rdl": "rdl", ".rds": "rdl", ".rsds": "rdl", ".rsd": "rdl", ".rptproj": "rdl",
    ".xpp": "rdp", ".xml": "candidate", ".axreport": "rdp",
}
SKIP_DIRS = {".git", ".vs", ".venv", "node_modules", "bin", "obj",
             "__pycache__", ".report-workbench", ".idea"}
MAX_FILES = 10000
MAX_FILE_SIZE = 8 * 1024 * 1024


def inventory(root: Path, prior: dict | None = None, max_files: int = MAX_FILES) -> dict:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    prior_files = (prior or {}).get("files", {})
    if not isinstance(prior_files, dict):
        prior_files = {}
    items: dict = {}
    warnings: list = []
    counters = {"hashed": 0, "reused": 0, "skipped_oversize": 0}
    candidates = []
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not (Path(base) / d).is_symlink())
        for name in sorted(names):
            p = Path(base) / name
            if p.suffix.lower() in EXTENSIONS and not p.is_symlink():
                candidates.append(p)
                if len(candidates) > max_files:
                    raise ValueError("File count limit exceeded")
    for p in candidates:
        rel = p.relative_to(root).as_posix()
        try:
            stat = p.stat()
            if stat.st_size > MAX_FILE_SIZE:
                counters["skipped_oversize"] += 1
                warnings.append({"path": rel, "reason": "oversize"})
                continue
            previous = prior_files.get(rel, {})
            # Never trust timestamps alone: always verify a content digest.
            digest = hashlib.sha256()
            with p.open("rb") as handle:
                while chunk := handle.read(65536):
                    digest.update(chunk)
            sha = digest.hexdigest()
            if previous.get("sha256") == sha:
                counters["reused"] += 1
            else:
                counters["hashed"] += 1
            suffix = p.suffix.lower()
            # XML remains an unclassified *candidate*, never misclassified as Dynamics by extension.
            kind = EXTENSIONS[suffix]
            items[rel] = {"kind": kind, "extension": suffix, "size": stat.st_size,
                          "sha256": sha}
        except (OSError, PermissionError) as exc:
            warnings.append({"path": rel, "reason": type(exc).__name__})
    counts = {"rdl": 0, "rdp": 0, "candidate": 0}
    for v in items.values():
        counts[v["kind"]] += 1
    return {"schema_version": 1, "mode": "read-only",
            "files": items, "counts": counts, "stats": counters,
            "warnings": warnings, "removed": sorted(set(prior_files) - set(items))}


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--previous", type=Path, help="Optional existing index JSON; read only")
    parser.add_argument("--max-files", type=int, default=MAX_FILES)
    args = parser.parse_args(argv)
    try:
        if args.max_files < 1 or args.max_files > MAX_FILES:
            raise ValueError("max-files outside safe range")
        previous = None
        if args.previous:
            if args.previous.stat().st_size > MAX_FILE_SIZE or args.previous.is_symlink():
                raise ValueError("Unsafe previous index")
            previous = json.loads(args.previous.read_text(encoding="utf-8"))
            if previous.get("schema_version") != 1:
                raise ValueError("Unsupported previous index version")
        result = inventory(args.root, previous, args.max_files)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "error": type(exc).__name__, "detail": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run())
