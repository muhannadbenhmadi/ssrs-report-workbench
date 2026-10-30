# Rule reference

Catalog source of truth: `python scripts/rdl_validate.py --rules`. Severity `error` makes a file FAIL; `warning` and `info` never do. A rule marked derived or heuristic is this plugin's judgement, not a Microsoft requirement.

## Contents

- Structure: RDL001, RDL002, RDL003
- Names and references: RDL010, RDL011, RDL012, RDL013, RDL014
- Expressions: RDL020, RDL021, RDL022
- Layout and security: RDL030, RDL031, RDL040
- Right-to-left: RDL050, RDL051, RDL052, RDL053, RDL054
- Companion files: RDL060, RDL061, RDL062
- Link references (end of file)

### RDL001 — File is well-formed XML with no DTD or entity declaration
- Severity: error
- What it checks: Rejects files that are not well-formed XML or contain `<!DOCTYPE` / `<!ENTITY`, before parsing.
- Why it matters: RDL never uses DTDs; entity declarations enable entity-expansion attacks against XML parsers. A parse error means the report server cannot load the file either.
- Typical fix: Fix the reported XML error (unclosed tag, bad character, wrong encoding). Remove any DTD or entity declaration.
- Basis: XML 1.0 well-formedness; safety rule of this plugin (not an MS-RDL rule).

### RDL002 — Root is Report in a supported namespace
- Severity: error (warning for legacy)
- What it checks: Root element must be `Report` in the 2008/01, 2010/01 or 2016/01 namespace. 2003/10 and 2005/01 produce a warning; any other namespace is an error and stops further rules.
- Why it matters: A wrong or misspelled namespace makes the report server treat the file as an unknown format. Legacy namespaces are only upgraded by Report Designer or SSDT.
- Typical fix: Set `xmlns` to the namespace for the target server (2016/01 for SSRS 2016 and later and Power BI Report Server). For legacy files, open and re-save in Report Designer, SSDT or Report Builder.
- Basis: [MS-RDL namespace][ns]; [Find the RDL schema version][ver].

### RDL003 — Version-specific required structure is present
- Severity: error
- What it checks: 2008/01: `Body`, `Page` and `Width` directly under `Report`. 2010/01 and 2016/01: at least one `ReportSections/ReportSection`, each with `Body/Height`, `Width` and `Page`. Child order is not checked (the 2016/01 content model is an unordered choice).
- Why it matters: Missing required parts make the definition invalid for that schema version.
- Typical fix: Add the missing element, or move 2008-style top-level elements into a `ReportSection` when targeting 2010/01 or 2016/01.
- Basis: [MS-RDL Report][rep]; [2016/01 XSD][xsd].

### RDL010 — Names are unique (case-insensitive) within their scope
- Severity: error
- What it checks: Duplicate `Name` among `DataSource`, among `DataSet`, among `ReportParameter`, and among report items (Textbox, Tablix, Rectangle, Image, Line, Subreport, Chart, GaugePanel, Map, CustomReportItem).
- Why it matters: Names must be unique in the innermost named scope, and CLS identifiers differing only by case are not distinct, so `Textbox1` and `textbox1` collide.
- Typical fix: Rename one of the duplicates and update every expression that references it (`ReportItems!Name`, `Fields!`, `Parameters!`).
- Basis: [RDL overview][ov]; [MS-RDL glossary][gl].

### RDL011 — DataSet Query/DataSourceName names an existing DataSource
- Severity: error
- What it checks: Each `DataSet/Query/DataSourceName` must equal the `Name` of a `DataSource` in the same report.
- Why it matters: A dangling reference fails at deployment or at first data retrieval.
- Typical fix: Correct the name, or add the missing `DataSource`. The message lists the known sources.
- Basis: [2016/01 XSD][xsd] (`Query/DataSourceName` required) plus cross-reference logic.

### RDL012 — DataSet has non-empty Query/CommandText unless it is shared
- Severity: error
- What it checks: An embedded dataset needs `Query/CommandText` with text. A dataset with `SharedDataSet` is exempt.
- Why it matters: An empty command text gives the data source nothing to run.
- Typical fix: Add the query or command text, or switch the dataset to a shared dataset reference.
- Basis: [2016/01 XSD][xsd].

### RDL013 — DataSource has not both ConnectionProperties and DataSourceReference
- Severity: error
- What it checks: A `DataSource` may carry `ConnectionProperties` (embedded) or `DataSourceReference` (shared), not both.
- Why it matters: MS-RDL states the two are mutually exclusive.
- Typical fix: Keep one: remove `DataSourceReference` for an embedded source, or remove `ConnectionProperties` for a shared one.
- Basis: [MS-RDL DataSource.ConnectionProperties][cp].

