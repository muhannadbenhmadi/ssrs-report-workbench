#!/usr/bin/env python3
"""Offline, read-only static validator for SSRS .rdl, .rds and .rsds files.

Structural and cross-reference checks only: expressions are never evaluated and a clean
result means "no rule fired", not "the report deploys or renders".
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

if __package__ in (None, ""):  # allow `python scripts/rdl_validate.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.discovery import MAX_FILE_SIZE, SKIP_DIRS  # noqa: E402

_BASE = "http://schemas.microsoft.com/sqlserver/reporting/"
RDL_NAMESPACES: dict[str, str] = {
    _BASE + "2008/01/reportdefinition": "2008/01",
    _BASE + "2010/01/reportdefinition": "2010/01",
    _BASE + "2016/01/reportdefinition": "2016/01",
}
LEGACY_NAMESPACES: dict[str, str] = {
    _BASE + "2003/10/reportdefinition": "2003/10",
    _BASE + "2005/01/reportdefinition": "2005/01",
}
SIZE_UNITS = {"cm": 1 / 2.54, "mm": 1 / 25.4, "in": 1.0, "pt": 1 / 72, "pc": 1 / 6}
MAX_SIZE_INCHES = 160.0
MAX_FILES = 10000
TOOL = "ssrs-report-workbench-rdl-validator"
_MSRDL = "MS-RDL (learn.microsoft.com/openspecs/sql_server_protocols/ms-rdl)"


def _rule(title: str, severity: str, basis: str) -> dict[str, str]:
    return {"title": title, "severity": severity, "basis": basis}


RULES: dict[str, dict[str, str]] = {
    "RDL001": _rule("File is well-formed XML with no DTD or entity declaration", "error", "XML; safety"),
    "RDL002": _rule("Root is Report in a supported namespace (legacy namespaces warn)", "error", _MSRDL + " 1.3.3.1"),
    "RDL003": _rule("Version-specific required structure is present", "error", _MSRDL + " Report; 2016/01 XSD"),
    "RDL010": _rule("Names are unique within their scope (exact duplicate is an error, case-only a warning)", "error", "RDL overview; " + _MSRDL + " glossary"),
    "RDL011": _rule("DataSet Query/DataSourceName names an existing DataSource", "error", "2016/01 XSD + logic"),
    "RDL012": _rule("DataSet has non-empty Query/CommandText unless it is shared", "error", "2016/01 XSD"),
    "RDL013": _rule("DataSource has not both ConnectionProperties and DataSourceReference", "error", _MSRDL + " DataSource.ConnectionProperties"),
    "RDL014": _rule("ReportParameter DataType is a valid RDL type", "error", "2016/01 XSD"),
    "RDL015": _rule("2016/01 ReportParametersLayout grid holds exactly one cell per ReportParameter", "error", "Report Builder publishing error (observed)"),
    "RDL020": _rule("Parameters!X references a defined ReportParameter", "error", "logic"),
    "RDL021": _rule("Fields!X references a Field of the in-scope dataset", "warning", "logic, scope-dependent"),
    "RDL022": _rule("ReportParameter is referenced by some expression", "info", "logic"),
    "RDL023": _rule("Caller parameter set matches the declared ReportParameters (opt-in, --expect-params)", "error", "URL access logic (observed)"),
    "RDL030": _rule("Size values are <number><unit> and at most 160in", "error", "RDL overview (Size type)"),
    "RDL031": _rule("Section width plus margins fits the page width", "warning", "layout logic (derived)"),
    "RDL040": _rule("ConnectString embeds credentials (value never shown)", "warning", "security smell"),
    "RDL050": _rule("Style/Direction is Default, LTR, RTL or an expression", "error", _MSRDL + " Style.Direction"),
    "RDL051": _rule("Style/Direction is set where it is ignored", "info", _MSRDL + " Style.Direction"),
    "RDL052": _rule("Style/NumeralVariant is an integer 1..7 or an expression", "error", _MSRDL + " Style.NumeralVariant"),
    "RDL053": _rule("Tablix/LayoutDirection is LTR or RTL", "error", "2016/01 XSD"),
    "RDL054": _rule("RTL-language report declares no RTL direction (readiness hint)", "info", "heuristic (derived)"),
    "RDL055": _rule("TextRun joins right-to-left text with text that may be left-to-right, with no direction mark", "warning", "Unicode UAX #9; heuristic (derived)"),
    "RDL060": _rule(".rds has RptDataSource with Name, Extension and ConnectString", "error", "ReportingServicesTools Write-RsCatalogItem.ps1"),
    "RDL061": _rule(".rsds has DataSourceDefinition with Extension and ConnectString", "error", "ReportingServicesTools Write-RsCatalogItem.ps1"),
    "RDL062": _rule("Shared data source/dataset reference resolves to a file in the scanned root", "warning", "deploy logic (derived)"),
    "RDL070": _rule("Static TablixMembers kept with a dynamic member share one RepeatOnNewPage value", "error", "Report Builder publishing error (observed)"),
}

ITEM_TAGS = {"Textbox", "Tablix", "Rectangle", "Image", "Line", "Subreport", "Chart",
             "GaugePanel", "Map", "CustomReportItem"}
SIZE_TAGS = {"Width", "Height", "Top", "Left", "PageWidth", "PageHeight", "LeftMargin", "RightMargin",
             "TopMargin", "BottomMargin", "InteractiveWidth", "InteractiveHeight"}
# Inside these items Left/Top/Width/Height of nested parts are percentages, not Size values.
PERCENT_CONTAINERS = {"GaugePanel", "Map", "Chart"}
DATA_TYPES = {"Boolean", "DateTime", "Integer", "Float", "String"}
DIRECTIONS = {"Default", "LTR", "RTL"}
DIRECTION_HOSTS = {"TextRun", "Subreport", "Chart", "LinearGauge", "RadialGauge"}
RTL_LANGS = {"ar", "he", "fa", "ur"}
FIELD_RE = re.compile(r"Fields!([A-Za-z_][A-Za-z0-9_]*)")
PARAM_RE = re.compile(r"Parameters!([A-Za-z_][A-Za-z0-9_]*)")
# VB string literal: double-quoted, with "" as the escaped quote. Removed before reference matching.
VB_STRING_RE = re.compile(r'"[^"]*(?:""[^"]*)*"')  # unrolled: linear, no alternation per char
QUERY_PARAM_RE = re.compile(r"@([A-Za-z_][A-Za-z0-9_]*)")
STATUS_EXIT = {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2}
CRED_RE = re.compile(r"(?i)\b(password|pwd|user id|uid)\s*=")
RTL_CHAR_RE = re.compile(r"[\u0590-\u08ff\ufb1d-\ufdff\ufe70-\ufefc]")  # Hebrew, Arabic and their presentation forms
LATIN_RE = re.compile(r"[A-Za-z]")
# An explicit direction mark, typed or built with ChrW(8206) / ChrW(&H200E): LRM, RLM, embeddings, overrides, isolates.
BIDI_MARK_RE = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]"
                          r"|ChrW\(\s*(?:820[67]|823[4-8]|829[4-7]|&H(?:200[EF]|202[A-E]|206[6-9]))\s*\)", re.I)
USER_RE = re.compile(r"\bUser!", re.I)
SIZE_RE = re.compile(r"^\s*(-?(?:\d+(?:\.\d+)?|\.\d+))\s*(cm|mm|in|pt|pc)\s*$")


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    location: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"rule": self.rule, "severity": self.severity,
                "location": self.location, "message": self.message}


def strip_vb_strings(expression: str) -> str:
    """Replace every VB string literal with "" so text inside quotes is never read as a reference."""
    return VB_STRING_RE.sub('""', expression)


def parse_size(value: str) -> float | None:
    """Return inches for '<number><unit>', else None. Callers skip values starting with '='."""
    m = SIZE_RE.match(value or "")
    return float(m.group(1)) * SIZE_UNITS[m.group(2)] if m else None


def _ln(el: ET.Element) -> str:
    tag = el.tag if isinstance(el.tag, str) else ""
    return tag.rsplit("}", 1)[-1]


def _uri(el: ET.Element) -> str:
    tag = el.tag if isinstance(el.tag, str) else ""
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else ""


def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None else ""


def _kid(el: ET.Element, name: str) -> ET.Element | None:
    return next((c for c in el if _ln(c) == name), None)


def _kids(el: ET.Element, name: str) -> list[ET.Element]:
    return [c for c in el if _ln(c) == name]


def _parse(data: bytes) -> tuple[ET.Element | None, Finding | None]:
    lowered = data.lower()
    probe = lowered + b"\n" + lowered.replace(b"\x00", b"")  # also catches UTF-16 payloads
    if b"<!doctype" in probe or b"<!entity" in probe:
        return None, Finding("RDL001", "error", "/", "DTD or entity declarations are not allowed in RDL")
    try:
        return ET.fromstring(data), None
    except ET.ParseError as exc:
        return None, Finding("RDL001", "error", "/", f"Not well-formed XML: {exc}")


def _credential_finding(el: ET.Element, location: str) -> Finding | None:
    keys = sorted({m.group(1).lower() for m in CRED_RE.finditer(el.text or "")})
    if not keys:
        return None
    return Finding("RDL040", "warning", location,
                   f"ConnectString contains credential key(s): {', '.join(keys)} (value not shown)")


def validate_rdl_bytes(data: bytes, *, project_stems: set[str] | None = None,
                       expect_params: list[str] | None = None) -> tuple[dict, list[Finding]]:
    meta: dict[str, Any] = {"namespace": None, "rdl_version": None}
    root, err = _parse(data)
    if err or root is None:
        return meta, [err] if err else []
    uri = _uri(root)
    meta["namespace"] = uri or None
    version = RDL_NAMESPACES.get(uri) or LEGACY_NAMESPACES.get(uri)
    meta["rdl_version"] = version
    if _ln(root) != "Report":
        return meta, [Finding("RDL002", "error", _ln(root) or "/", f"Root element is '{_ln(root)}', expected 'Report'")]
    if version is None:
        return meta, [Finding("RDL002", "error", "Report", f"Unsupported or missing namespace '{uri}'")]
    if uri in LEGACY_NAMESPACES:
        return meta, [Finding("RDL002", "warning", "Report",
                              f"Legacy namespace {version}; upgrade in Report Designer (structural rules skipped)")]

    parents = {c: p for p in root.iter() for c in p}
    findings: list[Finding] = []

    def loc(el: ET.Element) -> str:
        parts = []
        cur: ET.Element | None = el
        while cur is not None:
            name = cur.get("Name")
            parts.append(f"{_ln(cur)}[@Name='{name}']" if name else _ln(cur))
            cur = parents.get(cur)
        return "/".join(reversed(parts))

    def add(rule: str, severity: str, el: ET.Element, message: str) -> None:
        findings.append(Finding(rule, severity, loc(el), message))

    def add_f(f: Finding | None) -> None:
        if f:
            findings.append(f)

    elems = [e for e in root.iter() if _uri(e) == uri]  # skips designer (rd:) elements
    by_tag: dict[str, list[ET.Element]] = {}
    for e in elems:
        by_tag.setdefault(_ln(e), []).append(e)

    _check_structure(root, version, add)
    _check_names(by_tag, add)
    sources = {d.get("Name", "").lower(): d.get("Name", "") for d in by_tag.get("DataSource", []) if d.get("Name")}
    _check_datasets_sources(by_tag, sources, add)
    params = {p.get("Name", "").lower(): p for p in by_tag.get("ReportParameter", [])}
    _check_expressions(root, elems, by_tag, parents, params, add)
    _check_parameter_layout(root, version, by_tag, add)
    if expect_params is not None:
        _check_caller_params(root, by_tag, expect_params, add)
    _check_repeat_on_new_page(by_tag, add)
    _check_sizes(root, version, by_tag, parents, add)
    for e in by_tag.get("ConnectString", []):
        add_f(_credential_finding(e, loc(e)))
    _check_rtl(root, by_tag, parents, add)
    _check_mixed_direction(by_tag, params, add)
    # Only meaningful when the scanned root actually holds shared files; otherwise the references
    # most likely point at items that live on the report server.
    if project_stems:
        for tag in ("DataSourceReference", "SharedDataSetReference"):
            for e in by_tag.get(tag, []):
                ref = _text(e)
                if not ref or ref.startswith("="):
                    continue
                name = PurePosixPath(ref.replace("\\", "/")).name.lower()
                stem = PurePosixPath(ref.replace("\\", "/")).stem.lower()
                if name not in project_stems and stem not in project_stems:
                    add("RDL062", "warning", e,
                        f"{tag} '{ref}' does not match any .rds/.rsds/.rsd file in the scanned root")
    return meta, findings


Adder = Callable[[str, str, ET.Element, str], None]


def _check_structure(root: ET.Element, version: str, add: Adder) -> None:
    if version == "2008/01":
        for name in ("Body", "Page", "Width"):
            if _kid(root, name) is None:
                add("RDL003", "error", root, f"2008/01 Report requires a direct '{name}' child")
        return
    sections = _kid(root, "ReportSections")
    secs = _kids(sections, "ReportSection") if sections is not None else []
    if not secs:
        add("RDL003", "error", root, f"{version} Report requires ReportSections/ReportSection")
    for sec in secs:
        body = _kid(sec, "Body")
        if body is None or _kid(body, "Height") is None:
            add("RDL003", "error", sec, "ReportSection requires Body with a Height")
        for name in ("Width", "Page"):
            if _kid(sec, name) is None:
                add("RDL003", "error", sec, f"ReportSection requires a '{name}' child")


def _check_names(by_tag: dict[str, list[ET.Element]], add: Adder) -> None:
    groups = {"DataSource": ["DataSource"], "DataSet": ["DataSet"],
              "ReportParameter": ["ReportParameter"], "report item": sorted(ITEM_TAGS)}
    for label, tags in groups.items():
        seen: dict[str, str] = {}
        for tag in tags:
            for e in by_tag.get(tag, []):
                name = e.get("Name")
                if not name:
                    continue
                key = name.lower()
                if key in seen and seen[key] == name:
                    add("RDL010", "error", e, f"Duplicate {label} name '{name}'")
                elif key in seen:
                    # Designer-saved Microsoft reports exist with names differing only by case, so this
                    # is a warning: expressions compare identifiers case-insensitively and may be ambiguous.
                    add("RDL010", "warning", e,
                        f"{label} name '{name}' differs only by case from '{seen[key]}'")
                else:
                    seen[key] = name


def _check_datasets_sources(by_tag: dict[str, list[ET.Element]], sources: dict[str, str], add: Adder) -> None:
    for ds in by_tag.get("DataSource", []):
        if _kid(ds, "ConnectionProperties") is not None and _kid(ds, "DataSourceReference") is not None:
            add("RDL013", "error", ds, "DataSource has both ConnectionProperties and DataSourceReference")
    for p in by_tag.get("ReportParameter", []):
        dtype = _text(_kid(p, "DataType"))
        if dtype not in DATA_TYPES:
            add("RDL014", "error", p, f"DataType '{dtype}' is not one of {', '.join(sorted(DATA_TYPES))}")
    for ds in by_tag.get("DataSet", []):
        query = _kid(ds, "Query")
        shared = _kid(ds, "SharedDataSet") is not None
        if not shared and not _text(_kid(query, "CommandText") if query is not None else None):
            add("RDL012", "error", ds, "DataSet has no Query/CommandText and is not a SharedDataSet")
        if query is None:
            continue
        name_el = _kid(query, "DataSourceName")
        ref = _text(name_el)
        if not ref:
            if not shared:
                add("RDL011", "error", name_el if name_el is not None else query,
                    "Embedded DataSet Query has a missing or empty DataSourceName")
            continue
        if not ref.startswith("=") and ref.lower() not in sources:
            known = ", ".join(sorted(sources.values())) or "none"
            add("RDL011", "error", name_el, f"DataSourceName '{ref}' does not match any DataSource (known: {known})")


def _fields_of(dataset: ET.Element) -> set[str]:
    return {f.get("Name", "").lower() for f in dataset.iter() if _ln(f) == "Field"}


def _check_expressions(root, elems, by_tag, parents, params, add: Adder) -> None:
    datasets = {d.get("Name", "").lower(): d for d in by_tag.get("DataSet", [])}
    fields_by_dataset = {key: _fields_of(d) for key, d in datasets.items()}
    used: set[str] = set()
    # "@Name" inside query text is the usual way a parameter feeds a query, with or without an
    # explicit QueryParameters mapping, so it counts as a use. Whole tokens only (@Year != @YearEnd).
    query_params = {m.group(1).lower() for c in by_tag.get("CommandText", [])
                    for m in QUERY_PARAM_RE.finditer(_text(c))}
    for e in elems:
        raw = _text(e)
        if not raw.startswith("="):
            continue
        text = strip_vb_strings(raw)
        for m in PARAM_RE.finditer(text):
            used.add(m.group(1).lower())
            if m.group(1).lower() not in params:
                add("RDL020", "error", e, f"Parameters!{m.group(1)} does not match any ReportParameter")
        names = FIELD_RE.findall(text)
        if not names:
            continue
        # Aggregates and lookups name their scope as a string literal: First(Fields!X.Value, "Other").
        # Any literal that matches a dataset name widens the set of datasets the fields may come from.
        scope = _scope_dataset(e, parents, datasets)
        keys = dict.fromkeys(([scope.get("Name", "").lower()] if scope is not None else [])
                             + [lit[1:-1].lower() for lit in VB_STRING_RE.findall(raw)])
        candidates = [k for k in keys if k in datasets]  # deduped, in order of appearance
        if not candidates:
            continue
        fields = set().union(*(fields_by_dataset[k] for k in candidates))
        label = "', '".join(datasets[k].get("Name", "") for k in candidates)
        for n in names:
            if n.lower() not in fields:
                add("RDL021", "warning", e, f"Fields!{n} is not a field of dataset '{label}'")
    for key, p in params.items():
        if key and key not in used and key not in query_params:
            add("RDL022", "info", p, f"ReportParameter '{p.get('Name')}' is never referenced by an expression or query")


def _scope_dataset(el, parents, datasets):
    cur = el
    while cur is not None:
        if _ln(cur) == "DataSet":
            return cur
        name_el = _kid(cur, "DataSetName")
        if name_el is not None:
            return datasets.get(_text(name_el).lower())
        cur = parents.get(cur)
    return next(iter(datasets.values())) if len(datasets) == 1 else None


def _int(el: ET.Element | None) -> int | None:
    text = _text(el)
    return int(text) if text.isascii() and text.isdigit() else None  # isdigit alone accepts non-ASCII digits int() rejects


def _check_parameter_layout(root, version, by_tag, add: Adder) -> None:
    """RDL015. Report Builder: "The number of defined parameters is not equal to the number of cell
    definitions in the parameter panel" - raised also when the layout is absent (0 cells)."""
    params = by_tag.get("ReportParameter", [])
    layout = _kid(root, "ReportParametersLayout")
    if version != "2016/01" or (not params and layout is None):
        return
    grid = _kid(layout, "GridLayoutDefinition") if layout is not None else None
    if grid is None:
        add("RDL015", "error", root if layout is None else layout,
            f"{len(params)} ReportParameter(s) but no ReportParametersLayout/GridLayoutDefinition")
        return
    cells = by_tag.get("CellDefinition", [])
    if len(cells) != len(params):
        add("RDL015", "error", grid, f"{len(params)} ReportParameter(s) but {len(cells)} CellDefinition(s)")
    limits = {}
    for tag in ("NumberOfColumns", "NumberOfRows"):
        limits[tag] = _int(_kid(grid, tag))
        if limits[tag] is None:
            add("RDL015", "error", grid, f"GridLayoutDefinition/{tag} is missing or not a non-negative integer")
    declared = {p.get("Name", "").lower() for p in params}
    seen_names: set[str] = set()
    seen_slots: set[tuple[int, int]] = set()
    for cell in cells:
        name = _text(_kid(cell, "ParameterName"))
        if name.lower() not in declared:
            add("RDL015", "error", cell, f"CellDefinition names '{name}', which is not a ReportParameter")
        elif name.lower() in seen_names:
            add("RDL015", "error", cell, f"ReportParameter '{name}' has more than one CellDefinition")
        seen_names.add(name.lower())
        slot = []
        for tag, limit in (("ColumnIndex", limits["NumberOfColumns"]), ("RowIndex", limits["NumberOfRows"])):
            el = _kid(cell, tag)
            index = 0 if el is None else _int(el)  # an omitted index is read as 0
            if index is None:
                add("RDL015", "error", cell, f"Cell '{name}': {tag} '{_text(el)}' is not a non-negative integer")
            elif limit is not None and index >= limit:
                add("RDL015", "error", cell, f"Cell '{name}': {tag} {index} is outside the grid (size {limit})")
            slot.append(index)
        if None not in slot:
            if tuple(slot) in seen_slots:
                add("RDL015", "error", cell, f"Cell '{name}' shares column {slot[0]}, row {slot[1]} with another cell")
            seen_slots.add(tuple(slot))
    for p in params:
        if p.get("Name", "").lower() not in seen_names:
            add("RDL015", "error", p, f"ReportParameter '{p.get('Name')}' has no CellDefinition in the parameter panel")


