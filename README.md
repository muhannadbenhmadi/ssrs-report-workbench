# SSRS Report Workbench

Claude Code plugin foundation for **two future, independently developed modules**:

- **SSRS RDL:** XML definitions, datasets, SQL and report rendering.
- **Dynamics 365 Finance & Operations RDP:** X++ data providers, contracts and report metadata.

**Scope:** PR-01 foundation (version 0.1.0) only. No RDL/RDP generator, Report Server connector, deployment action or production-readiness claim.

## Requirements

- Python 3.11+ (standard library only)
- Claude Code CLI for actual plugin loading/validation (optional for Python tests)

## Validation

```powershell
python scripts/diagnose.py --root . --json
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
claude plugin validate . --strict
claude --plugin-dir .
```

In Claude Code: `/ssrs-report-workbench:diagnose`.

The Python diagnostic verifies the manifest and diagnostic skill; it does **not** verify RDL compilation, X++ builds, SSRS rendering or Claude's plugin validator.

## Safe-by-default behavior

- Diagnostic is offline/read-only and does not execute report content.
- CI uses synthetic fixtures, never connects to production, and needs no secrets.
- Separate RDL and RDP validation/release gates.
- No external application code modifications or automatic deployment.

## Roadmap

PR-02 discovery and indexing; PR-03 RDL static checks; PR-04 RDL generation; PR-05 Dynamics RDP indexing; PR-06 Dynamics generation; PR-07 evidence/evals/checkpoints. Future capabilities are not implemented yet.

## Official references

- https://code.claude.com/docs/en/plugins/create
- https://code.claude.com/docs/en/plugins-reference
- https://code.claude.com/docs/en/skills
- https://learn.microsoft.com/en-us/sql/reporting-services/plan-for-report-design-and-report-deployment-reporting-services

## License

No license has been selected. The owner should select a license before assuming open-source reuse permissions.
