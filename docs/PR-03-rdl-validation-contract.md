# PR-03 — RDL static validation contract

Status: Implementation proposed for review (2026-10-30). Baseline: `main` at `2312710` (PR-02 merged).

## Purpose

Add an offline, read-only static validator for SSRS report definition files (`.rdl`) and
their companion shared data source files (`.rds`, `.rsds`), expose it as a plugin skill,
a read-only reviewer agent and a post-edit hook, and make the plugin installable from a
marketplace. Nothing in this PR renders, deploys, compiles or connects to anything.

## Boundaries

- Python 3.11+ standard library only (`xml.etree.ElementTree`, `re`, `json`, `argparse`).
- Structural and cross-reference checks only. Python's standard library cannot validate
  against the RDL XSD, so every rule is hand-written and documented with its basis in
  `skills/validate-rdl/references/rules.md`.
- A clean result means "no rule fired", never "the report deploys or renders".
- Files containing `<!DOCTYPE` or `<!ENTITY` are rejected before parsing (RDL never uses
  DTDs; this blocks entity-expansion attacks against `xml.etree`).
- Symlinks are refused; files over 8 MiB are skipped with a warning; at most 10,000
  candidate files per run.
- Output goes to stdout only. Connection-string values are never echoed; only the fact
  that a credential-looking key is present.
- The Dynamics 365 RDP adapter is untouched (PR-05).

## Supported RDL namespaces

| Namespace year | Treatment |
|---|---|
| 2008/01 | Supported. `Body`, `Page`, `Width` required directly under `Report`. |
| 2010/01, 2016/01 | Supported. `ReportSections/ReportSection` required, each with `Body/Height`, `Width`, `Page`. |
| 2003/10, 2005/01 | Parsed; `RDL002` warning "legacy namespace, upgrade in Report Designer". Structural rules skipped. |
| Anything else | `RDL002` error. No further rules run. |

Source: MS-RDL 1.3.3.1 (namespace list) and the MS-RDL `Report` element page. The latest
published schema is 2016/01; SSRS 2016 through 2025 and Power BI Report Server emit it.

## Rule catalog

Severity: `error` makes the file FAIL; `warning` and `info` never do.
Expressions (`=...`) are never evaluated. Rules that need a literal value skip expressions.

| Rule | Severity | Check | Basis |
|---|---|---|---|
| RDL001 | error | File is well-formed XML and contains no DTD or entity declaration | XML; safety |
| RDL002 | error / warning | Root is `Report` in a supported namespace (legacy → warning) | MS-RDL 1.3.3.1 |
| RDL003 | error | Version-specific required structure (see table above) | MS-RDL `Report`, 2016/01 XSD |
| RDL010 | error / warning | Duplicate `Name` among `DataSource`, `DataSet`, `ReportParameter`, and among report items (`Textbox`, `Tablix`, `Rectangle`, `Image`, `Line`, `Subreport`, `Chart`, `GaugePanel`, `Map`, `CustomReportItem`). Exact duplicate → error; names differing only by case → warning (designer-saved Microsoft reports with case-only collisions exist) | RDL overview (names unique in scope); MS-RDL glossary (CLS identifiers differ by more than case) |
| RDL011 | error | `DataSet/Query/DataSourceName` names an existing `DataSource` | 2016/01 XSD + logic |
| RDL012 | error | `DataSet` has `Query/CommandText` (non-empty) unless it has `SharedDataSet` | 2016/01 XSD |
| RDL013 | error | `DataSource` does not have both `ConnectionProperties` and `DataSourceReference` | MS-RDL `DataSource.ConnectionProperties` |
| RDL014 | error | `ReportParameter/DataType` ∈ {Boolean, DateTime, Integer, Float, String} | 2016/01 XSD |
| RDL020 | error | Every `Parameters!X` in any expression names a `ReportParameter` | logic |
| RDL021 | warning | Every `Fields!X` in an expression names a `Field` of the in-scope dataset (nearest ancestor with a `DataSetName` child; else the only dataset) or of any dataset named by a string literal in the same expression (aggregate/lookup scope such as `First(Fields!X.Value, "Other")`); skipped when no dataset can be determined | logic, scope-dependent |
| RDL022 | info | `ReportParameter` never referenced by any expression (`Parameters!X`) nor by `@X` in any `CommandText` | logic |
| RDL030 | error | Size values (`Width`, `Height`, `Top`, `Left`, `PageWidth`, `PageHeight`, margins) are `<number><unit>` with unit ∈ {cm, mm, in, pt, pc} and ≤ 160 in | RDL overview (`Size` type) |
| RDL031 | warning | `ReportSection/Width` + `LeftMargin` + `RightMargin` ≤ `PageWidth` when all are literal | layout logic (derived) |
| RDL040 | warning | `ConnectString` contains `Password=`, `Pwd=`, `User ID=` or `Uid=` (value never echoed) | security smell |
| RDL050 | error | `Style/Direction` ∈ {Default, LTR, RTL} or expression | MS-RDL `Style.Direction` |
| RDL051 | info | `Direction` set where the spec says it is ignored (grandparent not `TextRun`, `Subreport`, `Chart`, `LinearGauge`, `RadialGauge`) | MS-RDL `Style.Direction` |
| RDL052 | error | `Style/NumeralVariant` is an integer 1..7 or expression | MS-RDL `Style.NumeralVariant` |
| RDL053 | error | `Tablix/LayoutDirection` ∈ {LTR, RTL} | 2016/01 XSD |
| RDL054 | info | `Report/Language` starts with `ar`, `he`, `fa` or `ur` but no `Direction` = RTL and no `LayoutDirection` = RTL anywhere (RTL readiness) | heuristic (derived) |
| RDL060 | error | `.rds`: root `RptDataSource` with `Name`, `ConnectionProperties/Extension`, `ConnectionProperties/ConnectString` | ReportingServicesTools `Write-RsCatalogItem.ps1` |
| RDL061 | error | `.rsds`: root `DataSourceDefinition` with `Extension` and `ConnectString` | same |
| RDL062 | warning | `DataSourceReference` / `SharedDataSetReference` resolves to a `.rds`/`.rsds`/`.rsd` file stem in the scanned root (only with `--root`, and only when the root contains at least one such file) | deploy logic (derived) |