def _check_caller_params(root, by_tag, expected: list[str], add: Adder) -> None:
    """RDL023. Names are compared exactly: URL-access report parameter names are case-sensitive."""
    params = by_tag.get("ReportParameter", [])
    declared = {p.get("Name", "") for p in params}
    for name in dict.fromkeys(expected):
        if name not in declared:
            add("RDL023", "error", root, f"Caller sends parameter '{name}', which the report does not declare")
    for p in params:
        if p.get("Name", "") not in expected and _kid(p, "DefaultValue") is None:
            add("RDL023", "warning", p,
                f"ReportParameter '{p.get('Name')}' has no DefaultValue and is not in the caller's parameter list")


def _check_repeat_on_new_page(by_tag, add: Adder) -> None:
    """RDL070. Report Builder: TablixMembers kept with a dynamic member "must have the same value set
    for the RepeatOnNewPage property as those following or preceding the dynamic TablixMember"."""
    def repeats(member: ET.Element) -> bool:
        return _text(_kid(member, "RepeatOnNewPage")).lower() == "true"  # absent means false

    for holder in by_tag.get("TablixMembers", []):
        members = _kids(holder, "TablixMember")
        for i, member in enumerate(members):
            group = _kid(member, "Group")
            if group is None:
                continue
            # Static siblings bound to this group: KeepWithGroup=After just before it, =Before just after it.
            for keep, indexes in (("After", range(i - 1, -1, -1)), ("Before", range(i + 1, len(members)))):
                expected = None
                for j in indexes:
                    other = members[j]
                    if _kid(other, "Group") is not None or _text(_kid(other, "KeepWithGroup")) != keep:
                        break
                    if expected is None:
                        expected = repeats(other)  # the member next to the group sets the expected value
                    elif repeats(other) != expected:
                        add("RDL070", "error", other,
                            f"TablixMember {j + 1} (KeepWithGroup={keep}) has RepeatOnNewPage {repeats(other)} but the "
                            f"members kept with group '{group.get('Name', '')}' have {expected}")