### RDL014 — ReportParameter DataType is a valid RDL type
- Severity: error
- What it checks: `ReportParameter/DataType` must be Boolean, DateTime, Integer, Float or String.
- Why it matters: Other values (for example `Text` or `Int`) are not in the RDL enumeration.
- Typical fix: Use one of the five valid types.
- Basis: [2016/01 XSD][xsd]; [RDL overview][ov].

### RDL020 — Parameters!X references a defined ReportParameter
- Severity: error
- What it checks: Every `Parameters!Name` in an expression must name a `ReportParameter` (case-insensitive).
- Why it matters: An undefined parameter fails when the report is processed.
- Typical fix: Fix the spelling or add the `ReportParameter`.
- Basis: Cross-reference logic (derived; not an MS-RDL rule).

### RDL021 — Fields!X references a Field of the in-scope dataset
- Severity: warning
- What it checks: Resolves `Fields!Name` against the nearest ancestor that has a `DataSetName` child; otherwise the only dataset; otherwise the check is skipped.
- Why it matters: A missing field gives an error value at render time. It is only a warning because scope rules (aggregates or lookups that name another dataset) are not fully evaluated.
- Typical fix: Add the field to the dataset `Fields`, correct the name, or point the data region at the right dataset.
- Basis: Scope-dependent logic (derived).

### RDL022 — ReportParameter is referenced by some expression
- Severity: info
- What it checks: Flags a `ReportParameter` that no expression or `QueryParameter` uses.
- Why it matters: An unused parameter prompts the user for a value that changes nothing.
- Typical fix: Wire it into a query or filter, or delete it. Ignore when it is intentionally unused.
- Basis: Cross-reference logic (derived).

### RDL030 — Size values are <number><unit> and at most 160in
- Severity: error
- What it checks: Literal `Width`, `Height`, `Top`, `Left`, `PageWidth`, `PageHeight`, margins and interactive sizes must be a number plus cm, mm, in, pt or pc, and not exceed 160 in. Expressions are skipped.
- Why it matters: The XSD types sizes as a plain string, so bad units pass the schema but fail in the report processor.
- Typical fix: Add the unit (`2.5cm`) and keep the value within 160 in.
- Basis: [RDL overview, Size type][ov]; [2016/01 XSD][xsd] (`SizeType` has no pattern facet).

### RDL031 — Section width plus margins fits the page width
- Severity: warning
- What it checks: When literal, `ReportSection/Width + LeftMargin + RightMargin` must not exceed `PageWidth`.
- Why it matters: A wider body spills onto extra pages in paginated and PDF output.
- Typical fix: Narrow the body or widen the page. Check landscape swaps of `PageWidth` and `PageHeight`.
- Basis: Layout logic (derived; not an MS-RDL rule).

### RDL040 — ConnectString embeds credentials (value never shown)
- Severity: warning
- What it checks: Flags `Password=`, `Pwd=`, `User ID=` or `Uid=` inside `ConnectString`. Only the key name is reported.
- Why it matters: Credentials stored in the RDL travel with source control and every export.
- Typical fix: Use integrated security, a shared data source with credentials stored on the server, or a prompt. Rotate any password already committed.
- Basis: Security smell (heuristic). The sample [Invoice.rdl][inv] keeps `ConnectString` and `IntegratedSecurity` in `ConnectionProperties`.

### RDL050 — Style/Direction is Default, LTR, RTL or an expression
- Severity: error
- What it checks: Literal `Style/Direction` must be `Default`, `LTR` or `RTL`. Values starting with `=` are skipped.
- Why it matters: The XSD type is a plain string, so a typo such as `Rtl` passes the schema but is not a valid value.
- Typical fix: Use the exact spelling `RTL` or `LTR`.
- Basis: [MS-RDL Style.Direction][dir].

### RDL051 — Style/Direction is set where it is ignored
- Severity: info
- What it checks: `Direction` has no effect unless the grandparent of `Style` is `TextRun`, `Subreport`, `Chart`, `LinearGauge` or `RadialGauge`.
- Why it matters: Setting it on a `Textbox`, `Tablix` or `Paragraph` style looks right in the file but does nothing.
- Typical fix: Move `Direction` into the `TextRun` style (or the chart, gauge or subreport style).
- Basis: [MS-RDL Style.Direction][dir].

### RDL052 — Style/NumeralVariant is an integer 1..7 or an expression
- Severity: error
- What it checks: Literal `NumeralVariant` must be an integer from 1 to 7. Meaning: 1 default, 2 Western digits, 3 native digits for ar, bn, bo, fa, gu, hi, kn, kok, lo, mr, ms, or, pa, sa, ta, te, th, ur; 4 to 6 for ko, ja, zh; 7 for ko. The static check covers the range only, not the culture match.
- Why it matters: An out-of-range value is invalid, and a variant that does not suit the culture is silently ignored.
- Typical fix: Use 3 for native digits in Arabic, Persian and Urdu reports.
- Basis: [MS-RDL Style.NumeralVariant][nv].

