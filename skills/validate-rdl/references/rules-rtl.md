# Rule reference - right-to-left and mixed direction

Part of the rule reference; the other rules are in [rules.md](rules.md). Same conventions: `error` makes a file FAIL, `warning` and `info` never do, and a rule marked derived or heuristic is this plugin's judgement, not a Microsoft requirement.

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

### RDL055 — TextRun joins right-to-left text with text that may be left-to-right
- Severity: warning when the file itself shows the mix or makes it likely; info when it is only possible
- What it checks: Warning: a literal `Value` with right-to-left and Latin letters in one `TextRun`; or an expression where a right-to-left string literal is concatenated (`&`, `+`) and the expression reads a `ReportParameter` of type String or `User!`. Info: the same join when the expression reads only `Fields!`. Not flagged: a literal that is not concatenated (`IIf(x, "نعم", "لا")`), joins with `Globals!` or non-String parameters only, and any run holding a direction mark, typed or as `ChrW(8206)`, `ChrW(8207)`, `ChrW(8234)`..`ChrW(8238)`, `ChrW(8294)`..`ChrW(8297)` (decimal or `&H`). The mark's placement is not checked. Run-time values are never read.
- Why it matters: A `TextRun` has one base direction. The Unicode bidirectional algorithm reorders the other-direction part and the neutral characters beside it (spaces, dashes, brackets), so a key, a code, an account name or a group of numbers can appear moved or in a different visual order.
- Typical fix: Give the value its own `Textbox` or `TextRun` with `Direction` LTR, or wrap it in the expression, for example `ChrW(8234) & value & ChrW(8236)`. Then preview the report: this plugin does not render, and the wrap is not verified per renderer.
- Basis: [Unicode UAX #9][uax9]; heuristic (derived; not an MS-RDL rule).

## Link references

[dir]: https://learn.microsoft.com/en-us/openspecs/sql_server_protocols/MS-RDL/4c0efe27-0fb0-43ca-a3c1-d37cd7fb4c72
[nv]: https://learn.microsoft.com/en-us/openspecs/sql_server_protocols/ms-rdl/e1b67670-1195-48a5-afd8-033107befe20
[xsd]: https://learn.microsoft.com/en-us/openspecs/sql_server_protocols/ms-rdl/52ce3983-2bfc-4e72-9359-42aaf5fe4509
[ld]: https://learn.microsoft.com/en-us/previous-versions/sql/sql-server-2008/ms155126(v=sql.100)
[xl]: https://learn.microsoft.com/en-us/answers/questions/1091489/ssrs-export-to-excel-ignores-default-sheet-directi
[uax9]: https://www.unicode.org/reports/tr9/
