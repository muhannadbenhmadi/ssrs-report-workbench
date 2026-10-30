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
| RDL010 | error | Duplicate `Name` (case-insensitive) among `DataSource`, `DataSet`, `ReportParameter`, and among report items (`Textbox`, `Tablix`, `Rectangle`, `Image`, `Line`, `Subreport`, `Chart`, `GaugePanel`, `Map`, `CustomReportItem`) | RDL overview (names unique in scope); MS-RDL glossary (CLS identifiers differ by more than case) |
| RDL011 | error | `DataSet/Query/DataSourceName` names an existing `DataSource` | 2016/01 XSD + logic |
| RDL012 | error | `DataSet` has `Query/CommandText` (non-empty) unless it has `SharedDataSet` | 2016/01 XSD |
| RDL013 | error | `DataSource` does not have both `ConnectionProperties` and `DataSourceReference` | MS-RDL `DataSource.ConnectionProperties` |
| RDL014 | error | `ReportParameter/DataType` ∈ {Boolean, DateTime, Integer, Float, String} | 2016/01 XSD |
| RDL020 | error | Every `Parameters!X` in any expression names a `ReportParameter` | logic |
| RDL021 | warning | Every `Fields!X` in an expression names a `Field` of the in-scope dataset (nearest ancestor with a `DataSetName` child; else the only dataset; else skipped) | logic, scope-dependent |
| RDL022 | info | `ReportParameter` never referenced by any expression or `QueryParameter` | logic |
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
| RDL062 | warning | `DataSourceReference` / `SharedDataSetReference` resolves to a `.rds`/`.rsds`/`.rsd` file stem in the scanned root (only when `--root` is used) | deploy logic (derived) |

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

`status` is FAIL when any finding has severity `error` or any file could not be read.
Exit code 0 = PASS, 1 = FAIL or fatal error (details on stderr as JSON).

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

## Acceptance

- `python -m unittest discover -s tests -v` passes on Windows and Linux, Python 3.11 and 3.13.
- `python scripts/rdl_validate.py --root tests/fixtures --json` exits 1 (fixtures include
  deliberately broken files) and the PASS fixture reports zero errors.
- `claude plugin validate . --strict` passes.
- No test writes into the inspected directory (`test_no_writes` pattern from PR-02).
- PR-01 and PR-02 tests unchanged except for the `.rsds` extension addition.