def _check_sizes(root, version, by_tag, parents, add: Adder) -> None:
    for tag in SIZE_TAGS:
        for e in by_tag.get(tag, []):
            text = _text(e)
            if text.startswith("="):
                continue
            anc = parents.get(e)
            while anc is not None and _ln(anc) not in PERCENT_CONTAINERS:
                anc = parents.get(anc)
            if anc is not None and parents.get(e) is not anc:
                continue  # nested gauge/map/chart part: percentage, not a Size
            inches = parse_size(text)
            if inches is None:
                add("RDL030", "error", e, f"'{_ln(e)}' value '{text}' is not <number><unit> (cm, mm, in, pt, pc)")
            elif inches > MAX_SIZE_INCHES:
                add("RDL030", "error", e, f"'{_ln(e)}' value '{text}' exceeds {MAX_SIZE_INCHES:g}in")
            elif inches < 0:
                add("RDL030", "error", e, f"'{_ln(e)}' value '{text}' is negative (Size minimum is 0in)")
    pairs = ([(root, _kid(root, "Page"))] if version == "2008/01"
             else [(s, _kid(s, "Page")) for s in by_tag.get("ReportSection", [])])
    for holder, page in pairs:
        if page is None:
            continue
        vals = [parse_size(_text(_kid(holder, "Width"))), parse_size(_text(_kid(page, "PageWidth")))]
        margins = []
        for m in ("LeftMargin", "RightMargin"):
            el = _kid(page, m)
            margins.append(0.0 if el is None else parse_size(_text(el)))
        if None in vals or None in margins:
            continue
        if vals[0] + sum(margins) > vals[1] + 0.005:
            add("RDL031", "warning", holder,
                f"Width {vals[0]:.2f}in + margins {sum(margins):.2f}in exceeds PageWidth {vals[1]:.2f}in")


