# RDL structure reference

## Contents

- Namespaces
- Required structure per version
- Size type
- Name uniqueness
- Expression collections
- Companion file shapes
- Right-to-left reports
- Link references

## Namespaces

Report definition namespace template: `http://schemas.microsoft.com/sqlserver/reporting/<yyyy>/<mm>/reportdefinition`. Standard extensions are `.rdl` and `.rdlx`; MIME type is `text/xml` ([MS-RDL namespace][ns]).

| Namespace | Tooling that emits it | Validator treatment |
|---|---|---|
| 2003/10 | SQL Server 2000 and 2005 era designers | Legacy, warning RDL002 |
| 2005/01 | SQL Server 2005 Report Designer | Legacy, warning RDL002 |
| 2008/01 | SQL Server 2008 Report Designer | Supported |
| 2010/01 | SQL Server 2008 R2 | Supported |
| 2011/01, 2012/01, 2013/01 | Listed by MS-RDL; not treated as supported by the validator | Error RDL002 |
| 2016/01 | SSRS 2016 and later, SSDT, Report Builder, Power BI Report Server (inferred, see below) | Supported |

- MS-RDL lists 2016/01 as its last version; no newer namespace is published. The mapping "SSRS 2017 to 2025 and Power BI Report Server emit 2016/01" is an inference from the samples, not an explicit Microsoft statement.
- Older reports are upgraded when opened in Report Designer, SSDT or Report Builder, with a backup. The copy on the server is not upgraded in place ([Find the RDL schema version][ver]).
- Designer namespace: `xmlns:rd="http://schemas.microsoft.com/SQLServer/reporting/reportdesigner"`. The path spells `SQLServer` with capital S, Q, L; the report definition namespace is all lowercase. Elements in `rd:` carry designer state and are ignored by the validator.
- A 2016 root also commonly declares `xmlns:df=".../2016/01/reportdefinition/defaultfontfamily"` and `MustUnderstand="df"`.
- Shared datasets (`.rsd`) use a separate namespace, see Companion file shapes.

## Required structure per version

([MS-RDL Report][rep])

| Version | Required children of `Report` |
|---|---|
| 2003/10, 2005/01 | `Body`, `Width` |
| 2008/01 | `Body`, `Page`, `Width` |
| 2010/01, 2016/01 | `ReportSections` with one or more `ReportSection` |

- In 2010/01 and 2016/01 each `ReportSection` holds `Body` (with `Height`), `Width` and `Page`. `Page` holds `PageHeight`, `PageWidth`, margins, header and footer. In 2008/01 these sit under `Report`.
- The 2016/01 `Report` content model is an `xsd:choice` with `maxOccurs="unbounded"`, so child order is free ([2016/01 XSD][xsd]). The validator never checks child order.
- The XSD also allows elements from other namespaces (`##other`, lax), which is why designer `rd:` elements are legal.
- `DataSource` has required attribute `Name`; `ConnectionProperties` and `DataSourceReference` are mutually exclusive ([DataSource.ConnectionProperties][cp]). `DataSet` has required `Name`; `Query/DataSourceName` is required for an embedded query.
- Report item types allowed in a body or cell: `Line`, `Rectangle`, `Textbox`, `Image`, `Subreport`, `Chart`, `GaugePanel`, `Map`, `CustomReportItem`, `Tablix`.
- `ReportParameter/DataType` is one of Boolean, DateTime, Integer, Float, String.

## Size type

([RDL overview][ov])

- A Size is a number followed by a CSS length unit: `cm`, `mm`, `in`, `pt`, `pc`. Maximum 160 in, minimum 0 in. Examples: `2.5cm`, `0.25in`, `12pt`.
- The XSD declares `SizeType` as `xsd:normalizedString` with no pattern, so the schema does not catch a missing or wrong unit. RDL030 does, for literals only.
- Conversion used by the validator: 1 in = 2.54 cm = 25.4 mm = 72 pt = 6 pc.

## Name uniqueness

- A `Name` must be unique within the namespace of its item; that namespace is the innermost containing object that has a name ([RDL overview][ov]).
- Identifiers are CLS-compliant: two names are distinct only if they differ by more than case ([MS-RDL glossary][gl]).
- The validator checks data sources, datasets, report parameters, and report items across the whole report (RDL010).

## Expression collections

RDL expressions are Visual Basic expressions starting with `=`. The validator never evaluates them; it only scans for references.

| Collection | Example | Checked by |
|---|---|---|
| `Fields!` | `=Fields!Total.Value` | RDL021 |
| `Parameters!` | `=Parameters!Year.Value` | RDL020, RDL022 |
| `Globals!` | `=Globals!PageNumber` | not checked |
| `User!` | `=User!UserID` | not checked |
| `ReportItems!` | `=ReportItems!Textbox1.Value` | not checked |
| `Variables!` | `=Variables!MyVar.Value` | not checked |

The collection names are unverified background knowledge; the Microsoft page "Built-in collections in expressions" was not fetched for this reference.

## Companion file shapes

- `.rds` (legacy shared data source): root `RptDataSource` with `Name` and `ConnectionProperties/Extension`, `ConnectionProperties/ConnectString`, optional `IntegratedSecurity` and `Prompt`. RDL060 follows what the ReportingServicesTools upload function requires ([Write-RsCatalogItem.ps1][rsc]).
- `.rsds` (shared data source): root `DataSourceDefinition` with `Extension` and `ConnectString`. RDL061 follows the same tool and the server API property names ([DataSourceDefinition][dsd]). The exact `.rsds` file layout is not specified in any Microsoft schema that was fetched (unverified).
- `.rsd` (shared dataset): namespace `http://schemas.microsoft.com/sqlserver/reporting/2010/01/shareddatasetdefinition`. A typical root is `SharedDataSet` holding `DataSet` with `Query` and `Fields`; the nesting is unverified because no sample was fetched. The validator only uses `.rsd` file names to resolve RDL062 and does not validate their content.
- Tool mapping: `.rdl` Report, `.rsds` and `.rds` DataSource, `.rsd` DataSet ([Get-ItemType.ps1][git]).

