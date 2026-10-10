#!/usr/bin/env python3
"""sf-md-footnote-check: offline Markdown footnote label linter.

Scans one or more Markdown files (or directories recursively) and reports
footnote label problems that are easy to miss before rendering:

  * duplicate definitions of the same normalized label
  * definitions that are never referenced
  * references that are never defined

The tool is deliberately dependency-free (Python standard library only),
does not touch the network, and never modifies the input paths it is given.
(``--demo`` is the one exception: it writes its own synthetic files under a
fresh temporary directory and deletes them again; it never touches your
files.)

Usage:
    python cli.py [--json] [--quiet] PATH [PATH ...]
    python cli.py --demo
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field

PROG = "sf-md-footnote-check"
MARKDOWN_EXTS = (".md", ".markdown")

# A definition label: letters, digits, underscore, hyphen, 1-64 chars.
# The optional up-to-3-space indent is handled separately.
_LABEL = r"[A-Za-z0-9_-]{1,64}"

# Definition: line-leading (after <=3 spaces) [^label]:
_DEF_RE = re.compile(r"^ {0,3}\[\^(" + _LABEL + r")\]:")
# Reference: [^label], optionally escaped by preceding backslashes.
# A run of an odd number of backslashes escapes the opening bracket; an even
# number leaves it unescaped.  Escaping is validated in `_iter_references`.
_REF_RE = re.compile(r"(\\*)\[\^(" + _LABEL + r")\]")
# Fence open/close: ``` or ~~~ (>=3), possibly indented <=3 spaces.
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_INLINE_CODE_RE = re.compile(r"`+[^`]*`+")


def normalize_label(label: str) -> str:
    """Return the canonical form used for comparing labels."""
    return label.strip().lower()


def _strip_inline_code(line: str) -> str:
    """Remove inline code spans (backtick-delimited) from a line.

    Replacing with a single space preserves character positions, so a
    `[^x]:` that sits inside an inline code span cannot be mistaken for a
    definition after stripping.
    """
    return _INLINE_CODE_RE.sub(" ", line)


def _iter_references(code_free: str):
    """Yield normalized labels for unescaped references in *code_free*.

    A reference is escaped when it is preceded by an odd number of
    backslashes (that is, the immediately preceding backslash escapes the
    opening ``[``).  An even number of backslashes leaves the ``[`` literal
    and therefore still counts as a reference.
    """
    for match in _REF_RE.finditer(code_free):
        backslashes = match.group(1)
        if len(backslashes) % 2 == 1:
            continue
        yield normalize_label(match.group(2))


def _iter_lines(handle, chunk_size: int = 65536):
    """Yield lines from *handle*, splitting on CR, LF, or CRLF.

    The file is consumed in fixed-size chunks so very large inputs are
    streamed rather than loaded in full.  Lines are split on lone ``\\r`` as
    well as ``\\n`` (including ``\\r\\n``), so files that use old-Mac style
    line endings are handled.
    """
    pending = ""
    while True:
        chunk = handle.read(chunk_size)
        if not chunk:
            break
        pending += chunk
        # Keep any trailing partial line (after the last recognised break).
        start = 0
        index = 0
        length = len(pending)
        while index < length:
            ch = pending[index]
            if ch == "\r":
                if index + 1 >= length:
                    # Might be a CRLF split across chunks; keep it pending.
                    break
                yield pending[start:index]
                if pending[index + 1] == "\n":
                    index += 2
                else:
                    index += 1
                start = index
            elif ch == "\n":
                yield pending[start:index]
                index += 1
                start = index
            else:
                index += 1
        pending = pending[start:]
    if pending:
        yield pending


@dataclass
class FileReport:
    """Collected footnote data for a single file.

    ``definitions`` and ``references`` hold the raw per-file label counts.
    ``unreferenced_labels`` and ``undefined_labels`` are filled in by
    :func:`finalize`, which resolves them against the *whole* set of scanned
    files so that a label defined in one file and referenced in another is
    not falsely reported.  A report produced by :func:`scan_file` on its own
    is finalized against itself (single-file semantics).
    """

    path: str
    definitions: dict = field(default_factory=dict)   # norm label -> count
    references: dict = field(default_factory=dict)     # norm label -> count
    duplicate_labels: set = field(default_factory=set)
    unreferenced_labels: list = field(default_factory=list)
    undefined_labels: list = field(default_factory=list)

    @property
    def duplicates(self) -> list:
        return sorted(self.duplicate_labels)

    @property
    def unreferenced(self) -> list:
        return list(self.unreferenced_labels)

    @property
    def undefined(self) -> list:
        return list(self.undefined_labels)

    def has_issues(self) -> bool:
        return bool(self.duplicate_labels or self.unreferenced_labels or self.undefined_labels)

    def to_dict(self) -> dict:
        return {
            "duplicates": self.duplicates,
            "unreferenced": self.unreferenced,
            "undefined": self.undefined,
            "definition_count": sum(self.definitions.values()),
            "reference_count": sum(self.references.values()),
        }


def finalize(reports) -> None:
    """Resolve unreferenced/undefined labels across *all* reports in place.

    A label counts as "defined" (or "referenced") if it is defined
    (referenced) in *any* of the supplied files.  This keeps folder scans
    self-consistent: a footnote defined in one file and cited in another is
    reported as neither undefined nor unreferenced.

    Duplicate definitions remain file-scoped: defining the same label twice
    in one document is flagged, whereas reusing a label in two separate
    documents is not.
    """
    defined = set()
    referenced = set()
    for rep in reports:
        defined.update(rep.definitions)
        referenced.update(rep.references)
    for rep in reports:
        rep.unreferenced_labels = sorted(l for l in rep.definitions if l not in referenced)
        rep.undefined_labels = sorted(l for l in rep.references if l not in defined)



def scan_file(path: str) -> FileReport:
    """Stream a file line by line and collect definition/reference info.

    Raises OSError if the file cannot be read.
    """
    report = FileReport(path=path)
    fence_char = None
    fence_len = 0

    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        for line in _iter_lines(fh):
            fence = _FENCE_RE.match(line)
            if fence:
                marker = fence.group(1)
                char = marker[0]
                length = len(marker)
                if fence_char is None:
                    fence_char, fence_len = char, length
                    continue
                elif char == fence_char and length >= fence_len:
                    fence_char, fence_len = None, 0
                    continue
            if fence_char is not None:
                # Inside a fenced code block: ignore entirely.
                continue

            code_free = _strip_inline_code(line)

            m = _DEF_RE.match(code_free)
            if m:
                norm = normalize_label(m.group(1))
                report.definitions[norm] = report.definitions.get(norm, 0) + 1
                if report.definitions[norm] > 1:
                    report.duplicate_labels.add(norm)
                # A reference on the definition line is not counted as a
                # separate reference; skip reference scanning for this line.
                continue

            for norm in _iter_references(code_free):
                report.references[norm] = report.references.get(norm, 0) + 1

    # Single-file semantics: a standalone scan resolves against itself.
    # Callers scanning several files call ``finalize`` again on the full set.
    finalize([report])
    return report


def collect_paths(paths) -> list:
    """Expand directories recursively into Markdown file paths."""
    files = []
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, names in os.walk(p):
                for name in sorted(names):
                    if name.lower().endswith(MARKDOWN_EXTS):
                        files.append(os.path.join(root, name))
        else:
            files.append(p)
    return files


def render_text(reports) -> str:
    lines = []
    total_defs = total_refs = 0
    total_dupes = total_unref = total_undef = 0

    for rep in reports:
        total_defs += sum(rep.definitions.values())
        total_refs += sum(rep.references.values())
        total_dupes += len(rep.duplicates)
        total_unref += len(rep.unreferenced)
        total_undef += len(rep.undefined)

        lines.append(rep.path)
        if not rep.has_issues() and not rep.definitions and not rep.references:
            lines.append("  clean: no footnotes found")
        elif not rep.has_issues():
            lines.append(
                "  clean: %d definition(s), %d reference(s)"
                % (sum(rep.definitions.values()), sum(rep.references.values()))
            )
        else:
            if rep.duplicates:
                lines.append("  duplicates: " + ", ".join("[^%s]" % l for l in rep.duplicates))
            if rep.unreferenced:
                lines.append("  unreferenced: " + ", ".join("[^%s]" % l for l in rep.unreferenced))
            if rep.undefined:
                lines.append("  undefined: " + ", ".join("[^%s]" % l for l in rep.undefined))
        lines.append(
            "  definitions=%d references=%d"
            % (sum(rep.definitions.values()), sum(rep.references.values()))
        )

    lines.append("")
    lines.append("summary")
    lines.append("  files=%d definitions=%d references=%d" % (len(reports), total_defs, total_refs))
    lines.append(
        "  duplicate_labels=%d unreferenced=%d undefined=%d"
        % (total_dupes, total_unref, total_undef)
    )
    return "\n".join(lines)


def render_json(reports) -> str:
    payload = {}
    global_summary = {
        "duplicates": 0,
        "unreferenced": 0,
        "undefined": 0,
        "definition_count": 0,
        "reference_count": 0,
    }
    for rep in reports:
        payload[rep.path] = rep.to_dict()
        global_summary["duplicates"] += len(rep.duplicates)
        global_summary["unreferenced"] += len(rep.unreferenced)
        global_summary["undefined"] += len(rep.undefined)
        global_summary["definition_count"] += sum(rep.definitions.values())
        global_summary["reference_count"] += sum(rep.references.values())
    return json.dumps(
        {"files": payload, "summary": global_summary},
        indent=2,
        sort_keys=True,
    )


def run_demo() -> int:
    """Exercise the scanner on synthetic data written to a temp directory.

    Creates a fresh directory via :func:`tempfile.mkdtemp`, writes a few
    synthetic ``.md``/``.markdown`` files into it, scans them with the same
    code path used for real inputs, prints a human report and a JSON view,
    then removes the files and the directory.  Your own files are never
    touched.  Returns 1 because the synthetic data deliberately contains
    issues.
    """
    import tempfile

    samples = {
        "intro.md": (
            "Intro\n\n"
            "See the note[^alpha] and again[^alpha].\n"
            "Also [^Beta] here.\n"
            "This one is never used.[^orphan]\n\n"
            "[^alpha]: A defined note.\n"
            "[^beta]: Defined with different case in the reference.\n"
            "[^orphan]: Defined but never referenced.\n"
            "[^ghost]: A second definition of alpha?\n"
        ),
        "code.md": (
            "Example:\n\n"
            "```\n"
            "[^notaref]: inside code\n"
            "```\n"
            "Real text[^real].\n\n"
            "[^real]: the real one.\n"
            "[^never-used]: orphan.\n"
        ),
        "notes.markdown": (
            "A missing target[^nope] and a duplicate.\n\n"
            "[^done]: first.\n"
            "[^DONE]: second definition, same label.\n"
        ),
    }

    reports = []
    tmpdir = tempfile.mkdtemp(prefix="sf-demo-")
    try:
        for name, content in samples.items():
            p = os.path.join(tmpdir, name)
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(content)
            reports.append(scan_file(p))
        finalize(reports)
        print("Demo: synthetic Markdown footnote audit (temp dir)")
        print()
        print(render_text(reports))
        print()
        print("JSON view:")
        print(render_json(reports))
    finally:
        for name in samples:
            try:
                os.remove(os.path.join(tmpdir, name))
            except OSError:
                pass
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass
    return 1 if any(r.has_issues() for r in reports) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Detect duplicate, unreferenced and undefined Markdown footnote labels.",
    )
    parser.add_argument("paths", nargs="*", help="Markdown files or directories")
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit a stable JSON object keyed by file path",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress normal output; rely on exit code",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="run a self-contained synthetic demonstration and exit",
    )
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()

    if not args.paths:
        parser.error("at least one PATH is required (or use --demo)")

    files = []
    for p in args.paths:
        if not os.path.exists(p):
            sys.stderr.write("error: path does not exist: %s\n" % p)
            return 2
        files.extend(collect_paths([p]))

    if not files:
        sys.stderr.write("error: no Markdown files found in the given paths\n")
        return 2

    reports = []
    for f in files:
        try:
            reports.append(scan_file(f))
        except OSError as exc:
            sys.stderr.write("error: cannot read %s: %s\n" % (f, exc))
            return 2

    # Resolve unreferenced/undefined labels across the whole input set so a
    # label defined in one file and cited in another is not misreported.
    finalize(reports)

    if not args.quiet:
        if args.json:
            print(render_json(reports))
        else:
            print(render_text(reports))

    return 1 if any(r.has_issues() for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