def _check_rtl(root, by_tag, parents, add: Adder) -> None:
    rtl = False
    for e in by_tag.get("Direction", []):
        parent = parents.get(e)
        if parent is None or _ln(parent) != "Style":
            continue
        value = _text(e)
        rtl = rtl or value == "RTL"
        if not value.startswith("=") and value not in DIRECTIONS:
            add("RDL050", "error", e, f"Direction '{value}' is not Default, LTR or RTL")
        grand = parents.get(parent)
        if grand is not None and _ln(grand) not in DIRECTION_HOSTS:
            add("RDL051", "info", e, f"Direction on '{_ln(grand)}' is ignored (honored on TextRun, Subreport, Chart, gauges)")
    for e in by_tag.get("NumeralVariant", []):
        parent = parents.get(e)
        value = _text(e)
        if parent is not None and _ln(parent) == "Style" and not value.startswith("="):
            if not (value.isdigit() and 1 <= int(value) <= 7):
                add("RDL052", "error", e, f"NumeralVariant '{value}' must be an integer 1..7")
    for e in by_tag.get("LayoutDirection", []):
        value = _text(e)
        rtl = rtl or value == "RTL"
        if not value.startswith("=") and value not in {"LTR", "RTL"}:
            add("RDL053", "error", e, f"LayoutDirection '{value}' must be LTR or RTL")
    lang = _text(_kid(root, "Language"))
    if lang and not lang.startswith("=") and lang.lower().split("-")[0] in RTL_LANGS and not rtl:
        add("RDL054", "info", _kid(root, "Language"),
            f"Language '{lang}' is right-to-left but no Direction or LayoutDirection is RTL")


