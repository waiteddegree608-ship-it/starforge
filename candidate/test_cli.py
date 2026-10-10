"""Behavior tests for cli.py (sf-md-ref-inventory).

Run with:
    python -m unittest discover -s . -p "test_*.py"
or simply:
    python test_cli.py

All tests build temporary Markdown/BibTeX content under a temp directory;
nothing is written outside it.
"""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

import cli


class ExtractionTests(unittest.TestCase):
    """Unit-level checks on the lexing/extraction helpers."""

    def test_strip_code_blanks_fences_and_inline(self):
        src = (
            "visible @keep\n"
            "```\n"
            "@hidden\n"
            "```\n"
            "`@inline-hidden` and @also-keep\n"
        )
        stripped = cli.strip_code(src)
        cites = cli.extract_citations(stripped)
        self.assertIn("keep", cites)
        self.assertIn("also-keep", cites)
        self.assertNotIn("hidden", cites)
        self.assertNotIn("inline-hidden", cites)

    def test_citations_ignore_emails(self):
        cites = cli.extract_citations("mail user@example.com and cite @real")
        self.assertIn("real", cites)
        self.assertNotIn("example", cites)

    def test_bracket_and_semicolon_citations(self):
        cites = cli.extract_citations("[@a; @b, p. 3] and [@c]")
        self.assertEqual(sorted(cites), ["a", "b", "c"])

    def test_definitions_from_heading_attribute_and_div(self):
        text = (
            "# Title {#sec-a}\n"
            "para {#fig-b .wide}\n"
            "::: {#div-c}\n"
            "x\n"
            ":::\n"
            "heading without id {not-an-id}\n"
            "## Plain heading\n"
        )
        defs = cli.extract_definitions(text)
        ids = {i for _, i in defs}
        self.assertIn("sec-a", ids)
        self.assertIn("fig-b", ids)
        self.assertIn("div-c", ids)
        # attribute without '#' is not an id
        self.assertNotIn("not-an-id", ids)


class AnalyzeTests(unittest.TestCase):
    """End-to-end analysis on constructed projects."""

    def _write(self, root, name, content):
        p = Path(root) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def test_duplicates_undefined_and_unused(self):
        with tempfile.TemporaryDirectory() as td:
            self._write(
                td,
                "a.md",
                "# One {#sec-x}\n"
                "See [link](#broken-here) and [good](#sec-y).\n"
                "Cite [@k1].\n",
            )
            self._write(
                td,
                "b.md",
                "# Two {#sec-x}\n"   # duplicate of sec-x
                "## Used {#sec-y}\n"
                "## Never {#sec-orphan}\n",
            )
            files = cli.collect_files([td])
            result = cli.analyze(files)

            dup_ids = [d["id"] for d in result["duplicates"]]
            self.assertEqual(dup_ids, ["sec-x"])

            undef_ids = [d["id"] for d in result["undefined_refs"]]
            self.assertEqual(undef_ids, ["broken-here"])

            unused_ids = [d["id"] for d in result["unused_labels"]]
            # sec-orphan unused; sec-x is "used" only as a duplicate definition
            self.assertIn("sec-orphan", unused_ids)

    def test_no_matches_is_empty_and_success(self):
        with tempfile.TemporaryDirectory() as td:
            self._write(td, "clean.md", "Just prose, nothing special here.\n")
            result = cli.analyze(cli.collect_files([td]))
            self.assertEqual(result["duplicates"], [])
            self.assertEqual(result["undefined_refs"], [])
            self.assertEqual(result["unused_labels"], [])
            self.assertEqual(result["summary"]["duplicates"], 0)

    def test_bib_check_flags_missing_and_uncited(self):
        with tempfile.TemporaryDirectory() as td:
            self._write(td, "doc.md", "Cite [@present] and [@absent].\n")
            bib = self._write(
                td,
                "refs.bib",
                "@article{present, title={P}}\n"
                "@book{never, title={N}}\n",
            )
            result = cli.analyze(
                cli.collect_files([td]), check_bib=True, bib_path=bib
            )
            not_found = [d["key"] for d in result["bib"]["not_found"]]
            uncited = [d["key"] for d in result["bib"]["uncited"]]
            self.assertEqual(not_found, ["absent"])
            self.assertEqual(uncited, ["never"])
            self.assertIn("present", result["bib"]["entries"])

    def test_unreadable_file_reported(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad.md"
            bad.write_bytes(b"\xff\xfe\x00 broken utf-8 \xff")
            result = cli.analyze(cli.collect_files([td]))
            self.assertTrue(result["read_errors"])
            self.assertEqual(result["files"], [str(bad)])


class CliTests(unittest.TestCase):
    """Command-line behavior, including failure/edge cases."""

    def test_help_exits_zero(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cli.main(["--help"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("usage", buf.getvalue().lower())

    def test_no_paths_usage_error_exit_2(self):
        err = io.StringIO()
        with redirect_stderr(err):
            with self.assertRaises(SystemExit) as cm:
                cli.main([])
        self.assertEqual(cm.exception.code, 2)

    def test_demo_prints_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = os.getcwd()
            before = set(os.listdir(td))
            os.chdir(td)
            try:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cli.main(["--demo"])
                after = set(os.listdir(td))
            finally:
                os.chdir(cwd)
            self.assertEqual(rc, 0)
            out = buf.getvalue()
            self.assertIn("Summary", out)
            self.assertIn("Duplicate labels", out)
            # nothing written in the temp cwd
            self.assertEqual(before, after)

    def test_json_output_and_out_file(self):
        with tempfile.TemporaryDirectory() as td:
            md = Path(td) / "d.md"
            md.write_text("Cite [@a].\n# H {#sec-1}\n", encoding="utf-8")
            out_file = Path(td) / "out.json"
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(
                    ["--format", "json", "--out", str(out_file), str(md)]
                )
            self.assertEqual(rc, 0)
            data = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertIn("labels_defined", data)
            self.assertIn("summary", data)

    def test_missing_path_exit_1(self):
        with tempfile.TemporaryDirectory() as td:
            err = io.StringIO()
            with redirect_stderr(err):
                rc = cli.main([str(Path(td) / "does-not-exist.md")])
            self.assertEqual(rc, 1)
            self.assertIn("not found", err.getvalue().lower())


if __name__ == "__main__":
    unittest.main()
