"""Synthetic, offline tests for the RDL static validator."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.rdl_validate import (
    RULES, parse_size, validate_companion_bytes, validate_file,
    validate_rdl_bytes, validate_root, validate_single, collect_project_stems,
)

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures" / "rdl"
RULE_FIXTURES = REPO / "tests" / "fixtures" / "rules"  # one broken and one fixed report per rule
NS = {
    "2008/01": "http://schemas.microsoft.com/sqlserver/reporting/2008/01/reportdefinition",
    "2010/01": "http://schemas.microsoft.com/sqlserver/reporting/2010/01/reportdefinition",
    "2016/01": "http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition",
    "2005/01": "http://schemas.microsoft.com/sqlserver/reporting/2005/01/reportdefinition",
}
DS = ("<DataSources><DataSource Name=\"S1\"><ConnectionProperties><DataProvider>SQL</DataProvider>"
      "<ConnectString>Data Source=localhost</ConnectString></ConnectionProperties></DataSource></DataSources>")


def rdl(body: str, version: str = "2016/01") -> bytes:
    return (f'<?xml version="1.0" encoding="utf-8"?>'
            f'<Report xmlns="{NS[version]}">{body}</Report>').encode("utf-8")


def section(inner: str = "", width: str = "6.5in", page: str = "") -> str:
    page = page or ("<Page><PageHeight>11in</PageHeight><PageWidth>8.5in</PageWidth>"
                    "<LeftMargin>1in</LeftMargin><RightMargin>1in</RightMargin></Page>")
    return (f"<ReportSections><ReportSection><Width>{width}</Width>"
            f"<Body><Height>2in</Height><ReportItems>{inner}</ReportItems></Body>{page}"
            f"</ReportSection></ReportSections>")


def textbox(name: str, value: str = "x") -> str:
    return (f'<Textbox Name="{name}"><Paragraphs><Paragraph><TextRuns><TextRun>'
            f"<Value>{value}</Value></TextRun></TextRuns></Paragraph></Paragraphs></Textbox>")


def styled_textbox(style_inner: str) -> str:
    return ('<Textbox Name="T"><Paragraphs><Paragraph><TextRuns><TextRun><Value>x</Value>'
            f"<Style>{style_inner}</Style></TextRun></TextRuns></Paragraph></Paragraphs></Textbox>")


def dataset(name: str, fields=("A",), source: str = "S1", command: str = "SELECT 1") -> str:
    fs = "".join(f'<Field Name="{f}"><DataField>{f}</DataField></Field>' for f in fields)
    return (f'<DataSet Name="{name}"><Query><DataSourceName>{source}</DataSourceName>'
            f"<CommandText>{command}</CommandText></Query><Fields>{fs}</Fields></DataSet>")


def param(name: str, dtype: str = "String") -> str:
    return f'<ReportParameter Name="{name}"><DataType>{dtype}</DataType></ReportParameter>'


def panel(cells, cols=4, rows=1) -> str:
    defs = "".join(f"<CellDefinition><ColumnIndex>{c}</ColumnIndex><RowIndex>{r}</RowIndex>"
                   f"<ParameterName>{n}</ParameterName></CellDefinition>" for n, c, r in cells)
    return (f"<ReportParametersLayout><GridLayoutDefinition><NumberOfColumns>{cols}</NumberOfColumns>"
            f"<NumberOfRows>{rows}</NumberOfRows><CellDefinitions>{defs}</CellDefinitions>"
            f"</GridLayoutDefinition></ReportParametersLayout>")


def member(keep: str = "", repeat: str = "", group: str = "", inner: str = "") -> str:
    return ("<TablixMember>" + (f'<Group Name="{group}" />' if group else "")
            + (f"<KeepWithGroup>{keep}</KeepWithGroup>" if keep else "")
            + (f"<RepeatOnNewPage>{repeat}</RepeatOnNewPage>" if repeat else "")
            + (f"<TablixMembers>{inner}</TablixMembers>" if inner else "") + "</TablixMember>")


def tablix_rows(members: str) -> str:
    return f'<Tablix Name="X"><TablixRowHierarchy><TablixMembers>{members}</TablixMembers></TablixRowHierarchy></Tablix>'


def rules_of(findings):
    return [f.rule for f in findings]


def check(body: str, version: str = "2016/01", **kw):
    return validate_rdl_bytes(rdl(body, version), **kw)[1]


class RdlValidateTests(unittest.TestCase):
    # ---- fixtures ----
    def test_fixture_valid_2016_passes(self):
        r = validate_file(FIXTURES / "valid_2016.rdl")
        self.assertEqual(r["status"], "PASS", r["findings"])
        self.assertEqual(r["rdl_version"], "2016/01")
        self.assertEqual([f for f in r["findings"] if f["severity"] == "error"], [])

    def test_fixture_valid_2008_passes(self):
        r = validate_file(FIXTURES / "valid_2008.rdl")
        self.assertEqual(r["status"], "PASS", r["findings"])
        self.assertEqual(r["rdl_version"], "2008/01")

    def test_fixture_broken_reports_expected_rules(self):
        r = validate_file(FIXTURES / "broken_refs_2016.rdl")
        self.assertEqual(r["status"], "FAIL")
        ids = {f["rule"] for f in r["findings"]}
        self.assertTrue({"RDL011", "RDL020", "RDL010", "RDL014", "RDL030", "RDL040"} <= ids, ids)

    # ---- parsing and structure ----
    def test_bom_is_accepted(self):
        data = b"\xef\xbb\xbf" + (FIXTURES / "valid_2016.rdl").read_bytes()
        meta, findings = validate_rdl_bytes(data)
        self.assertEqual(meta["rdl_version"], "2016/01")
        self.assertEqual([f for f in findings if f.severity == "error"], [])

    def test_dtd_rejected(self):
        for decl in ("<!DOCTYPE Report>", '<!DOCTYPE r [<!ENTITY x "y">]>'):
            data = (f'<?xml version="1.0"?>{decl}<Report xmlns="{NS["2016/01"]}"/>').encode()
            _, findings = validate_rdl_bytes(data)
            self.assertEqual(rules_of(findings), ["RDL001"])

    def test_malformed_xml_rdl001(self):
        _, findings = validate_rdl_bytes(b"<Report><unclosed></Report>")
        self.assertEqual(rules_of(findings), ["RDL001"])

    def test_unknown_namespace_error(self):
        data = b'<Report xmlns="urn:example:other"><Body/></Report>'
        meta, findings = validate_rdl_bytes(data)
        self.assertEqual(rules_of(findings), ["RDL002"])
        self.assertEqual(findings[0].severity, "error")
        self.assertIsNone(meta["rdl_version"])

    def test_wrong_root_is_rdl002_error(self):
        _, findings = validate_rdl_bytes(f'<Other xmlns="{NS["2016/01"]}"/>'.encode())
        self.assertEqual(rules_of(findings), ["RDL002"])

    def test_legacy_namespace_warning(self):
        meta, findings = validate_rdl_bytes(rdl("", "2005/01"))
        self.assertEqual(rules_of(findings), ["RDL002"])
        self.assertEqual(findings[0].severity, "warning")
        self.assertEqual(meta["rdl_version"], "2005/01")

    def test_rdl003_2008_requires_body_page_width(self):
        findings = check("<Language>en-US</Language>", "2008/01")
        self.assertEqual(rules_of(findings).count("RDL003"), 3)

    def test_rdl003_2016_requires_report_sections(self):
        self.assertIn("RDL003", rules_of(check("<Language>en-US</Language>")))

    def test_rdl003_section_requires_parts(self):
        findings = check("<ReportSections><ReportSection/></ReportSections>")
        self.assertGreaterEqual(rules_of(findings).count("RDL003"), 3)

    def test_children_order_free(self):
        body = (f"{DS}<DataSets>{dataset('D1')}</DataSets>"
                f"<Language>en-US</Language>{section(textbox('T1'))}")
        self.assertEqual([f for f in check(body) if f.severity == "error"], [])
        body2 = (f"<Language>en-US</Language>{section(textbox('T1'))}"
                 f"<DataSets>{dataset('D1')}</DataSets>{DS}")
        self.assertEqual([f for f in check(body2) if f.severity == "error"], [])

    # ---- names and references ----
    def test_rdl010_duplicate_names_case_insensitive(self):
        def sev(body):
            return [x.severity for x in check(body) if x.rule == "RDL010"]
        # Case-only collisions are warnings: Microsoft-shipped designer reports contain them.
        self.assertEqual(sev(section(textbox("A") + textbox("a"))), ["warning"])
        self.assertEqual(sev(f"{DS}<DataSets>{dataset('D')}{dataset('d')}</DataSets>" + section()), ["warning"])
        self.assertEqual(sev(f"<ReportParameters>{param('P')}{param('p')}</ReportParameters>" + section()),
                         ["warning"])
        # Exact duplicates are errors.
        self.assertEqual(sev(section(textbox("A") + textbox("A"))), ["error"])
        self.assertEqual(sev(f"{DS}<DataSets>{dataset('D')}{dataset('D')}</DataSets>" + section()), ["error"])

    def test_rdl010_same_name_across_categories_ok(self):
        body = f"{DS}<DataSets>{dataset('X')}</DataSets>" + section(textbox("X"))
        self.assertNotIn("RDL010", rules_of(check(body)))

    def test_rdl011_unknown_data_source(self):
        body = f"{DS}<DataSets>{dataset('D1', source='Nope')}</DataSets>" + section()
        f = [x for x in check(body) if x.rule == "RDL011"]
        self.assertEqual(len(f), 1)
        self.assertIn("Nope", f[0].message)
        self.assertIn("DataSet[@Name='D1']", f[0].location)

    def test_rdl012_missing_command_text(self):
        ds = '<DataSet Name="D1"><Query><DataSourceName>S1</DataSourceName></Query></DataSet>'
        self.assertIn("RDL012", rules_of(check(f"{DS}<DataSets>{ds}</DataSets>" + section())))
        shared = ('<DataSet Name="D1"><SharedDataSet><SharedDataSetReference>Shared'
                  "</SharedDataSetReference></SharedDataSet></DataSet>")
        self.assertNotIn("RDL012", rules_of(check(f"<DataSets>{shared}</DataSets>" + section())))

    def test_rdl013_both_connection_and_reference(self):
        ds = ('<DataSources><DataSource Name="S1"><ConnectionProperties><DataProvider>SQL</DataProvider>'
              "<ConnectString>x</ConnectString></ConnectionProperties>"
              "<DataSourceReference>Shared</DataSourceReference></DataSource></DataSources>")
        self.assertIn("RDL013", rules_of(check(ds + section())))

    def test_rdl014_bad_datatype(self):
        body = f"<ReportParameters>{param('P', 'Text')}</ReportParameters>" + section()
        self.assertIn("RDL014", rules_of(check(body)))
        for ok in ("Boolean", "DateTime", "Integer", "Float", "String"):
            body = f"<ReportParameters>{param('P', ok)}</ReportParameters>" + section()
            self.assertNotIn("RDL014", rules_of(check(body)))

    def test_rdl020_undefined_parameter(self):
        body = f"<ReportParameters>{param('Year')}</ReportParameters>" + section(
            textbox("T1", "=Parameters!Year.Value") + textbox("T2", "=Parameters!Region.Value"))
        f = [x for x in check(body) if x.rule == "RDL020"]
        self.assertEqual(len(f), 1)
        self.assertIn("Region", f[0].message)

    def test_rdl021_unknown_field_warns(self):
        body = f"{DS}<DataSets>{dataset('D1', ('A',))}</DataSets>" + section(
            textbox("T1", "=Fields!Missing.Value"))
        f = [x for x in check(body) if x.rule == "RDL021"]
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0].severity, "warning")

    def test_fields_scope_uses_nearest_dataset(self):
        ds = f"{DS}<DataSets>{dataset('Orders', ('Total',))}{dataset('Other', ('Amount',))}</DataSets>"
        good = ('<Tablix Name="Tx"><DataSetName>Orders</DataSetName>'
                + textbox("T1", "=Fields!Total.Value") + "</Tablix>")
        self.assertNotIn("RDL021", rules_of(check(ds + section(good))))
        bad = ('<Tablix Name="Tx"><DataSetName>Other</DataSetName>'
               + textbox("T1", "=Fields!Total.Value") + "</Tablix>")
        self.assertIn("RDL021", rules_of(check(ds + section(bad))))

    def test_fields_unknown_dataset_skipped(self):
        ds = f"{DS}<DataSets>{dataset('Orders', ('Total',))}{dataset('Other', ('Amount',))}</DataSets>"
        tx = ('<Tablix Name="Tx"><DataSetName>Ghost</DataSetName>'
              + textbox("T1", "=Fields!Whatever.Value") + "</Tablix>")
        self.assertNotIn("RDL021", rules_of(check(ds + section(tx))))

    def test_fields_without_scope_and_many_datasets_skipped(self):
        ds = f"{DS}<DataSets>{dataset('Orders', ('Total',))}{dataset('Other', ('Amount',))}</DataSets>"
        self.assertNotIn("RDL021", rules_of(check(ds + section(textbox("T1", "=Fields!Zzz.Value")))))

    def test_fields_single_dataset_default(self):
        ds = f"{DS}<DataSets>{dataset('Only', ('Total',))}</DataSets>"
        self.assertIn("RDL021", rules_of(check(ds + section(textbox("T1", "=Fields!Zzz.Value")))))

    def test_orphan_parameter_info(self):
        body = f"<ReportParameters>{param('Unused')}{param('Used')}</ReportParameters>" + section(
            textbox("T1", "=Parameters!Used.Value"))
        f = [x for x in check(body) if x.rule == "RDL022"]
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0].severity, "info")
        self.assertIn("Unused", f[0].message)

    # ---- sizes ----
    def test_parse_size(self):
        self.assertAlmostEqual(parse_size("2.54cm"), 1.0)
        self.assertAlmostEqual(parse_size("25.4mm"), 1.0)
        self.assertAlmostEqual(parse_size("72pt"), 1.0)
        self.assertAlmostEqual(parse_size("6pc"), 1.0)
        self.assertEqual(parse_size("3in"), 3.0)
        for bad in ("3", "in", "3 inches", "abc", "", "1e3in"):
            self.assertIsNone(parse_size(bad), bad)

    def test_rdl030_bad_and_oversize(self):
        self.assertIn("RDL030", rules_of(check(section(width="6.5"))))
        self.assertIn("RDL030", rules_of(check(section(width="200in"))))
        self.assertIn("RDL030", rules_of(check(section(width="500cm"))))
        self.assertIn("RDL030", rules_of(check(section(width="-1in"))))
        self.assertNotIn("RDL030", rules_of(check(section(width="160in"))))
        self.assertNotIn("RDL030", rules_of(check(section(width="0in"))))

    def test_rdl030_skips_expressions_and_gauge_percentages(self):
        self.assertNotIn("RDL030", rules_of(check(section(width="=Parameters!W.Value"))))
        gauge = ('<GaugePanel Name="G"><Left>1in</Left><LinearGauges><LinearGauge Name="L">'
                 "<Left>10.5</Left><Top>20</Top></LinearGauge></LinearGauges></GaugePanel>")
        self.assertNotIn("RDL030", rules_of(check(section(gauge))))

    def test_width_exceeds_page_warning(self):
        findings = check(section(width="7in"))
        f = [x for x in findings if x.rule == "RDL031"]
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0].severity, "warning")
        self.assertNotIn("RDL031", rules_of(check(section(width="6.5in"))))
        self.assertNotIn("RDL031", rules_of(check(section(width="=Code.W()"))))

    # ---- secrets ----
    def test_rdl040_credential_keys(self):
        for cs in ("Password=abc", "x;pwd = abc", "User ID=bob", "Uid=bob"):
            ds = ("<DataSources><DataSource Name=\"S1\"><ConnectionProperties><DataProvider>SQL"
                  f"</DataProvider><ConnectString>Data Source=h;{cs}</ConnectString>"
                  "</ConnectionProperties></DataSource></DataSources>")
            self.assertIn("RDL040", rules_of(check(ds + section())), cs)
        self.assertNotIn("RDL040", rules_of(check(DS + section())))

    def test_connect_string_value_not_in_output(self):
        secret = "Zq9TopSecretValue"
        ds = ("<DataSources><DataSource Name=\"S1\"><ConnectionProperties><DataProvider>SQL"
              "</DataProvider><ConnectString>Data Source=srv-hidden;User ID=u_hidden;"
              f"Password={secret}</ConnectString></ConnectionProperties></DataSource></DataSources>")
        _, findings = validate_rdl_bytes(rdl(ds + section()))
        blob = json.dumps([f.to_dict() for f in findings])
        for token in (secret, "srv-hidden", "u_hidden"):
            self.assertNotIn(token, blob)
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "a.rdl").write_bytes(rdl(ds + section()))
            self.assertNotIn(secret, json.dumps(validate_root(Path(tmp))))
            Path(tmp, "b.rds").write_text(
                "<RptDataSource><Name>n</Name><ConnectionProperties><Extension>SQL</Extension>"
                f"<ConnectString>Password={secret}</ConnectString></ConnectionProperties>"
                "</RptDataSource>", encoding="utf-8")
            doc = validate_root(Path(tmp))
            self.assertNotIn(secret, json.dumps(doc))
            self.assertIn("RDL040", {x["rule"] for f in doc["files"] if f["path"] == "b.rds"
                                     for x in f["findings"]})

    # ---- RTL ----
    def test_rdl050_direction_values(self):
        self.assertIn("RDL050", rules_of(check(section(
            styled_textbox("<Direction>Sideways</Direction>")))))
        for ok in ("Default", "LTR", "RTL", "=Code.D()"):
            self.assertNotIn("RDL050", rules_of(check(section(
                styled_textbox(f"<Direction>{ok}</Direction>")))), ok)

    def test_rdl051_direction_ignored_location(self):
        tb = ('<Textbox Name="T"><Paragraphs><Paragraph><TextRuns><TextRun><Value>x</Value></TextRun>'
              "</TextRuns></Paragraph></Paragraphs><Style><Direction>RTL</Direction></Style></Textbox>")
        f = [x for x in check(section(tb)) if x.rule == "RDL051"]
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0].severity, "info")
        self.assertNotIn("RDL051", rules_of(check(section(
            styled_textbox("<Direction>RTL</Direction>")))))

    def test_rdl052_numeral_variant(self):
        for bad in ("0", "8", "x"):
            self.assertIn("RDL052", rules_of(check(section(
                styled_textbox(f"<NumeralVariant>{bad}</NumeralVariant>")))), bad)
        for ok in ("1", "7", "=Code.N()"):
            self.assertNotIn("RDL052", rules_of(check(section(
                styled_textbox(f"<NumeralVariant>{ok}</NumeralVariant>")))), ok)

    def test_rdl053_layout_direction(self):
        bad = '<Tablix Name="Tx"><LayoutDirection>Up</LayoutDirection></Tablix>'
        good = '<Tablix Name="Tx"><LayoutDirection>RTL</LayoutDirection></Tablix>'
        self.assertIn("RDL053", rules_of(check(section(bad))))
        self.assertNotIn("RDL053", rules_of(check(section(good))))

    def test_rdl054_rtl_readiness(self):
        f = [x for x in check("<Language>ar-SA</Language>" + section()) if x.rule == "RDL054"]
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0].severity, "info")
        rtl = "<Language>ar-SA</Language>" + section(
            '<Tablix Name="Tx"><LayoutDirection>RTL</LayoutDirection></Tablix>')
        self.assertNotIn("RDL054", rules_of(check(rtl)))
        self.assertNotIn("RDL054", rules_of(check("<Language>en-US</Language>" + section())))
        self.assertNotIn("RDL054", rules_of(check("<Language>arm-XX</Language>" + section())))

    # ---- companions ----
    def test_rds_rules(self):
        good = (b"<RptDataSource><Name>n</Name><ConnectionProperties><Extension>SQL</Extension>"
                b"<ConnectString>Data Source=h</ConnectString></ConnectionProperties></RptDataSource>")
        self.assertEqual(validate_companion_bytes(good, ".rds"), [])
        self.assertEqual(rules_of(validate_companion_bytes(b"<Other/>", ".rds")), ["RDL060"])
        missing = b"<RptDataSource><Name>n</Name><ConnectionProperties/></RptDataSource>"
        self.assertEqual(rules_of(validate_companion_bytes(missing, ".rds")), ["RDL060", "RDL060"])
        self.assertEqual(rules_of(validate_companion_bytes(b"<RptDataSource", ".rds")), ["RDL001"])

    def test_rsds_rules(self):
        good = (b'<DataSourceDefinition xmlns="http://schemas.microsoft.com/sqlserver/reporting/2010/01/'
                b'datasourcedefinition"><Extension>SQL</Extension>'
                b"<ConnectString>Data Source=h</ConnectString></DataSourceDefinition>")
        self.assertEqual(validate_companion_bytes(good, ".rsds"), [])
        self.assertEqual(rules_of(validate_companion_bytes(b"<RptDataSource/>", ".rsds")), ["RDL061"])
        self.assertEqual(rules_of(validate_companion_bytes(b"<DataSourceDefinition/>", ".rsds")),
                         ["RDL061", "RDL061"])

    def test_rsds_rsd_reference_resolution(self):
        ds = ('<DataSources><DataSource Name="S1"><DataSourceReference>/Data Sources/Shared One'
              "</DataSourceReference></DataSource></DataSources>")
        shared = ('<DataSets><DataSet Name="D1"><SharedDataSet><SharedDataSetReference>/Sets/Common'
                  "</SharedDataSetReference></SharedDataSet></DataSet></DataSets>")
        body = ds + shared + section()
        # Without project stems (single-file mode) the rule is skipped, and also when the scanned
        # root holds no shared files at all (references then live on the report server).
        self.assertNotIn("RDL062", rules_of(check(body)))
        self.assertNotIn("RDL062", rules_of(check(body, project_stems=set())))
        miss = [x for x in check(body, project_stems={"unrelated"}) if x.rule == "RDL062"]
        self.assertEqual(len(miss), 2)
        self.assertEqual(miss[0].severity, "warning")
        hit = check(body, project_stems={"shared one", "common"})
        self.assertNotIn("RDL062", rules_of(hit))

    def test_collect_project_stems(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sub").mkdir()
            (root / ".git").mkdir()
            (root / "sub" / "Alpha.RDS").write_text("<x/>")
            (root / "Beta.rsds").write_text("<x/>")
            (root / "Gamma.rsd").write_text("<x/>")
            (root / "Report.rdl").write_text("<x/>")
            (root / ".git" / "Hidden.rds").write_text("<x/>")
            self.assertEqual(collect_project_stems(root), {"alpha", "beta", "gamma"})

    # ---- root / single ----
    def test_root_no_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = validate_root(Path(tmp))
        self.assertEqual(doc["status"], "INCOMPLETE")
        self.assertFalse(doc["coverage_complete"])
        self.assertEqual(doc["summary"]["files"], 0)
        self.assertEqual(doc["warnings"], [{"path": ".", "reason": "no-candidates"}])

    def test_root_coverage_complete_when_nothing_skipped(self):
        doc = validate_root(FIXTURES)
        self.assertTrue(doc["coverage_complete"])
        self.assertEqual(doc["warnings"], [])

    def test_root_incomplete_never_reports_pass(self):
        from scripts.discovery import MAX_FILE_SIZE
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.joinpath("ok.rdl").write_bytes(rdl(section()))
            with (root / "big.rdl").open("wb") as f:
                f.truncate(MAX_FILE_SIZE + 1)
            doc = validate_root(root)
        self.assertEqual(doc["status"], "INCOMPLETE")
        self.assertFalse(doc["coverage_complete"])
        self.assertEqual(doc["summary"]["files"], 1)
        self.assertEqual(doc["summary"]["errors"], 0)

    def test_root_errors_outrank_incomplete(self):
        from scripts.discovery import MAX_FILE_SIZE
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.joinpath("bad.rdl").write_bytes(rdl(section(width="200in")))
            with (root / "big.rdl").open("wb") as f:
                f.truncate(MAX_FILE_SIZE + 1)
            doc = validate_root(root)
        self.assertEqual(doc["status"], "FAIL")
        self.assertFalse(doc["coverage_complete"])

    def test_string_literal_references_are_not_references(self):
        body = (f"{DS}<DataSets>{dataset('D1', ('A',))}</DataSets>"
                f"<ReportParameters>{param('Year')}</ReportParameters>" + section(
                    textbox("T1", '="Parameters!NotAParameter.Value"')
                    + textbox("T2", '="Fields!Missing.Value"')
                    + textbox("T3", '="He said ""Parameters!Nope.Value"" and ""Fields!Nope.Value"""')
                    + textbox("T4", '=Parameters!Year.Value &amp; " Fields!Ghost.Value Parameters!Ghost.Value"')))
        rules = rules_of(check(body))
        self.assertNotIn("RDL020", rules)
        self.assertNotIn("RDL021", rules)
        self.assertNotIn("RDL022", rules)  # Year is really referenced in T4

    def test_references_outside_string_literals_still_checked(self):
        body = (f"{DS}<DataSets>{dataset('D1', ('A',))}</DataSets>"
                f"<ReportParameters>{param('Year')}</ReportParameters>" + section(
                    textbox("T1", '="Label: " &amp; Parameters!Missing.Value &amp; Fields!Nope.Value')))
        rules = rules_of(check(body))
        self.assertIn("RDL020", rules)
        self.assertIn("RDL021", rules)

    def test_rdl011_missing_or_empty_data_source_name(self):
        missing = '<DataSet Name="D1"><Query><CommandText>SELECT 1</CommandText></Query></DataSet>'
        empty = ('<DataSet Name="D1"><Query><DataSourceName> </DataSourceName>'
                 "<CommandText>SELECT 1</CommandText></Query></DataSet>")
        for ds in (missing, empty):
            f = [x for x in check(f"{DS}<DataSets>{ds}</DataSets>" + section()) if x.rule == "RDL011"]
            self.assertEqual(len(f), 1, ds)
            self.assertEqual(f[0].severity, "error")
            self.assertIn("missing or empty", f[0].message)
        resolved = f"{DS}<DataSets>{dataset('D1')}</DataSets>" + section()
        self.assertNotIn("RDL011", rules_of(check(resolved)))
        shared = ('<DataSet Name="D1"><SharedDataSet><SharedDataSetReference>Shared'
                  "</SharedDataSetReference></SharedDataSet></DataSet>")
        self.assertNotIn("RDL011", rules_of(check(f"<DataSets>{shared}</DataSets>" + section())))

    def test_rdl021_aggregate_scope_literal(self):
        ds = f"{DS}<DataSets>{dataset('Orders', ('Total',))}{dataset('Company', ('PrimaryColor',))}</DataSets>"
        tablix = ('<Tablix Name="T"><DataSetName>Orders</DataSetName><TablixBody><TablixRows><TablixRow>'
                  "<TablixCells><TablixCell><CellContents>"
                  + textbox("T1", '=First(Fields!PrimaryColor.Value, "Company")')
                  + textbox("T2", '=First(Fields!Nope.Value, "Company")')
                  + "</CellContents></TablixCell></TablixCells></TablixRow></TablixRows></TablixBody></Tablix>")
        f = [x for x in check(ds + section(tablix)) if x.rule == "RDL021"]
        self.assertEqual(len(f), 1)
        self.assertIn("Nope", f[0].message)
        self.assertIn("Company", f[0].message)

    def test_rdl022_query_text_parameter_counts_as_used(self):
        body = (f"{DS}<DataSets>{dataset('D1', command='SELECT * FROM t WHERE y = @YearEnd')}</DataSets>"
                f"<ReportParameters>{param('YearEnd')}{param('Year')}{param('Unused')}</ReportParameters>"
                + section())
        f = [x for x in check(body) if x.rule == "RDL022"]
        # @YearEnd uses YearEnd only; Year is not a prefix match.
        self.assertEqual(sorted(x.location.split("'")[1] for x in f), ["Unused", "Year"])

    def test_large_expression_is_linear(self):
        import time
        big = '="' + ("x" * 200000) + '" & Fields!A.Value & "' + ('""' * 50000) + '"'
        body = f"{DS}<DataSets>{dataset('D1', ('A',))}</DataSets>" + section(textbox("T1", big))
        start = time.perf_counter()
        self.assertNotIn("RDL021", rules_of(check(body)))
        self.assertLess(time.perf_counter() - start, 5.0)

    def test_strip_vb_strings(self):
        from scripts.rdl_validate import strip_vb_strings
        self.assertEqual(strip_vb_strings('="a"'), '=""')
        self.assertEqual(strip_vb_strings('="say ""hi"" " & X'), '="" & X')
        self.assertEqual(strip_vb_strings("=Fields!A.Value"), "=Fields!A.Value")

    def test_root_status_and_summary(self):
        doc = validate_root(FIXTURES)
        self.assertEqual(doc["schema_version"], 1)
        self.assertEqual(doc["mode"], "read-only")
        self.assertEqual(doc["tool"], "ssrs-report-workbench-rdl-validator")
        self.assertEqual(doc["status"], "FAIL")
        by_path = {f["path"]: f for f in doc["files"]}
        self.assertEqual(set(by_path), {"valid_2016.rdl", "valid_2008.rdl", "broken_refs_2016.rdl",
                                        "shared.rds", "shared.rsds"})
        self.assertEqual(by_path["valid_2016.rdl"]["status"], "PASS")
        self.assertEqual(by_path["broken_refs_2016.rdl"]["status"], "FAIL")
        self.assertEqual(by_path["shared.rds"]["kind"], "rds")
        s = doc["summary"]
        self.assertEqual(s["files"], 5)
        self.assertEqual(s["errors"], sum(1 for f in doc["files"] for x in f["findings"]
                                          if x["severity"] == "error"))
        self.assertGreaterEqual(s["errors"], 5)

    def test_root_pass_when_only_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "w.rdl").write_bytes(rdl(section(width="7in")))
            doc = validate_root(Path(tmp))
        self.assertEqual(doc["status"], "PASS")
        self.assertGreaterEqual(doc["summary"]["warnings"], 1)

    def test_root_oversize_warns(self):
        from scripts.discovery import MAX_FILE_SIZE
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (root / "big.rdl").open("wb") as f:
                f.truncate(MAX_FILE_SIZE + 1)
            doc = validate_root(root)
        self.assertIn({"path": "big.rdl", "reason": "oversize"}, doc["warnings"])
        self.assertEqual(doc["summary"]["files"], 0)
        self.assertEqual(doc["status"], "INCOMPLETE")

    def test_symlink_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real.rdl"
            real.write_bytes(rdl(section()))
            link = root / "link.rdl"
            try:
                link.symlink_to(real)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            doc = validate_root(root)
            self.assertEqual([f["path"] for f in doc["files"]], ["real.rdl"])
            self.assertIn({"path": "link.rdl", "reason": "symlink"}, doc["warnings"])
            self.assertEqual(validate_single(link)["status"], "FAIL")

    def test_count_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "a.rdl").write_bytes(rdl(section()))
            Path(tmp, "b.rdl").write_bytes(rdl(section()))
            with self.assertRaises(ValueError):
                validate_root(Path(tmp), max_files=1)

    def test_validate_single_shape(self):
        doc = validate_single(FIXTURES / "valid_2016.rdl")
        self.assertEqual(doc["status"], "PASS")
        self.assertEqual(doc["summary"]["files"], 1)
        self.assertEqual(len(doc["files"]), 1)

    def test_no_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.rdl").write_bytes((FIXTURES / "broken_refs_2016.rdl").read_bytes())
            (root / "b.rds").write_bytes((FIXTURES / "shared.rds").read_bytes())

            def snap():
                return sorted((x.relative_to(root).as_posix(), x.stat().st_size, x.stat().st_mtime_ns)
                              for x in root.rglob("*"))
            before = snap()
            validate_root(root)
            validate_single(root / "a.rdl")
            self.assertEqual(before, snap())

    # ---- catalog ----
    def test_rules_catalog_has_all_ids_used(self):
        src = (REPO / "scripts" / "rdl_validate.py").read_text(encoding="utf-8")
        used = set(re.findall(r'"(RDL0\d\d)"', src))
        self.assertTrue(used)
        self.assertEqual(used - set(RULES), set())
        self.assertGreaterEqual(len(RULES), 20)
        for rule in RULES.values():
            self.assertEqual(set(rule), {"title", "severity", "basis"})

    # ---- parameter panel (RDL015), RepeatOnNewPage parity (RDL070), caller parameters (RDL023) ----
    def test_rule_fixtures_broken_fail_and_fixed_pass(self):
        for stem, rule in (("panel", "RDL015"), ("repeat_parity", "RDL070")):
            broken = validate_file(RULE_FIXTURES / f"{stem}_{'missing' if stem == 'panel' else 'broken'}_2016.rdl")
            self.assertEqual(broken["status"], "FAIL")
            self.assertEqual({f["rule"] for f in broken["findings"]}, {rule})
            fixed = validate_file(RULE_FIXTURES / f"{stem}_fixed_2016.rdl")
            self.assertEqual((fixed["status"], fixed["findings"]), ("PASS", []))

    def test_rdl015_grid_rules(self):
        def messages(cells, cols=4, rows=1, names=("A", "B"), version="2016/01"):
            body = (f"<ReportParameters>{''.join(param(n) for n in names)}</ReportParameters>" + panel(cells, cols, rows)
                    + section(textbox("T", "=" + " &amp; ".join(f"Parameters!{n}.Value" for n in names))))
            return [f.message for f in check(body, version) if f.rule == "RDL015"]

        self.assertEqual(messages([("A", 0, 0), ("B", 1, 0)]), [])
        self.assertEqual(messages([("a", 0, 0), ("B", 1, 0)]), [])  # names are matched without case
        self.assertIn("2 ReportParameter(s) but 1 CellDefinition(s)", messages([("A", 0, 0)])[0])
        self.assertIn("'B' has no CellDefinition", messages([("A", 0, 0)])[1])
        self.assertIn("'Z', which is not a ReportParameter", messages([("A", 0, 0), ("Z", 1, 0)])[0])
        self.assertIn("more than one CellDefinition", messages([("A", 0, 0), ("A", 1, 0)])[0])
        self.assertIn("ColumnIndex 4 is outside the grid", messages([("A", 0, 0), ("B", 4, 0)])[0])
        self.assertIn("RowIndex 1 is outside the grid", messages([("A", 0, 0), ("B", 0, 1)])[0])
        self.assertIn("shares column 0, row 0", messages([("A", 0, 0), ("B", 0, 0)])[0])
        self.assertIn("ColumnIndex 'x' is not", messages([("A", 0, 0), ("B", "x", 0)])[0])
        self.assertIn("NumberOfRows is missing", messages([("A", 0, 0), ("B", 1, 0)], rows="")[0])
        # A layout that lists a parameter the report no longer declares.
        self.assertTrue(messages([("A", 0, 0)], names=()))
        # ReportParametersLayout exists only in the 2016/01 schema.
        body = f"<ReportParameters>{param('A')}</ReportParameters>" + section(textbox("T", "=Parameters!A.Value"))
        self.assertNotIn("RDL015", rules_of(check(body, "2010/01")))
        self.assertIn("RDL015", rules_of(check(body, "2016/01")))
        self.assertNotIn("RDL015", rules_of(check(section())))  # no parameters, no layout

    def test_rdl070_repeat_on_new_page_parity(self):
        def count(*members):
            return rules_of(check(section(tablix_rows("".join(members))))).count("RDL070")

        group, t, f, none = member(group="G"), member("After", "true"), member("After", "false"), member("After")
        self.assertEqual(count(t, t, group), 0)
        self.assertEqual(count(none, none, f, group), 0)  # an absent RepeatOnNewPage is false
        self.assertEqual(count(t, none, t, group), 1)     # expected value comes from the member next to the group
        self.assertEqual(count(none, t, t, group), 1)
        self.assertEqual(count(none, member(), t, group), 0)  # KeepWithGroup=None ends the run
        self.assertEqual(count(group, member("Before", "true"), member("Before")), 1)
        self.assertEqual(count(t, group, member("Before")), 0)  # header and footer runs are judged separately
        self.assertEqual(count(t, none), 0)  # no dynamic member, nothing to keep with
        nested = member(group="Outer", inner=t + none + group)
        self.assertEqual(count(t, nested), 1)

    def test_rdl023_caller_parameters(self):
        fixed = RULE_FIXTURES / "panel_fixed_2016.rdl"
        declared = ["UserId", "FromDate", "ToDate", "BranchId", "IsMain"]
        self.assertEqual(validate_file(fixed, expect_params=declared)["findings"], [])
        self.assertEqual(validate_file(fixed)["findings"], [])  # the rule is opt-in
        r = validate_file(fixed, expect_params=declared + ["PrintedBy", "userid"])
        self.assertEqual(r["status"], "FAIL")
        self.assertEqual([(f["rule"], f["severity"]) for f in r["findings"]], [("RDL023", "error")] * 2)
        r = validate_file(fixed, expect_params=declared[:4])
        self.assertEqual(r["status"], "PASS")
        self.assertEqual([(f["rule"], f["severity"]) for f in r["findings"]], [("RDL023", "warning")])
        self.assertIn("'IsMain'", r["findings"][0]["message"])
        with_default = (f"<ReportParameters>{param('A')[:-18]}<DefaultValue><Values><Value>1</Value></Values>"
                        f"</DefaultValue></ReportParameter></ReportParameters>" + panel([("A", 0, 0)])
                        + section(textbox("T", "=Parameters!A.Value")))
        self.assertEqual(check(with_default, expect_params=[]), [])

    def test_rdl055_mixed_direction(self):
        joined = validate_file(RULE_FIXTURES / "mixed_direction_joined_2016.rdl")
        self.assertEqual(joined["status"], "PASS")  # a warning never fails a file
        self.assertEqual([(f["rule"], f["severity"]) for f in joined["findings"]], [("RDL055", "warning")])
        self.assertIn("Textbox[@Name='Subtitle']", joined["findings"][0]["location"])
        self.assertEqual(validate_file(RULE_FIXTURES / "mixed_direction_marked_2016.rdl")["findings"], [])

        def hits(value, params=""):
            body = f"<ReportParameters>{params}</ReportParameters>" + section(textbox("T", value))
            return [f.severity for f in check(body) if f.rule == "RDL055"]

        label, key, amp = '"\u0631\u0642\u0645: "', "Parameters!Key.Value", " &amp; "
        self.assertEqual(hits("\u062a\u0642\u0631\u064a\u0631 HR"), ["warning"])        # literal mix
        self.assertEqual(hits("\u0627\u0644\u0625\u0630\u0646 (30) - 2"), [])           # digits and brackets only
        self.assertEqual(hits("Report (30)"), [])
        self.assertEqual(hits(f"={label}{amp}{key}", param("Key")), ["warning"])
        self.assertEqual(hits(f"={key} + {label}", param("Key")), ["warning"])
        self.assertEqual(hits(f"={label}{amp}{key}", param("Key", "Integer")), [])
        self.assertEqual(hits(f"={label}{amp}User!UserID"), ["warning"])
        self.assertEqual(hits(f"={label}{amp}Fields!A.Value"), ["info"])
        self.assertEqual(hits(f'={label} + Format(Fields!D.Value, "yyyy/MM/dd")'), ["info"])
        self.assertEqual(hits(f"={label}{amp}CStr(Globals!PageNumber)"), [])
        self.assertEqual(hits('=IIf(Fields!A.Value, "\u0646\u0639\u0645", "\u0644\u0627")'), [])  # not concatenated
        self.assertEqual(hits(f'="Key: "{amp}{key}', param("Key")), [])                    # no right-to-left text
        for mark in ("ChrW(8234)", "ChrW(8206)", "chrw( &amp;H202A )", "ChrW(8296)", "\u200e"):
            self.assertEqual(hits(f"={label}{amp}{mark}{amp}{key}", param("Key")), [], mark)
        self.assertEqual(hits(f"={label}{amp}ChrW(8212){amp}{key}", param("Key")), ["warning"])  # a dash is no mark

    def test_cli_expect_params(self):
        path = "tests/fixtures/rules/panel_fixed_2016.rdl"
        ok = self._cli("--file", path, "--json", "--expect-params", "UserId, FromDate,ToDate,BranchId,IsMain")
        self.assertEqual((ok.returncode, json.loads(ok.stdout)["status"]), (0, "PASS"))
        bad = self._cli("--file", path, "--json", "--expect-params", "UserId,FromDate,ToDate,BranchId,IsMain,PrintedAt")
        self.assertEqual(bad.returncode, 1)
        self.assertEqual([f["rule"] for f in json.loads(bad.stdout)["files"][0]["findings"]], ["RDL023"])
        root = self._cli("--root", "tests/fixtures/rules", "--expect-params", "UserId")
        self.assertEqual(root.returncode, 1)
        self.assertEqual(json.loads(root.stderr)["error"], "ValueError")

    # ---- CLI ----
    def _cli(self, *args):
        return subprocess.run([sys.executable, str(REPO / "scripts" / "rdl_validate.py"), *args],
                              capture_output=True, text=True, cwd=REPO)

    def test_cli_file_pass_and_root_fail(self):
        ok = self._cli("--file", "tests/fixtures/rdl/valid_2016.rdl", "--json")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(ok.stdout)["status"], "PASS")
        bad = self._cli("--root", "tests/fixtures/rdl", "--json")
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(json.loads(bad.stdout)["status"], "FAIL")
        human = self._cli("--root", "tests/fixtures/rdl")
        self.assertIn("FAIL broken_refs_2016.rdl", human.stdout)
        self.assertIn("error RDL011", human.stdout)

    def test_cli_rules_and_errors(self):
        r = self._cli("--rules")
        self.assertEqual(r.returncode, 0)
        self.assertGreaterEqual(len(json.loads(r.stdout)["rules"]), 20)
        missing = self._cli("--file", "tests/fixtures/rdl/nope.rdl", "--json")
        self.assertEqual(missing.returncode, 1)
        self.assertEqual(json.loads(missing.stderr)["status"], "FAIL")

    def test_cli_incomplete_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = self._cli("--root", tmp, "--json")
            human = self._cli("--root", tmp)
        self.assertEqual(empty.returncode, 2, empty.stderr)
        doc = json.loads(empty.stdout)
        self.assertEqual(doc["status"], "INCOMPLETE")
        self.assertFalse(doc["coverage_complete"])
        self.assertIn("coverage incomplete", human.stdout)


if __name__ == "__main__":
    unittest.main()