def _check_mixed_direction(by_tag, params, add: Adder) -> None:
    """RDL055. A TextRun has one base direction; other-direction text joined to it is reordered by the
    Unicode bidirectional algorithm. Only what the file shows is judged, never run-time values."""
    for run in by_tag.get("TextRun", []):
        value = _kid(run, "Value")
        raw = _text(value)
        # shortcut: any direction mark counts as handled, its placement is not checked; upgrade if that proves too lax
        if not RTL_CHAR_RE.search(raw) or BIDI_MARK_RE.search(raw):
            continue
        if not raw.startswith("="):
            if LATIN_RE.search(raw):
                add("RDL055", "warning", value, "Literal text mixes right-to-left and Latin letters in one TextRun")
            continue
        # A right-to-left string literal counts only when it is concatenated; IIf(x, "...", "...") is one direction.
        if not any(RTL_CHAR_RE.search(m.group()) and (raw[m.end():].lstrip()[:1] in ("&", "+")
                                                      or raw[:m.start()].rstrip()[-1:] in ("&", "+"))
                   for m in VB_STRING_RE.finditer(raw)):
            continue
        bare = strip_vb_strings(raw)
        likely = [f"Parameters!{n}" for n in dict.fromkeys(PARAM_RE.findall(bare))
                  if n.lower() in params and _text(_kid(params[n.lower()], "DataType")) == "String"]
        likely += ["User!"] if USER_RE.search(bare) else []
        fields = [f"Fields!{n}" for n in dict.fromkeys(FIELD_RE.findall(bare))]
        if likely:
            add("RDL055", "warning", value, f"Right-to-left text is joined to {', '.join(likely)} (text that may be "
                "left-to-right: a key, a code, an account name) with no direction mark")
        elif fields:
            add("RDL055", "info", value, f"Right-to-left text is joined to {', '.join(fields)}; "
                "check the order if a field can hold Latin text")


