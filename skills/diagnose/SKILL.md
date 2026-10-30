---
name: diagnose
description: Run a read-only foundation check of the SSRS Report Workbench plugin. Use when validating its manifest, diagnostic skill, or local test readiness.
disable-model-invocation: true
---

# Diagnose SSRS Report Workbench

This is a PR-01 bootstrap skill, NOT an RDL or Dynamics validator.

1. Locate the plugin root containing `.claude-plugin/plugin.json`. Do not assume the application repository is the plugin root.
2. Explain the check is read-only, local, and does not connect to databases, SSRS, or Dynamics.
3. Run `python "<plugin-root>/scripts/diagnose.py" --root "<plugin-root>" --json` with Python 3.11+; adjust quoting for the shell.
4. Report exact status and checks. Do not claim Claude CLI validation or report rendering without evidence.
5. If Claude CLI is installed and requested, separately run `claude plugin validate <plugin-root> --strict`.
6. On failure, report the failing path and minimal remedy; do not modify files without authorization.

Return PASS, FAIL, or BLOCKED, the commands run, findings, and unrun checks.
