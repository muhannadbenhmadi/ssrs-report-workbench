# SSRS Report Workbench

Claude Code plugin with independent **SSRS RDL** and **Dynamics 365 Finance & Operations RDP** workflows.

## Install

```text
/plugin install ssrs-report-workbench --marketplace muhannadbenhmadi/ssrs-report-workbench
```

Or in two steps from a shell:

```sh
claude plugin marketplace add muhannadbenhmadi/ssrs-report-workbench
claude plugin install ssrs-report-workbench@ssrs-report-workbench
```

## Implemented

PR-01: Manifest, diagnostic skill, offline tests and CI.

PR-02 (proposed): read-only source discovery, SHA-256 inventory/index, CLI-driven requirements question generator.

PR-03: offline RDL static validation (`.rdl`, `.rds`, `.rsds`) with a rule catalog, a skill, a read-only reviewer agent, an advisory post-edit hook and marketplace packaging. There is still no report generator, runtime connector or deployment function.

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

## RDL validation (read-only)

```sh
python scripts/rdl_validate.py --file reports/Invoice.rdl --json
python scripts/rdl_validate.py --root path/to/project --json
python scripts/rdl_validate.py --rules
```

Output is a JSON document: top-level `status` (`PASS` or `FAIL`) and `summary` (`files`, `errors`, `warnings`, `info`), then one entry per file with its `findings` (`rule`, `severity`, `location`, `message`). Exit code 0 means PASS; 1 means FAIL or a fatal error. A PASS means no static rule fired. It is not proof that a report deploys or renders.

- Skill: `/ssrs-report-workbench:validate-rdl <path>` runs the validator and explains each finding.
- Agent: `@agent-ssrs-report-workbench:rdl-reviewer` is a read-only reviewer that reports with evidence and never edits or deploys.
- Hook: a `PostToolUse` hook fires after Claude writes or edits a `.rdl`, `.rds` or `.rsds` file and adds a short validation summary to Claude's context. It is advisory, never blocks, and ignores other files. It uses the first working interpreter among `python3`, `python` and `py` (Windows Store aliases that only print an install hint are skipped). Disable it with `"disableAllHooks": true` in Claude Code settings.

## Safety

Offline and read-only by default, no SQL credentials, connections or report execution; no automatic edits or deployment. The validator rejects `<!DOCTYPE` and `<!ENTITY` before parsing and refuses symlinks and oversized files. Credential keys in connection strings are reported without their values. Windows and Linux CI with synthetic fixtures.

## Documentation

- [Discovery contract](docs/PR-02-discovery-contract.md)
- [RDL validation contract](docs/PR-03-rdl-validation-contract.md)
- [Architecture decision](docs/ADR-0001-architecture.md)
- [Security](SECURITY.md)

## Roadmap

PR-03 RDL static validation (done); PR-04 generation and RTL; PR-05 Dynamics RDP semantic inspection; PR-06 generation; PR-07 checkpoints/evals/Obsidian.

## Reference documentation

- https://code.claude.com/docs/en/plugins/create
- https://code.claude.com/docs/en/skills
- https://learn.microsoft.com/en-us/sql/reporting-services/plan-for-report-design-and-report-deployment-reporting-services

License has not been selected.