## Right-to-left reports

For Arabic, Hebrew, Persian and Urdu reports, set these properties deliberately.

### Style/Direction

- Values: `Default` (same as LTR), `LTR`, `RTL`, or an expression returning one of them. Absent means Default ([Style.Direction][dir]).
- It is honored only when the grandparent of `Style` is `TextRun`, `Subreport`, `Chart`, `LinearGauge` or `RadialGauge`; elsewhere it is ignored (RDL051).
- It does not change text alignment unless the peer `Style/TextAlign` is `General`. Set `TextAlign` to `General` if alignment must follow direction.
- The XSD type is a plain string, so a typo such as `Rtl` passes the schema (RDL050 catches it).
- Direction can be driven by an expression (for example from a dataset field) in SSRS 2012 and later ([SQLServerCentral thread][ssc], community source).

### Digits: NumeralVariant and NumeralLanguage

- `Style/NumeralVariant` is an integer 1 to 7 or an expression ([Style.NumeralVariant][nv]).
- 1 follows Unicode context rules (default). 2 forces `0123456789`. 3 gives the traditional digits of the script and applies to ar, bn, bo, fa, gu, hi, kn, kok, lo, mr, ms, or, pa, sa, ta, te, th, ur. 4, 5, 6 apply to ko, ja, zh-CHS, zh-CHT (6 is wide digits). 7 applies to ko only.
- `Style/NumeralLanguage` takes a culture code; when absent it falls back to the peer `Style/Language` ([Style.NumeralLanguage][nl]). Both are ignored unless the grandparent is `TextRun`, `Textbox`, `Chart`, `LinearGauge` or `RadialGauge`.
- `Report/Language` and `Style/Language` take a culture code such as `ar-SA`; the value must be a specific culture or a neutral language with a .NET default ([RDL overview][ov]).

### Tablix LayoutDirection

- `Tablix/LayoutDirection` is `LTR` or `RTL` ([2016/01 XSD][xsd]).
- RTL grows dynamic columns right to left, places headers on the right and reverses the order of peer groups ([2008 docs][ld]).
- It reorders only the table's columns. Excel export keeps the default sheet direction ([Microsoft Q&A][xl]).
- Hiding columns by expression can misalign RTL tables; the cited workaround was a separate RTL report ([Dynamics AX BI blog][axbi]).

### Calendar

`Style/Calendar` values (Gregorian, Hijri, UmAlQura and others) are not covered by any validator rule and the value list is unverified here. Check the MS-RDL `Style.Calendar` page before relying on a value.

## Link references

[ns]: https://learn.microsoft.com/en-us/openspecs/sql_server_protocols/MS-RDL/6f0bcdd5-0a38-4a38-a8fa-05eb8249f59a
[ver]: https://learn.microsoft.com/en-us/sql/reporting-services/reports/find-the-report-definition-schema-version-ssrs
[rep]: https://learn.microsoft.com/en-us/openspecs/sql_server_protocols/ms-rdl/6bbaafec-020b-406c-b4e7-5e4318b616cb
[xsd]: https://learn.microsoft.com/en-us/openspecs/sql_server_protocols/ms-rdl/52ce3983-2bfc-4e72-9359-42aaf5fe4509
[cp]: https://learn.microsoft.com/en-us/openspecs/sql_server_protocols/ms-rdl/66ba68b2-3d03-443a-bcc1-4cf0f53012a5
[ov]: https://learn.microsoft.com/en-us/sql/reporting-services/reports/report-definition-language-ssrs
[gl]: https://learn.microsoft.com/en-us/openspecs/sql_server_protocols/ms-rdl/b2482b3f-74ab-4ca8-a9e5-c07955011743
[dir]: https://learn.microsoft.com/en-us/openspecs/sql_server_protocols/MS-RDL/4c0efe27-0fb0-43ca-a3c1-d37cd7fb4c72
[nl]: https://learn.microsoft.com/en-us/openspecs/sql_server_protocols/MS-RDL/bf896159-675f-417b-b221-a0d590cbef25
[nv]: https://learn.microsoft.com/en-us/openspecs/sql_server_protocols/ms-rdl/e1b67670-1195-48a5-afd8-033107befe20
[ld]: https://learn.microsoft.com/en-us/previous-versions/sql/sql-server-2008/ms155126(v=sql.100)
[xl]: https://learn.microsoft.com/en-us/answers/questions/1091489/ssrs-export-to-excel-ignores-default-sheet-directi
[axbi]: https://learn.microsoft.com/en-us/archive/blogs/dynamicsaxbi/known-issue-dynamic-precision-designs-spacing-issues-in-rtl-languages
[ssc]: https://www.sqlservercentral.com/?p=1778239
[rsc]: https://raw.githubusercontent.com/microsoft/ReportingServicesTools/master/ReportingServicesTools/Functions/CatalogItems/Write-RsCatalogItem.ps1
[git]: https://raw.githubusercontent.com/microsoft/ReportingServicesTools/master/ReportingServicesTools/Functions/Common/Get-ItemType.ps1
[dsd]: https://learn.microsoft.com/en-us/dotnet/api/reportservice2010.datasourcedefinition.connectstring