def validate_companion_bytes(data: bytes, suffix: str) -> list[Finding]:
    root, err = _parse(data)
    if err or root is None:
        return [err] if err else []
    findings: list[Finding] = []
    suffix = suffix.lower()
    rule, expect = ("RDL060", "RptDataSource") if suffix == ".rds" else ("RDL061", "DataSourceDefinition")
    if _ln(root) != expect:
        return [Finding(rule, "error", _ln(root) or "/", f"Root element is '{_ln(root)}', expected '{expect}'")]

    def need(parent: ET.Element | None, name: str, path: str) -> ET.Element | None:
        el = _kid(parent, name) if parent is not None else None
        if not _text(el):
            findings.append(Finding(rule, "error", path, f"Missing or empty '{name}'"))
            return None
        return el

    if suffix == ".rds":
        need(root, "Name", expect)
        props = _kid(root, "ConnectionProperties")
        if props is None:
            findings.append(Finding(rule, "error", expect, "Missing 'ConnectionProperties'"))
        base = f"{expect}/ConnectionProperties"
        need(props, "Extension", base)
        cs = need(props, "ConnectString", base)
    else:
        need(root, "Extension", expect)
        cs = need(root, "ConnectString", expect)
    if cs is not None:
        cred = _credential_finding(cs, f"{expect}/ConnectString")
        if cred:
            findings.append(cred)
    return findings


