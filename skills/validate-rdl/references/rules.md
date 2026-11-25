# Rule reference

Catalog source of truth: `python scripts/rdl_validate.py --rules`. Severity `error` makes a file FAIL; `warning` and `info` never do. A rule marked derived or heuristic is this plugin's judgement, not a Microsoft requirement.

## Contents

- Structure: RDL001, RDL002, RDL003
- Names, references and parameter panel: RDL010, RDL011, RDL012, RDL013, RDL014, RDL015
- Expressions and caller parameters: RDL020, RDL021, RDL022, RDL023
- Layout, security and Tablix members: RDL030, RDL031, RDL040, RDL070
- Right-to-left and mixed direction: RDL050, RDL051, RDL052, RDL053, RDL054, RDL055, RDL056 - in [rules-rtl.md](rules-rtl.md)
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

### RDL010 — Names are unique within their scope (exact duplicate is an error, case-only a warning)
- Severity: error for an exact duplicate, warning when two names differ only by case
- What it checks: Duplicate `Name` among `DataSource`, among `DataSet`, among `ReportParameter`, and among report items (Textbox, Tablix, Rectangle, Image, Line, Subreport, Chart, GaugePanel, Map, CustomReportItem).
- Why it matters: Names must be unique in the innermost named scope. CLS identifiers differing only by case are not distinct and expressions compare identifiers case-insensitively, so `Textbox1` and `textbox1` may be ambiguous. Designer-saved Microsoft reports with case-only collisions exist and do deploy, which is why that case is a warning, not an error.
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

### RDL015 — 2016/01 ReportParametersLayout grid holds exactly one cell per ReportParameter
- Severity: error
- What it checks: 2016/01 only. With any `ReportParameter`, `ReportParametersLayout/GridLayoutDefinition` must exist; `CellDefinition` count equals the parameter count; each `ParameterName` is a declared parameter (case-insensitive) and appears once; `ColumnIndex` < `NumberOfColumns`, `RowIndex` < `NumberOfRows` (an omitted index reads as 0); no two cells share a slot. Hidden parameters need a cell too.
- Why and fix: Report Builder refuses the preview ("The number of defined parameters is not equal to the number of cell definitions in the parameter panel"), also when the layout is absent. Add or correct the grid, one cell per parameter. Basis: observed Report Builder error; the slot and bounds checks are derived.

### RDL020 — Parameters!X references a defined ReportParameter
- Severity: error
- What it checks: Every `Parameters!Name` in an expression must name a `ReportParameter` (case-insensitive).
- Why it matters: An undefined parameter fails when the report is processed.
- Typical fix: Fix the spelling or add the `ReportParameter`.
- Basis: Cross-reference logic (derived; not an MS-RDL rule).

### RDL021 — Fields!X references a Field of the in-scope dataset
- Severity: warning
- What it checks: Resolves `Fields!Name` against the nearest ancestor that has a `DataSetName` child, otherwise the only dataset. Any string literal in the expression that equals a dataset name (the scope argument of `First`, `Sum`, `Lookup` and similar: `=First(Fields!X.Value, "Other")`) adds that dataset to the allowed set. Text inside VB string literals is never treated as a reference. The check is skipped when no dataset can be determined.
- Why it matters: A missing field gives an error value at render time. It is only a warning because expression scope is not fully evaluated.
- Typical fix: Add the field to the dataset `Fields`, correct the name, or point the data region at the right dataset.
- Basis: Scope-dependent logic (derived).

### RDL022 — ReportParameter is referenced by some expression
- Severity: info
- What it checks: Flags a `ReportParameter` that no expression (`Parameters!Name`, outside string literals) and no query text (`@Name` in any `CommandText`) uses.
- Why it matters: An unused parameter prompts the user for a value that changes nothing.
- Typical fix: Wire it into a query or filter, or delete it. Ignore when it is intentionally unused.
- Basis: Cross-reference logic (derived).

### RDL023 — Caller parameter set matches the declared ReportParameters (opt-in)
- Severity: error for a sent name the report does not declare; warning for a declared parameter with no `DefaultValue` that the caller does not send
- What it checks: Only with `--file <rdl> --expect-params A,B,...` (the names an application puts in its URL-access request). Names are compared exactly, case included. Without the option the rule never runs.
- Why and fix: The report server rejects a request that carries an undeclared parameter, and prompts or fails for a missing value with no default. Declare the parameter (and give it a panel cell, RDL015), or change the caller. Basis: URL access behaviour (observed).

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

### RDL070 — Static TablixMembers kept with a dynamic member share one RepeatOnNewPage value
- Severity: error
- What it checks: In each `TablixMembers` list, the unbroken run of static members with `KeepWithGroup=After` just before a dynamic member (one with `Group`), and the run with `KeepWithGroup=Before` just after it, must each hold one `RepeatOnNewPage` value. Absent means `false`. The member next to the group sets the expected value. Hidden members count.
- Why and fix: Report Builder refuses the Tablix ("... must have the same value set for the RepeatOnNewPage property as those following or preceding the dynamic TablixMember"). Set the same value on every member of the run. Basis: observed Report Builder error; the run definition is derived, not taken from a Microsoft specification.

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
- What it checks: With `--root`, and only when the scanned folder contains at least one `.rds`, `.rsds` or `.rsd` file, each `DataSourceReference` and `SharedDataSetReference` is reduced to its last path segment and matched against those file names. A root with no shared files skips the rule, because the references then point at server-managed items.
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
[rsc]: https://raw.githubusercontent.com/microsoft/ReportingServicesTools/master/ReportingServicesTools/Functions/CatalogItems/Write-RsCatalogItem.ps1
[dsd]: https://learn.microsoft.com/en-us/dotnet/api/reportservice2010.datasourcedefinition.connectstring
[inv]: https://raw.githubusercontent.com/microsoft/Reporting-Services/master/PaginatedReportSamples/Invoice.rdl
