# SSRS Report Workbench

Claude Code plugin with independent **SSRS RDL** and **Dynamics 365 Finance & Operations RDP** workflows.

## Implemented

PR-01: Manifest, diagnostic skill, offline tests and CI.

PR-02 (proposed): read-only source discovery, SHA-256 inventory/index, CLI-driven requirements question generator. Neither module includes a report generator, parser/semantic validator, runtime connector or deployment function yet.

## Requirements

Python 3.11+ (standard library only). Claude Code CLI is needed for plugin runtime and CLI validation.

## Discovery (read-only)

```powershell
python scripts/discovery.py --root "C:\\Path\\To\\Project" > inventory.json
python scripts/requirements_wizard.py --index inventory.json
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
claude plugin validate . --strict
```

Do not use PowerShell redirection to write indexes into sensitive source trees without authorization. Generated indexes contain file paths and hashes; store them in a trusted local directory. To diff against an earlier inventory, add `--previous inventory.json`. Do not overwrite an index while simultaneously reading it.

In Claude Code: `/ssrs-report-workbench:diagnose` or `/ssrs-report-workbench:discover`.

The discovery command classifies **extensions only**. It does not prove SSRS compatibility, Dynamics RDP semantics, report security, or deployment readiness. Generic XML is explicitly a candidate. Warnings indicate incomplete coverage.

## Safety

Offline and read-only by default, no SQL credentials, connections or report execution; no automatic edits or deployment. Windows and Linux CI with synthetic fixtures.

## Documentation

- [Discovery contract](docs/PR-02-discovery-contract.md)
- [Architecture decision](docs/ADR-0001-architecture.md)
- [Security](SECURITY.md)

## Roadmap

PR-03 RDL static validation; PR-04 generation and RTL; PR-05 Dynamics RDP semantic inspection; PR-06 generation; PR-07 checkpoints/evals/Obsidian.

## Reference documentation

- https://code.claude.com/docs/en/plugins/create
- https://code.claude.com/docs/en/skills
- https://learn.microsoft.com/en-us/sql/reporting-services/plan-for-report-design-and-report-deployment-reporting-services

License has not been selected.