def _result(path: str, kind: str, meta: dict, findings: list[Finding]) -> dict:
    status = "FAIL" if any(f.severity == "error" for f in findings) else "PASS"
    return {"path": path, "kind": kind, "namespace": meta.get("namespace"),
            "rdl_version": meta.get("rdl_version"), "status": status,
            "findings": [f.to_dict() for f in findings]}


def validate_file(path: Path, *, project_stems: set[str] | None = None,
                  expect_params: list[str] | None = None) -> dict:
    suffix = path.suffix.lower()
    kind = suffix.lstrip(".") if suffix in (".rds", ".rsds") else "rdl"
    shown = path.as_posix()
    skipped = {"path": shown, "kind": kind, "namespace": None, "rdl_version": None,
               "status": "FAIL", "findings": []}
    if path.is_symlink():
        return {**skipped, "skipped": "symlink"}
    try:
        if path.stat().st_size > MAX_FILE_SIZE:
            return {**skipped, "skipped": "oversize"}
        data = path.read_bytes()
    except OSError as exc:
        return {**skipped, "skipped": "unreadable", "detail": type(exc).__name__}
    if kind == "rdl":
        meta, findings = validate_rdl_bytes(data, project_stems=project_stems, expect_params=expect_params)
    else:
        meta, findings = {}, validate_companion_bytes(data, suffix)
    return _result(shown, kind, meta, findings)


def collect_project_stems(root: Path) -> set[str]:
    stems: set[str] = set()
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not (Path(base) / d).is_symlink()]
        for name in names:
            p = Path(base) / name
            if p.suffix.lower() in (".rds", ".rsds", ".rsd") and not p.is_symlink():
                stems.add(p.stem.lower())
    return stems


