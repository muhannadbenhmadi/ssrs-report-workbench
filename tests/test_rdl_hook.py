"""Synthetic, offline tests for the PostToolUse RDL hook."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.rdl_hook import build_context, run

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures" / "rdl"
BROKEN = FIXTURES / "broken_refs_2016.rdl"
VALID = FIXTURES / "valid_2016.rdl"


def payload(path, tool="Write", **extra) -> str:
    data = {"session_id": "s", "cwd": str(REPO), "hook_event_name": "PostToolUse",
            "tool_name": tool, "tool_input": {"file_path": str(path)}, "tool_response": {}}
    data.update(extra)
    return json.dumps(data)


class RdlHookTests(unittest.TestCase):
    def test_non_rdl_path_returns_empty(self):
        self.assertEqual(run(payload("foo.py")), "")
        self.assertIsNone(build_context({"tool_input": {"file_path": "foo.py"}}))

    def test_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(run(payload(Path(d) / "nope.rdl")), "")

    def test_missing_file_path_returns_empty(self):
        self.assertEqual(run(json.dumps({"tool_input": {}})), "")

    def test_rdl_file_returns_context_json(self):
        out = json.loads(run(payload(BROKEN)))
        hso = out["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], "PostToolUse")
        ctx = hso["additionalContext"]
        self.assertIn("RDL011", ctx)
        self.assertTrue(ctx.startswith("SSRS Report Workbench rdl-validate: broken_refs_2016.rdl -> FAIL"))
        self.assertIn("/ssrs-report-workbench:validate-rdl", ctx.splitlines()[-1])

    def test_valid_file_reports_pass(self):
        ctx = json.loads(run(payload(VALID, tool="Edit")))["hookSpecificOutput"]["additionalContext"]
        self.assertIn("-> PASS (0 errors", ctx)

    def test_relative_path_resolved_against_cwd(self):
        data = json.loads(payload(BROKEN))
        data["tool_input"]["file_path"] = "tests/fixtures/rdl/broken_refs_2016.rdl"
        self.assertIn("RDL011", run(json.dumps(data)))

    def test_output_never_contains_connect_string_value(self):
        out = run(payload(BROKEN))
        self.assertNotIn("secret", out)
        self.assertNotIn("Initial Catalog", out)

    def test_malformed_stdin_returns_empty(self):
        self.assertEqual(run("not json"), "")
        self.assertEqual(run(""), "")
        self.assertEqual(run("[1, 2]"), "")
        self.assertEqual(run('{"tool_input": "x"}'), "")

    def test_context_capped(self):
        boxes = "".join(
            f'<Textbox Name="Dup"><Paragraphs><Paragraph><TextRuns><TextRun><Value>x{"y" * 40}</Value>'
            f'</TextRun></TextRuns></Paragraph></Paragraphs></Textbox>' for _ in range(100))
        xml = ('<?xml version="1.0" encoding="utf-8"?><Report xmlns="http://schemas.microsoft.com/'
               'sqlserver/reporting/2016/01/reportdefinition"><ReportSections><ReportSection>'
               f'<Body><Height>2in</Height><ReportItems>{boxes}</ReportItems></Body>'
               '<Width>6in</Width></ReportSection></ReportSections></Report>')
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "many.rdl"
            p.write_text(xml, encoding="utf-8")
            ctx = json.loads(run(payload(p)))["hookSpecificOutput"]["additionalContext"]
        self.assertLessEqual(len(ctx), 4000)
        self.assertLessEqual(len([l for l in ctx.splitlines() if l.startswith("- ")]), 15)

    def test_main_exit_zero(self):
        script = REPO / "scripts" / "rdl_hook.py"
        for stdin, expect_output in ((payload(BROKEN), True), ("garbage", False), (payload("a.py"), False)):
            with tempfile.TemporaryDirectory() as d:
                r = subprocess.run([sys.executable, str(script)], input=stdin, capture_output=True,
                                   text=True, cwd=d)
            self.assertEqual(r.returncode, 0)
            self.assertEqual(bool(r.stdout.strip()), expect_output)

    def test_hooks_json_shape(self):
        data = json.loads((REPO / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        entry = data["hooks"]["PostToolUse"][0]
        self.assertEqual(entry["matcher"], "Write|Edit")
        self.assertIn("${CLAUDE_PLUGIN_ROOT}", entry["hooks"][0]["command"])


if __name__ == "__main__":
    unittest.main()
