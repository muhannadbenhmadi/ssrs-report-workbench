---
name: discover
description: Inventory SSRS RDL and Dynamics 365 RDP source files safely and ask only for missing target-version and runtime requirements.
disable-model-invocation: true
---

# Discover reporting project (PR-02)

1. Ask user which local project directory is authorized for inspection.
2. Execute `python "<plugin-root>/scripts/discovery.py" --root "<project-root>"` using Python 3.11+.
3. Treat result as a file inventory, not a validated RDL schema or X++ code model.
4. Save stdout to a user-approved local index file only if requested. Never save in the inspected workspace implicitly.
5. When saved, run `python "<plugin-root>/scripts/requirements_wizard.py" --index "<index-path>"`.
6. Present suggested technology only as a suggestion. Ask missing target versions, locale/RTL, and Dev/Test access.
7. Do not connect to SQL Server, Dynamics, or render/deploy reports.
8. On incomplete scans, report warnings and do not claim completeness.

Deliver: file counts by module, candidates, warnings, unanswered questions, and read-only assurance.
