# ADR-0001 — Independent reporting adapters

Status: Accepted for the PR-01 foundation (2026-10-30).

## Context

SSRS RDL is an XML report definition format; Dynamics 365 F&O RDP is an X++ provider pattern. Conflating their runtime validation would create incorrect success claims and unsafe assumptions.

## Decision

Use one Claude Code plugin with a small shared engineering core and independent RDL and Dynamics adapters. PR-01 introduces only the manifest, diagnostic skill, read-only Python script, offline tests and CI. Platform adapters will be introduced in later PRs and must have separate validation gates.

Python 3.11+ supplies deterministic local checks. Claude Code orchestrates workflows, but model output cannot substitute for an RDL runtime, X++ compiler, authenticated report execution or deployment validation.

## Safety boundaries

No access to production databases; no automatic deployment; no secret logging; no unverified PASS; no modifying application repositories as an implicit side effect. Each change must include evidence and a rollback path.

## Consequences

Foundation tests can run without SSRS or Dynamics installed, but success cannot be interpreted as report correctness. Future adapters are optional and isolated by design.

## PR-03 amendment

The PostToolUse hook is advisory only: it adds validation context after an RDL write or edit, never blocks a tool call and never edits files. The static validator cannot replace the RDL runtime; a PASS means no static rule fired, not that a report deploys or renders on SSRS or Power BI Report Server.
