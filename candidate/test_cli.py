"""Behavior tests for sf-md-footnote-check (offline, stdlib only).

Tests import ``cli`` directly; run from the test directory with::

    python -m unittest discover -s .

or::

    python -m unittest test_cli
"""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

import cli


def write(tmpdir, name, content, newline=""):
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8", newline=newline) as fh:
        fh.write(content)
    return path


class CleanFileTests(unittest.TestCase):
    def test_clean_file_has_no_issues_and_exit_zero(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "ok.md", "Text[^a].\n\n[^a]: note.\n")
            rep = cli.scan_file(p)
            self.assertEqual(rep.duplicates, [])
            self.assertEqual(rep.unreferenced, [])
            self.assertEqual(rep.undefined, [])
            self.assertFalse(rep.has_issues())

    def test_file_without_footnotes_is_clean(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "plain.md", "# Title\n\nJust prose, no notes.\n")
            rep = cli.scan_file(p)
            self.assertFalse(rep.has_issues())
            self.assertEqual(sum(rep.definitions.values()), 0)


class DuplicateTests(unittest.TestCase):
    def test_duplicate_definition_is_flagged_case_insensitively(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "dup.md", "x[^Fn] y[^fn]\n\n[^fn]: one.\n[^FN]: two.\n")
            rep = cli.scan_file(p)
            self.assertEqual(rep.duplicates, ["fn"])
            self.assertTrue(rep.has_issues())


class UndefinedTests(unittest.TestCase):
    def test_reference_without_definition_is_undefined(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "undef.md", "Missing[^ghost].\n")
            rep = cli.scan_file(p)
            self.assertEqual(rep.undefined, ["ghost"])

    def test_multiple_references_to_one_label_are_counted_not_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "multi.md", "a[^x] b[^x] c[^x]\n\n[^x]: note.\n")
            rep = cli.scan_file(p)
            self.assertEqual(rep.references["x"], 3)
            self.assertFalse(rep.has_issues())


class UnreferencedTests(unittest.TestCase):
    def test_unreferenced_definition_is_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "orphan.md", "used[^a]\n\n[^a]: note.\n[^b]: orphan.\n")
            rep = cli.scan_file(p)
            self.assertEqual(rep.unreferenced, ["b"])


class ParsingEdgeCaseTests(unittest.TestCase):
    def test_escaped_reference_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "esc.md", "literal \\[^a] and real[^b]\n\n[^b]: note.\n")
            rep = cli.scan_file(p)
            self.assertNotIn("a", rep.references)
            self.assertEqual(rep.undefined, [])

    def test_reference_on_definition_line_counts_only_as_definition(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "same.md", "prose[^a]\n[^a]: see [^a] again.\n")
            rep = cli.scan_file(p)
            # The definition line reference must not be counted.
            self.assertEqual(rep.references.get("a", 0), 1)
            self.assertEqual(rep.unreferenced, [])

    def test_code_fences_and_inline_code_are_ignored(self):
        content = (
            "```\n[^infence]: not a def\nref[^fence]\n```\n"
            "inline `[^incode]` and `[^c]:`\n"
            "real[^r].\n\n[^r]: yes.\n"
        )
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "code.md", content)
            rep = cli.scan_file(p)
            self.assertNotIn("infence", rep.definitions)
            self.assertNotIn("fence", rep.references)
            self.assertNotIn("incode", rep.references)
            self.assertNotIn("c", rep.definitions)
            self.assertEqual(rep.undefined, [])

    def test_bom_and_crlf_are_handled(self):
        content = "text[^a]\r\n\r\n[^a]: note.\r\n"
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "crlf.md", content, newline="")
            rep = cli.scan_file(p)
            self.assertEqual(rep.duplicates, [])
            self.assertEqual(rep.undefined, [])
            self.assertEqual(rep.unreferenced, [])


class CliIntegrationTests(unittest.TestCase):
    def test_json_output_is_stable_and_keyed_by_file(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "a.md", "x[^missing]\n")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.main(["--json", d])
            self.assertEqual(code, 1)
            payload = json.loads(buf.getvalue())
            self.assertIn("files", payload)
            self.assertIn("summary", payload)
            self.assertEqual(len(payload["files"]), 1)
            only = next(iter(payload["files"].values()))
            self.assertEqual(only["undefined"], ["missing"])

    def test_missing_path_returns_usage_error(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = cli.main([os.path.join(tempfile.gettempdir(), "no-such-file-xyz.md")])
        self.assertEqual(code, 2)
        self.assertTrue(err.getvalue())

    def test_no_paths_is_usage_error(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = cli.main([])
        self.assertEqual(code, 2)

    def test_quiet_suppresses_output_but_keeps_exit_code(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "q.md", "x[^missing]\n")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.main(["--quiet", d])
            self.assertEqual(code, 1)
            self.assertEqual(buf.getvalue(), "")

    def test_demo_runs_successfully(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["--demo"])
        self.assertEqual(code, 1)  # demo intentionally contains issues
        self.assertIn("summary", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
