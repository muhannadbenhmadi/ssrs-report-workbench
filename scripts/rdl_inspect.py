"""Bounded, offline RDL metadata inspection. Never writes or evaluates report content."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
import xml.etree.ElementTree as ET

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_NODES = 100_000
MAX_DEPTH = 128
MAX_OUTPUT_BYTES = 64 * 1024
MAX_LIMIT = 100
MAX_FIELD_LIMIT = 50
MAX_IDENTIFIER = 128
MAX_CELL_SAMPLES = 3
MAX_REFERENCES = 20
VERSIONS = ("2003/10", "2005/01", "2008/01", "2010/01", "2016/01")
NAMESPACES = {f"http://schemas.microsoft.com/sqlserver/reporting/{v}/reportdefinition": v
              for v in VERSIONS}
OPERATIONS = ("describe_report", "list_datasets", "list_parameters", "list_tablix", "list_columns")
OMITTED = ["connection_properties", "query_text", "expressions", "cell_text", "parameter_values",
           "prompts", "code", "custom_properties", "external_references"]


class InspectionError(Exception):
    """A fixed error code, never a file-derived diagnostic."""


class _NoDTD(ET.TreeBuilder):
    def doctype(self, name, pubid, system):
        raise InspectionError("unsafe-xml")


def _identifier(value):
    # Unicode identifiers permit Arabic names, but no whitespace, markup or controls.
    if value and len(value) <= MAX_IDENTIFIER and value.isidentifier():
        return value
    return None


def _check_components(path):
    for part in (path, *path.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(
                stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise InspectionError("linked-path")


def _read(path):
    path = Path(path).absolute()  # Preserve links and .. until every component is checked.
    if path.suffix.lower() != ".rdl":
        raise InspectionError("not-rdl")
    _check_components(path)
    if not stat.S_ISREG(path.lstat().st_mode):
        raise InspectionError("not-regular-file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise InspectionError("not-regular-file")
        if not os.path.samestat(info, path.lstat()):
            raise InspectionError("changed-file")
        if info.st_size > MAX_FILE_BYTES:
            raise InspectionError("file-too-large")
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise InspectionError("file-too-large")
    # Decode before checking declarations so UTF-16 cannot bypass the DTD gate.
    if data.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        raise InspectionError("unsupported-encoding")
    try:
        text = data.decode("utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
    except UnicodeError:
        raise InspectionError("unsupported-encoding") from None
    if "\x00" in text:
        raise InspectionError("unsupported-encoding")
    declaration = re.match(r"\s*<\?xml\b[^?]*\?>", text)
    if declaration:
        encoding = re.search(r'''encoding\s*=\s*["']([^"']+)["']''', declaration[0], re.I)
        if encoding and encoding[1].lower() not in ("utf-8", "utf-16", "utf-16le", "utf-16be"):
            raise InspectionError("unsupported-encoding")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I):
        raise InspectionError("unsafe-xml")
    # The builder counts actual nodes/depth; comments/PIs are not metadata.
    return _parse_bounded(text)


class _BoundedBuilder(_NoDTD):
    def __init__(self):
        super().__init__()
        self.nodes = self.depth = 0

    def start(self, tag, attrs):
        self.nodes += 1
        self.depth += 1
        if self.nodes > MAX_NODES or self.depth > MAX_DEPTH:
            raise InspectionError("xml-limit")
        return super().start(tag, attrs)

    def end(self, tag):
        result = super().end(tag)
        self.depth -= 1
        return result


def _parse_bounded(text):
    parser = ET.XMLParser(target=_BoundedBuilder())
    for offset in range(0, len(text), 65536):
        parser.feed(text[offset:offset + 65536])
    return parser.close()


class _Report:
    def __init__(self, path):
        try:
            self.root = _read(path)
        except (OSError, ValueError, ET.ParseError):
            raise InspectionError("unreadable-or-invalid-xml") from None
        self.ns = self.root.tag.split("}", 1)[0][1:] if self.root.tag.startswith("{") else ""
        if self.ns not in NAMESPACES or self.root.tag != f"{{{self.ns}}}Report":
            raise InspectionError("unsupported-report")
        self.version = NAMESPACES[self.ns]
        self.warnings = []
        self.legacy = self.version in VERSIONS[:2]
        if self.legacy:
            self.warn("legacy-layout-not-inspected")
        self.datasets = self.children(self.child(self.root, "DataSets"), "DataSet")
        self.parameters = self.children(self.child(self.root, "ReportParameters"), "ReportParameter")
        self.tablix = []
        self.parents = {}
        # Iterative traversal gives deterministic document-order IDs, including nested tablix.
        stack = [(self.root, None)]
        while stack:
            element, parent_id = stack.pop()
            if element.tag == self.tag("Tablix") and not self.legacy:
                ident = len(self.tablix) + 1
                self.tablix.append(element)
                self.parents[ident] = parent_id
                parent_id = ident
            stack.extend((c, parent_id) for c in reversed(element))

    def tag(self, name):
        return f"{{{self.ns}}}{name}"

    def child(self, element, name):
        return element.find(self.tag(name)) if element is not None else None

    def children(self, element, name):
        return element.findall(self.tag(name)) if element is not None else []

    def text(self, element, name):
        child = self.child(element, name)
        return (child.text or "").strip() if child is not None else ""

    def warn(self, code):
        if code not in self.warnings:
            self.warnings.append(code)

    def name(self, element):
        value = element.get("Name", "")
        result = _identifier(value)
        if value and result is None:
            self.warn("identifier-omitted")
        return result

    def reference(self, element, name):
        value = self.text(element, name)
        result = _identifier(value)
        if value and result is None:
            self.warn("identifier-omitted")
        return result

    def enum(self, element, name, choices):
        value = self.text(element, name)
        if value and value not in choices:
            self.warn("nonliteral-or-invalid-metadata")
        return value if value in choices else None

    def columns(self, tablix):
        return self.children(self.child(self.child(tablix, "TablixBody"), "TablixColumns"), "TablixColumn")

    def rows(self, tablix):
        return self.children(self.child(self.child(tablix, "TablixBody"), "TablixRows"), "TablixRow")

    def tablix_info(self, index):
        element = self.tablix[index - 1]
        return {"id": index, "name": self.name(element), "parent_tablix_id": self.parents[index],
                "dataset": self.reference(element, "DataSetName"),
                "column_count": len(self.columns(element)), "row_count": len(self.rows(element)),
                "layout_direction": self.enum(element, "LayoutDirection", ("LTR", "RTL"))}


def _json(result):
    return json.dumps(result, ensure_ascii=True, separators=(",", ":"))


def _finish(report, operation, data, items_key=None, total=0, offset=0):
    result = {"schema_version": 1, "operation": operation, "status": "OK",
              "rdl_version": report.version, "warnings": report.warnings,
              "omitted_by_policy": OMITTED.copy(), "data": data}
    if items_key:
        items = data[items_key]
        page = {"offset": offset, "total": total, "returned": len(items), "next_offset": None}
        result["page"] = page
        while len(_json(result).encode("ascii")) > MAX_OUTPUT_BYTES and items:
            items.pop()
            page["returned"] = len(items)
            report.warn("output-limit")
        if not items and offset < total:
            raise InspectionError("output-limit")  # A single item cannot fit; never return a non-advancing page.
        if offset + len(items) < total:
            page["next_offset"] = offset + len(items)
            report.warn("page-truncated")
    if report.warnings:
        result["status"] = "INCOMPLETE"
    if len(_json(result).encode("ascii")) > MAX_OUTPUT_BYTES:
        raise InspectionError("output-limit")
    return result


def _limits(offset, limit):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
        raise InspectionError("invalid-limits")


def describe_report(path):
    """Describe counts only, without query, expression or literal text."""
    report = _Report(path)
    sections = report.children(report.child(report.root, "ReportSections"), "ReportSection")
    return _finish(report, "describe_report", {
        "dataset_count": len(report.datasets), "parameter_count": len(report.parameters),
        "tablix_count": len(report.tablix),
        "column_count": sum(len(report.columns(t)) for t in report.tablix),
        "section_count": len(sections) if report.version in VERSIONS[3:] else 1,
        "legacy_region_count": sum(1 for e in report.root.iter() if e.tag in
                                   {report.tag("Table"), report.tag("Matrix"), report.tag("List")})})


def list_datasets(path, *, offset=0, limit=50, field_limit=20):
    _limits(offset, limit)
    if type(field_limit) is not int or not 0 <= field_limit <= MAX_FIELD_LIMIT:
        raise InspectionError("invalid-limits")
    report = _Report(path)
    items = []
    for index, element in enumerate(report.datasets[offset:offset + limit], offset + 1):
        fields = report.children(report.child(element, "Fields"), "Field")
        query = report.child(element, "Query")
        items.append({"id": index, "name": report.name(element), "field_count": len(fields),
                      "fields": [{"name": report.name(f), "data_field": report.reference(f, "DataField"),
                                  "calculated": report.child(f, "Value") is not None}
                                 for f in fields[:field_limit]],
                      "fields_returned": min(field_limit, len(fields)),
                      "fields_truncated": len(fields) > field_limit,
                      "query_kind": "shared" if report.child(element, "SharedDataSet") is not None
                      else "embedded" if query is not None else "absent",
                      "command_type": report.enum(query, "CommandType", ("Text", "StoredProcedure", "TableDirect")),
                      "data_source": report.reference(query, "DataSourceName")})
        if len(fields) > field_limit:
            report.warn("fields-truncated")
    return _finish(report, "list_datasets", {"datasets": items}, "datasets", len(report.datasets), offset)


def list_parameters(path, *, offset=0, limit=50):
    _limits(offset, limit)
    report = _Report(path)
    items = []
    for index, element in enumerate(report.parameters[offset:offset + limit], offset + 1):
        item = {"id": index, "name": report.name(element),
                "data_type": report.enum(element, "DataType", ("Boolean", "DateTime", "Integer", "Float", "String")),
                "has_default": report.child(element, "DefaultValue") is not None,
                "has_valid_values": report.child(element, "ValidValues") is not None}
        for tag, key in (("Nullable", "nullable"), ("MultiValue", "multi_value"), ("Hidden", "hidden")):
            value = report.enum(element, tag, ("true", "false"))
            item[key] = value == "true" if value is not None else None
        items.append(item)
    return _finish(report, "list_parameters", {"parameters": items}, "parameters", len(report.parameters), offset)


def list_tablix(path, *, offset=0, limit=50):
    _limits(offset, limit)
    report = _Report(path)
    items = [report.tablix_info(i + 1) for i in range(offset, min(offset + limit, len(report.tablix)))]
    return _finish(report, "list_tablix", {"tablix": items}, "tablix", len(report.tablix), offset)


def _field_references(expression):
    # Remove VB quoted strings (including doubled quote escapes) in one linear pass.
    stripped = []
    quoted = False
    index = 0
    while index < len(expression):
        char = expression[index]
        if char == '"':
            if quoted and index + 1 < len(expression) and expression[index + 1] == '"':
                index += 2
                continue
            quoted = not quoted
            stripped.append(" ")
        elif not quoted:
            stripped.append(char)
        index += 1
    names = []
    for match in re.finditer(r"\bFields!([^\W\d]\w*)\b", "".join(stripped), re.I):
        name = _identifier(match[1])
        if name and name not in names:
            names.append(name)
            if len(names) > MAX_REFERENCES:
                break
    return names[:MAX_REFERENCES], len(names) > MAX_REFERENCES


def _cell_summary(report, contents):
    literals = expressions = 0
    references = []
    truncated = False
    stack = [contents] if contents is not None else []
    while stack:
        element = stack.pop()
        if element.tag == report.tag("Tablix"):
            continue  # A nested tablix belongs to its own ID and dataset scope.
        if element.tag == report.tag("Textbox"):
            values = report.children(element, "Value")
            for paragraph in report.children(report.child(element, "Paragraphs"), "Paragraph"):
                for run in report.children(report.child(paragraph, "TextRuns"), "TextRun"):
                    values.extend(report.children(run, "Value"))
            for value in values:
                text = (value.text or "").lstrip()
                if text.startswith("="):
                    expressions += 1
                    found, cut = _field_references(text)
                    truncated |= cut
                    for name in found:
                        if name not in references:
                            if len(references) < MAX_REFERENCES:
                                references.append(name)
                            else:
                                truncated = True
                else:
                    literals += 1
            continue
        # Only walk ordinary cell containers, not charts, subreports or arbitrary extensions.
        if element.tag in {report.tag("CellContents"), report.tag("Rectangle"), report.tag("ReportItems")}:
            stack.extend(reversed(element))
    if truncated:
        report.warn("references-truncated")
    return {"literal_value_count": literals, "expression_value_count": expressions,
            "field_references": references, "references_truncated": truncated}


def list_columns(path, *, tablix_id, offset=0, limit=50):
    _limits(offset, limit)
    report = _Report(path)
    if type(tablix_id) is not int or not 1 <= tablix_id <= len(report.tablix):
        raise InspectionError("unknown-tablix")
    tablix = report.tablix[tablix_id - 1]
    columns = report.columns(tablix)
    rows = report.rows(tablix)
    simple = True
    row_cells = []
    for row in rows:
        cells = report.children(report.child(row, "TablixCells"), "TablixCell")
        row_cells.append(cells)
        if len(cells) != len(columns):
            simple = False
        for cell in cells:
            contents = report.child(cell, "CellContents")
            if any(report.text(contents, tag) not in ("", "1") for tag in ("ColSpan", "RowSpan")):
                simple = False
    if not simple:
        report.warn("complex-grid-bindings-omitted")
    if simple and len(rows) > MAX_CELL_SAMPLES:
        report.warn("cells-truncated")
    items = []
    for index in range(offset, min(offset + limit, len(columns))):
        width = report.text(columns[index], "Width")
        if width and not re.fullmatch(r"(?:\d{1,4}(?:\.\d{1,6})?|\.\d{1,6})(?:in|cm|mm|pt|pc)", width):
            report.warn("nonliteral-or-invalid-metadata")
            width = None
        cells = []
        if simple:
            for row_index, row in enumerate(row_cells[:MAX_CELL_SAMPLES], 1):
                cells.append({"row_index": row_index, **_cell_summary(report, report.child(row[index], "CellContents"))})
        items.append({"index": index + 1, "width": width or None, "cells": cells,
                      "cells_truncated": simple and len(rows) > MAX_CELL_SAMPLES})
    return _finish(report, "list_columns", {"tablix_id": tablix_id,
                   "binding_coverage": "static-token-samples" if simple else "omitted-complex-grid",
                   "columns": items}, "columns", len(columns), offset)


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise InspectionError("invalid-arguments")


def main(argv=None):
    operation = None
    try:
        parser = _ArgumentParser(description=__doc__)
        parser.add_argument("operation", choices=OPERATIONS)
        parser.add_argument("--file", required=True, type=Path)
        parser.add_argument("--offset", type=int, default=0)
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--field-limit", type=int, default=20)
        parser.add_argument("--tablix-id", type=int)
        args = parser.parse_args(argv)
        operation = args.operation
        # Reject irrelevant options instead of silently suggesting they took effect.
        if (args.tablix_id is not None and operation != "list_columns") or (
                args.field_limit != 20 and operation != "list_datasets") or (
                operation == "describe_report" and (args.offset != 0 or args.limit != 50)):
            raise InspectionError("invalid-arguments")
        kwargs = {} if operation == "describe_report" else {"offset": args.offset, "limit": args.limit}
        if operation == "list_datasets":
            kwargs["field_limit"] = args.field_limit
        if operation == "list_columns":
            kwargs["tablix_id"] = args.tablix_id
        result = globals()[operation](args.file, **kwargs)
    except InspectionError as exc:
        result = {"schema_version": 1, "operation": operation, "status": "ERROR", "error": str(exc)}
    except (OSError, ValueError, ET.ParseError):
        result = {"schema_version": 1, "operation": operation, "status": "ERROR", "error": "unreadable-or-invalid-xml"}
    print(_json(result))
    return {"OK": 0, "ERROR": 1, "INCOMPLETE": 2}[result["status"]]


if __name__ == "__main__":
    sys.exit(main())
