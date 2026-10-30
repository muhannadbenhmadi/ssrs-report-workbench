# Contributing

This is the PR-01 foundation. Keep RDL and Dynamics RDP adapters independent. Make changes in narrowly scoped feature branches; never deploy, publish reports, query production systems, or modify third-party application repositories as part of a foundation test.

## Developer checks

Requires Python 3.11+:

```sh
python -m compileall -q scripts tests
python -m unittest discover -s tests -v
python scripts/diagnose.py --root . --json
python scripts/rdl_validate.py --root tests/fixtures/rdl --json
```

When Claude CLI is installed, also run `claude plugin validate . --strict` and record its result separately. The RDL validator command exits 1 by design because the fixtures include a deliberately broken file. CI must pass on Linux and Windows. Do not claim integration verification unless it actually ran.

## PR evidence

Include scope, baseline SHA, changed paths, tests run, unrun tests, known limitations and rollback. Minimize modifications and preserve platform separation.