### RDL053 — Tablix/LayoutDirection is LTR or RTL
- Severity: error
- What it checks: Literal `Tablix/LayoutDirection` must be `LTR` or `RTL`.
- Why it matters: RTL reverses column order and moves row headers right. It does not change Excel sheet direction.
- Typical fix: Use `LTR` or `RTL`.
- Basis: [2016/01 XSD][xsd]; [LayoutDirection (Tablix)][ld]; Excel caveat from [Microsoft Q&A][xl].

### RDL054 — RTL-language report declares no RTL direction
- Severity: info
- What it checks: When `Report/Language` starts with `ar`, `he`, `fa` or `ur`, flags a report with no `Direction` of RTL and no `LayoutDirection` of RTL anywhere.
- Why it matters: Readiness hint only. The report may be intentionally left-to-right, or may set direction through expressions.
- Typical fix: Set `Style/Direction` RTL on text runs and `LayoutDirection` RTL on tables. See `rdl-structure.md`, section "Right-to-left reports".
- Basis: Heuristic (derived; not an MS-RDL rule).

### RDL060 — .rds has RptDataSource with Name, Extension and ConnectString
- Severity: error
- What it checks: Root must be `RptDataSource` with `Name`, `ConnectionProperties/Extension` and `ConnectionProperties/ConnectString`.
- Why it matters: The ReportingServicesTools upload function throws "Invalid data source file!" when any is missing.
- Typical fix: Add the missing element. Re-export the data source from SSDT if unsure.
- Basis: [Write-RsCatalogItem.ps1][rsc].

### RDL061 — .rsds has DataSourceDefinition with Extension and ConnectString
- Severity: error
- What it checks: Root must be `DataSourceDefinition` with `Extension` and `ConnectString`.
- Why it matters: Both are required to create a data source item on the server.
- Typical fix: Add the missing element. `Extension` is the data processing extension name, for example SQL.
- Basis: [Write-RsCatalogItem.ps1][rsc]; [DataSourceDefinition.ConnectString][dsd]. The exact `.rsds` nesting is unverified against a Microsoft schema.

### RDL062 — Shared data source/dataset reference resolves to a file in the scanned root
- Severity: warning
- What it checks: With `--root`, each `DataSourceReference` and `SharedDataSetReference` is reduced to its last path segment and matched against `.rds`, `.rsds` and `.rsd` file names in the scanned folder.
- Why it matters: A reference to a shared item missing from the project fails at deploy unless the item already exists on the server.
- Typical fix: Add the shared file to the project, or ignore if the item is managed server-side.
- Basis: Deploy logic (derived; name matching is by file stem only).

## Link references

[ns]: https://learn.microsoft.com/en-us/openspecs/sql_server_protocols/MS-RDL/6f0bcdd5-0a38-4a38-a8fa-05eb8249f59a
[ver]: https://learn.microsoft.com/en-us/sql/reporting-services/reports/find-the-report-definition-schema-version-ssrs
[rep]: https://learn.microsoft.com/en-us/openspecs/sql_server_protocols/ms-rdl/6bbaafec-020b-406c-b4e7-5e4318b616cb
[xsd]: https://learn.microsoft.com/en-us/openspecs/sql_server_protocols/ms-rdl/52ce3983-2bfc-4e72-9359-42aaf5fe4509
[ov]: https://learn.microsoft.com/en-us/sql/reporting-services/reports/report-definition-language-ssrs
[gl]: https://learn.microsoft.com/en-us/openspecs/sql_server_protocols/ms-rdl/b2482b3f-74ab-4ca8-a9e5-c07955011743
[cp]: https://learn.microsoft.com/en-us/openspecs/sql_server_protocols/ms-rdl/66ba68b2-3d03-443a-bcc1-4cf0f53012a5
[dir]: https://learn.microsoft.com/en-us/openspecs/sql_server_protocols/MS-RDL/4c0efe27-0fb0-43ca-a3c1-d37cd7fb4c72
[nv]: https://learn.microsoft.com/en-us/openspecs/sql_server_protocols/ms-rdl/e1b67670-1195-48a5-afd8-033107befe20
[ld]: https://learn.microsoft.com/en-us/previous-versions/sql/sql-server-2008/ms155126(v=sql.100)
[xl]: https://learn.microsoft.com/en-us/answers/questions/1091489/ssrs-export-to-excel-ignores-default-sheet-directi
[rsc]: https://raw.githubusercontent.com/microsoft/ReportingServicesTools/master/ReportingServicesTools/Functions/CatalogItems/Write-RsCatalogItem.ps1
[dsd]: https://learn.microsoft.com/en-us/dotnet/api/reportservice2010.datasourcedefinition.connectstring
[inv]: https://raw.githubusercontent.com/microsoft/Reporting-Services/master/PaginatedReportSamples/Invoice.rdl
