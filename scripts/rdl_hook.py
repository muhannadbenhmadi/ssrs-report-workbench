"""PostToolUse hook: advisory offline validation of edited RDL/RDS/RSDS files.

Reads the hook JSON from stdin, prints additionalContext JSON when an SSRS file
was written or edited. Never blocks: always exits 0, prints nothing on any error.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RDL_SUFFIXES = {".rdl", ".rds", ".rsds"}
MAX_CONTEXT = 4000
MAX_FINDINGS = 15
SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
KNOWN_REASONS = {"oversize", "symlink", "unreadable", "no-candidates"}
# Only fixed vocabulary reaches the model: rule ids, severities, counts, catalog titles and
# structural locations with every Name value removed. No text from the edited file is echoed.
_NAME_SEG = re.compile(r"\[@Name='[^']*'\]")
_SEGMENT_OK = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,40}$")
_RULE_OK = re.compile(r"^RDL\d{3}$")
MAX_SEGMENTS = 14
# Closed vocabulary of element names that may appear in a reported location. Any other segment,
# including ones forged through quote or bracket tricks in a Name attribute, is replaced by "?".
KNOWN_ELEMENTS = frozenset("""
Report ReportSections ReportSection Body ReportItems Textbox Tablix Rectangle Image Line Subreport
Chart GaugePanel Map CustomReportItem Paragraphs Paragraph TextRuns TextRun Value Style Direction
NumeralVariant NumeralLanguage LayoutDirection DataSources DataSource ConnectionProperties
ConnectString DataSets DataSet Query DataSourceName CommandText Fields Field ReportParameters
ReportParameter DataType DefaultValue Values QueryParameters QueryParameter Width Height Top Left
Page PageWidth PageHeight LeftMargin RightMargin TopMargin BottomMargin InteractiveWidth
InteractiveHeight Language Filters Filter FilterExpression FilterValues FilterValue Visibility
Hidden TablixBody TablixRows TablixRow TablixCells TablixCell CellContents TablixColumnHierarchy
TablixRowHierarchy TablixMembers TablixMember TablixHeader Group GroupExpressions GroupExpression
SortExpressions SortExpression PageHeader PageFooter DataSourceReference SharedDataSetReference
SharedDataSet RptDataSource DataSourceDefinition Extension Name ValidValues DataSetReference
DataSetName ParameterValues ParameterValue Label Code Variables Variable EmbeddedImages
EmbeddedImage ChartData ChartSeriesCollection ChartSeries ChartDataPoints ChartDataPoint
ChartDataPointValues ChartCategoryHierarchy ChartMembers ChartMember ChartTitle Caption ToolTip
Action Hyperlink Drillthrough Parameters Parameter MapLayers LinearGauges LinearGauge
RadialGauges RadialGauge Prompt
""".split())
NOTE = "(File names, element names and messages are omitted here on purpose. Run the validate-rdl skill for details.)"


def _rule_title(rule: str, rules: dict) -> str:
    return rules[rule]["title"] if rule in rules else "unknown rule"


def _location(raw: object) -> str:
    text = _NAME_SEG.sub("", str(raw))
    segments = [seg for seg in text.split("/") if seg][:MAX_SEGMENTS]
    if not segments:
        return "<root>"
    return "/".join(seg if _SEGMENT_OK.match(seg) and seg in KNOWN_ELEMENTS else "?" for seg in segments)


def _resolve(payload: dict) -> Path | None:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw = tool_input.get("file_path")
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = Path(raw)
    if path.suffix.lower() not in RDL_SUFFIXES:
        return None
    if not path.is_absolute():
        cwd = payload.get("cwd")
        path = (Path(cwd) if isinstance(cwd, str) and cwd else Path.cwd()) / path
    return path if path.is_file() else None


def build_context(payload: dict) -> str | None:
    from scripts.rdl_validate import RULES, validate_single

    path = _resolve(payload)
    if path is None:
        return None
    doc = validate_single(path)
    summary = doc["summary"]
    status = doc["status"] if doc["status"] in ("PASS", "FAIL", "INCOMPLETE") else "FAIL"
    counts = tuple(int(summary.get(k, 0)) for k in ("errors", "warnings", "info"))
    lines = [f"SSRS Report Workbench rdl-validate: the edited file -> {status} "
             f"({counts[0]} errors, {counts[1]} warnings, {counts[2]} info)", NOTE]
    findings = list(doc["files"][0]["findings"]) if doc["files"] else []
    findings.sort(key=lambda f: SEVERITY_ORDER.get(f.get("severity"), 3))
    for f in findings[:MAX_FINDINGS]:
        severity = f.get("severity") if f.get("severity") in SEVERITY_ORDER else "unknown"
        rule = f.get("rule") if _RULE_OK.match(str(f.get("rule", ""))) else "RDL000"
        lines.append(f"- {severity} {rule} at {_location(f.get('location', ''))}: {_rule_title(rule, RULES)}")
    if len(findings) > MAX_FINDINGS:
        lines.append(f"({len(findings) - MAX_FINDINGS} more findings omitted)")
    for w in doc.get("warnings", []):
        reason = w.get("reason") if w.get("reason") in KNOWN_REASONS else "skipped"
        lines.append(f"- warning file {reason}")
    footer = "Run the ssrs-report-workbench validate-rdl skill on this file for locations, messages and fixes."
    body = "\n".join(lines)
    room = MAX_CONTEXT - len(footer) - 1
    if len(body) > room:
        body = body[: room - 3].rstrip() + "..."
    return body + "\n" + footer


def run(stdin_text: str) -> str:
    try:
        payload = json.loads(stdin_text)
        if not isinstance(payload, dict):
            return ""
        text = build_context(payload)
        if not text:
            return ""
        return json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                                  "additionalContext": text}})
    except Exception:
        return ""


def main() -> int:
    try:
        out = run(sys.stdin.read())
        if out:
            sys.stdout.write(out + "\n")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