def _document(files: list[dict], warnings: list[dict], unreadable: bool = False) -> dict:
    counts = {"error": 0, "warning": 0, "info": 0}
    for f in files:
        for x in f["findings"]:
            counts[x["severity"]] += 1
    failed = counts["error"] > 0 or unreadable
    # Any skipped, unreadable or absent candidate means the scan did not cover everything asked for.
    coverage_complete = not warnings
    status = "FAIL" if failed else ("PASS" if coverage_complete else "INCOMPLETE")
    return {"schema_version": 1, "mode": "read-only", "tool": TOOL,
            "status": status, "coverage_complete": coverage_complete,
            "summary": {"files": len(files), "errors": counts["error"],
                        "warnings": counts["warning"], "info": counts["info"]},
            "files": files, "warnings": warnings}


def validate_root(root: Path, max_files: int = MAX_FILES) -> dict:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    candidates: list[Path] = []
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not (Path(base) / d).is_symlink())
        for name in sorted(names):
            p = Path(base) / name
            if p.suffix.lower() in (".rdl", ".rds", ".rsds"):
                candidates.append(p)
                if len(candidates) > max_files:
                    raise ValueError("File count limit exceeded")
    stems = collect_project_stems(root)
    files: list[dict] = []
    warnings: list[dict] = []
    unreadable = False
    for p in candidates:
        rel = p.relative_to(root).as_posix()
        result = validate_file(p, project_stems=stems)
        result["path"] = rel
        reason = result.pop("skipped", None)
        if reason:
            warnings.append({"path": rel, "reason": reason})
            unreadable = unreadable or reason == "unreadable"
            continue
        files.append(result)
    if not candidates:
        warnings.append({"path": ".", "reason": "no-candidates"})
    return _document(files, warnings, unreadable)


def validate_single(path: Path, expect_params: list[str] | None = None) -> dict:
    result = validate_file(path, expect_params=expect_params)
    reason = result.pop("skipped", None)
    result.pop("detail", None)
    if reason:
        return _document([], [{"path": path.as_posix(), "reason": reason}], unreadable=True)
    return _document([result], [])


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def render_human(doc: dict) -> str:
    lines = []
    for f in doc["files"]:
        c = {s: sum(1 for x in f["findings"] if x["severity"] == s) for s in ("error", "warning", "info")}
        tail = f"{_plural(c['error'], 'error')}, {_plural(c['warning'], 'warning')}"
        if c["info"]:
            tail += f", {c['info']} info"
        lines.append(f"{f['status']} {f['path']} ({tail})")
        lines += [f"  {x['severity']} {x['rule']} {x['location']}: {x['message']}" for x in f["findings"]]
    lines += [f"WARN {w['path']}: {w['reason']}" for w in doc["warnings"]]
    s = doc["summary"]
    coverage = "" if doc.get("coverage_complete", True) else " (coverage incomplete)"
    lines.append(f"{doc['status']}: {_plural(s['files'], 'file')}, {_plural(s['errors'], 'error')}, "
                 f"{_plural(s['warnings'], 'warning')}, {s['info']} info{coverage}")
    return "\n".join(lines)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--file", type=Path, help="Validate one .rdl/.rds/.rsds file")
    mode.add_argument("--root", type=Path, help="Validate every candidate file under a directory")
    mode.add_argument("--rules", action="store_true", help="Print the rule catalog as JSON")
    parser.add_argument("--json", action="store_true", help="Print the full JSON document")
    parser.add_argument("--max-files", type=int, default=MAX_FILES)
    parser.add_argument("--expect-params", metavar="A,B,...",
                        help="With --file: comma-separated parameter names the caller sends (rule RDL023)")
    args = parser.parse_args(argv)
    try:
        if args.rules:
            print(json.dumps({"schema_version": 1, "tool": TOOL, "rules": RULES},
                             ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.max_files < 1 or args.max_files > MAX_FILES:
            raise ValueError("max-files outside safe range")
        if args.expect_params is not None and args.file is None:
            raise ValueError("--expect-params requires --file")
        if args.file is not None:
            if not args.file.is_file() and not args.file.is_symlink():
                raise FileNotFoundError(args.file.as_posix())
            expected = None if args.expect_params is None else [
                n.strip() for n in args.expect_params.split(",") if n.strip()]
            doc = validate_single(args.file, expected)
        else:
            doc = validate_root(args.root, args.max_files)
        if args.json:
            print(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(render_human(doc))
        return STATUS_EXIT.get(doc["status"], 1)
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "FAIL", "error": type(exc).__name__, "detail": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run())
