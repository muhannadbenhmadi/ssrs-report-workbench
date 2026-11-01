# RDL inspector evidence and residual risks

Date: 2026-11-01. Baseline: `main` at `b08908d524d8c0bedc1e881db573e1fa7bcfde8f` (PR-03 merged). Repository HEAD, README, contributing/security/architecture and PR-03 contract were reviewed before implementation. GitHub PRs #1, #2 and #3 were merged; no open PR existed at the start or the pre-publication recheck. Issue #4's fixes are already in the baseline.

## Scope and preservation

Adds `scripts/rdl_inspect.py`, `skills/inspect-rdl/SKILL.md`, 26 inspector tests, a synthetic multi-section/nested-Tablix fixture, the inspector contract and this report. README, CONTRIBUTING, SECURITY and the existing Windows/Linux CI gain inspection instructions/checks. Plugin manifest version becomes 0.3.0 and catalog descriptions include inspection.

The five operations are `describe_report`, `list_datasets`, `list_parameters`, `list_tablix`, `list_columns`. The implementation is original, inspired by the read interfaces in `bethmaloney/rdl-mcp` at `ed2b98125b0e4ae60e2e4b7002776d62df6bfaf5`, with no imported/copied upstream code. No generator, edit planner, RDL writer, new hook or runtime connector.

All existing scripts (including `rdl_validate.py`, `rdl_hook.py`, discovery and diagnostics), existing tests/fixtures, `hooks/`, `agents/`, `skills/validate-rdl/`, the PR-03 contract and architecture ADR are byte-for-byte unchanged from the baseline. No Dynamics RDP code or workflow is added or modified. The new inspector does not import the validator.

## Executed local checks

| Check | Linux (WSL2), Python 3.14.4 | Windows 11, Python 3.12.10 |
|---|---|---|
| `python -m unittest discover -s tests -v` | 147 tests, OK, no skips | 147 tests, OK, 3 skipped |
| `python -m compileall -q scripts tests` | exit 0 | exit 0 |
| `python scripts/diagnose.py --root . --json` | PASS, 5 checks | PASS, 5 checks |
| `python scripts/rdl_validate.py --root tests/fixtures/rdl --json` | exit 1 as expected, deliberately broken fixture | same |
| All five inspector CLI operations on `tests/fixtures/inspect/multi_2016.rdl` (`list_columns --tablix-id 1`) | exit 0, OK | exit 0, OK |

The 3 Windows skips are symlink creation tests in diagnostics, validator and inspector. The account lacks that permission. All three execute on Linux. Windows reparse/junction refusal is implemented but a real junction attack has not been separately exercised locally.

- Skill creator `quick_validate.py skills/inspect-rdl`: valid.
- `git diff --check`: clean.
- Windows `claude plugin validate . --strict`: exit 0, Validation passed. Existing directory-submission notes remain: missing LICENSE and icon. This does not establish Claude runtime or skill behavior under a model.
- Tests exercise byte caps, pagination progress, nested truncation, exact namespace matching, all five recognized versions, malformed XML, encoded DTDs/entities, oversized/deep/large-node documents, hostile identifiers, duplicate Tablix names, static bindings outside VB literals, missing optional properties, complex spans, paths with spaces/Arabic, redacted errors and excluded-channel secret canaries.
- SHA-256 and directory snapshots remain unchanged across all five operations on inspected synthetic inputs.

## Microsoft-authored report smoke checks

Fetched public report text copies into a temporary directory outside the repository. No third-party report is committed or queried. On Linux, ran all five interfaces, including `list_columns` for every Tablix with `limit=100`. Checked SHA-256 before/after each report; every inspected copy was unchanged. These are extraction checks, not validator/runtime results.

| Source | Actual namespace | Datasets / parameters / Tablix / body columns | Result |
|---|---|---|---|
| [Reporting-Services Invoice.rdl](https://github.com/microsoft/Reporting-Services/blob/master/PaginatedReportSamples/Invoice.rdl), fetched blob `d81d18617edc843ca699942e9063720c8db515d9` | 2016/01 | 5 / 1 / 3 / 11 | Counts/lists OK; columns explicitly INCOMPLETE: regions 1/3 `cells-truncated`, region 2 `complex-grid-bindings-omitted` |
| [SqlNexus NexusReports/Missing Indexes_C.rdl](https://github.com/microsoft/SqlNexus/blob/a30c7082d8691113174c146c01cab26f547e88ca/NexusReports/Missing%20Indexes_C.rdl), blob `1424d880251d27726f47f82c6b075286d6aa706c` | 2016/01 | 2 / 5 / 2 / 10 | All requested metadata OK |
| [SqlNexus NexusReports_bak/Perfmon_C.rdl](https://github.com/microsoft/SqlNexus/blob/a30c7082d8691113174c146c01cab26f547e88ca/NexusReports_bak/Perfmon_C.rdl), blob `44675c2c75c3a3d9006a164e86002daf77a247f2` | 2010/01 | 6 / 6 / 3 / 13 | All requested metadata OK |
| [SqlNexus NexusReports_bak/Missing Indexes_C.rdl](https://github.com/microsoft/SqlNexus/blob/a30c7082d8691113174c146c01cab26f547e88ca/NexusReports_bak/Missing%20Indexes_C.rdl), blob `4e858bd734c8c12f138dec94abe8826195f05c33` | 2008/01 | 1 / 4 / 1 / 4 | All requested metadata OK |

The namespace is read from the document, not inferred from its filename or repository folder. All four reports retained their before/after SHA-256 values.

## Remote CI evidence

The existing matrix is retained: Ubuntu and Windows, Python 3.11 and 3.13. It compiles, runs the full unit suite, diagnoses packaging, checks the unchanged validator fixtures, and invokes all five inspector CLI interfaces. Remote run URLs and conclusions are recorded in the PR description after the runs are actually reviewed. Local success is not represented as remote CI success.

## Remaining risks and unrun checks

- This is bounded metadata extraction. It performs no expression evaluation, SQL/data retrieval, XSD validation, SSRS rendering/deployment, Dynamics compilation or production checks.
- Column samples are XML body positions. Group headers/corners, dynamic/indexed bindings, aggregate dataset scope, rendered matrix expansion, charts and custom report items are not modeled. Complex/merged grids deliberately omit bindings. At most 3 rows and 20 references per sample are returned; datasets expose at most 50 fields and do not paginate fields.
- RDL 2003/2005 metadata is available, but legacy layout stays INCOMPLETE. Unknown namespaces fail closed. Encodings other than UTF-8 and BOM-marked UTF-16 are rejected.
- Connection properties/ConnectStrings, SQL/procedure text, defaults/valid values/prompts, cell literals, expressions, code and external paths are excluded. Identifier names remain visible, may be confidential and must be treated as untrusted data. The allowlist is not a general secret scanner.
- Link/reparse/type/identity checks assume a stable local directory. Concurrent ancestor replacement and input changes between paginated calls remain possible; IDs/offsets are only stable for unchanged files. OS-mounted network filesystems are outside the offline tool's control.
- Actual Power BI Report Server Report Builder output and model-driven skill execution remain unverified. The small public smoke corpus is not comprehensive designer coverage.

## Rollback

Before merge, close the independent PR; no main-branch change or migration has occurred. After merge, revert this PR's commits, including the 0.3.0 manifest bump. The inspector never writes RDL, credentials, configuration, datasets or deployment state. Existing PR-03 validation and Dynamics RDP are independent and remain intact.