## Output format

```json
{
  "schema_version": 1,
  "mode": "read-only",
  "tool": "ssrs-report-workbench-rdl-validator",
  "status": "PASS | FAIL",
  "summary": {"files": 3, "errors": 1, "warnings": 2, "info": 0},
  "files": [
    {
      "path": "reports/Invoice.rdl",
      "kind": "rdl",
      "namespace": "http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition",
      "rdl_version": "2016/01",
      "status": "FAIL",
      "findings": [
        {"rule": "RDL011", "severity": "error",
         "location": "Report/DataSets/DataSet[@Name='Orders']/Query/DataSourceName",
         "message": "DataSourceName 'Sales' does not match any DataSource (known: AdventureWorks)"}
      ]
    }
  ],
  "warnings": [{"path": "big.rdl", "reason": "oversize"}]
}
```

`status` is one of three values and the document also carries `coverage_complete`:

| Status | Meaning | Exit code |
|---|---|---|
| `PASS` | No `error` finding and every candidate file was validated (`coverage_complete: true`) | 0 |
| `FAIL` | At least one `error` finding, or a file could not be read | 1 |
| `INCOMPLETE` | No `error` finding, but at least one candidate was skipped (oversize, symlink) or the root held no candidates (`no-candidates`), so `coverage_complete: false` | 2 |

A fatal error (bad arguments, unreadable root) exits 1 with a JSON object on stderr. Integrations
must treat only exit 0 as "clean"; `INCOMPLETE` is never a clean result.

Expression references: `Parameters!X` and `Fields!X` are matched only after every VB string literal
(`"..."`, with `""` as the escaped quote) has been removed from the expression, so text inside quotes
never counts as a reference (`RDL020`, `RDL021`, `RDL022`). An embedded `DataSet/Query` with a
missing or empty `DataSourceName` fails `RDL011`; datasets that use `SharedDataSet` are exempt.

## CLI

```text
python scripts/rdl_validate.py --file <path.rdl> [--json]
python scripts/rdl_validate.py --root <project-dir> [--json] [--max-files N]
python scripts/rdl_validate.py --rules            # prints the rule catalog as JSON
```

Without `--json` a short human summary is printed. `--rules` is the single source of truth;
`references/rules.md` must list every rule ID the catalog defines (a test enforces this).

## Hook

`hooks/hooks.json` registers one `PostToolUse` hook on `Write|Edit`. `scripts/rdl_hook.py`
reads the hook JSON from stdin, returns immediately for non-RDL paths, otherwise validates
the single edited file and returns `additionalContext` with a compact summary (≤ 4,000
characters, no connection-string values). It always exits 0 and never blocks. Disable with
`"disableAllHooks": true` in settings if unwanted.

## Verification against designer-generated reports (2026-10-30)

Seventeen real, designer-saved RDL files (all MIT-licensed, all carrying the `rd:` designer
namespace) were validated read-only with `--root`. They are not committed to this repo; the
sources are listed so the run can be repeated.

| Namespace | Files | Source |
|---|---|---|
| 2016/01 | 7 | `microsoft/Reporting-Services`, `PaginatedReportSamples/*.rdl` (CountrySalesPerformance, Invoice, Labels, Letter, OrganizationExpenditures, RegionalSales, Transcript) |
| 2010/01 | 4 | `microsoft/SqlNexus` @ `a30c7082`, `sqlnexus/Reports/` and `NexusReports_bak/` (Active Queries, System_Requests, Perfmon_C, Loaded Modules_C) |
| 2008/01 | 6 | `microsoft/SqlNexus` @ `a30c7082` (Missing Indexes_C, SysIndexes_C, Query Hash_C); `microsoft/process-customization-scripts` @ `f3797d8d`, `Import/*/Reports/` (Bug Status, Bug Trends, Build Summary) |

Result after the fixes tracked in issue #4: all 17 parse, all 17 PASS, 0 errors, 1 warning,
20 info. The one warning is `RDL010` on `Bug Status.rdl`, which really contains both
`Textbox3` and `textbox3`. The 20 info findings are `RDL022` (parameters with no expression or
`@name` use), which is expected for hidden TFS plumbing parameters.

Before those fixes the same run produced 48 false `RDL021` warnings (aggregate scope literals
such as `First(Fields!PrimaryColor.Value, "Company")`), 1 false `RDL010` error (case-only
duplicate) and 5 noise `RDL062` warnings (no shared files in the scanned root). Those three
patterns are now covered by regression tests.

Still unverified: reports saved by Power BI Report Server's Report Builder specifically, reports
with `Code` blocks or custom assemblies, and `.rsd` shared dataset internals.

## Acceptance

- `python -m unittest discover -s tests -v` passes on Windows and Linux, Python 3.11 and 3.13.
- `python scripts/rdl_validate.py --root tests/fixtures --json` exits 1 (fixtures include
  deliberately broken files) and the PASS fixture reports zero errors.
- `claude plugin validate . --strict` passes.
- No test writes into the inspected directory (`test_no_writes` pattern from PR-02).
- PR-01 and PR-02 tests unchanged except for the `.rsds` extension addition.
