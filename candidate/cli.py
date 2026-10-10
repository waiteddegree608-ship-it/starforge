#!/usr/bin/env python3
"""sf-md-ref-inventory: offline citation-key and cross-reference inventory.

Scans Markdown / Quarto / plain-text files and reports:
  * where labels (anchors / ids) are defined
  * duplicate label definitions
  * references pointing at labels with no definition
  * labels that are defined but never referenced
  * optionally, whether citation keys agree with a simple BibTeX file

Standard library only. No network access. No writes unless --out is given.
Exit codes:
    0  normal completion (even when findings exist)
    1  an input could not be read / decoded, or --bib was unreadable
    2  usage error (e.g. no input paths)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SUPPORTED_SUFFIXES = {".md", ".markdown", ".qmd", ".txt"}

# ---------------------------------------------------------------------------
# Lexing helpers: strip fenced code blocks and inline code spans first so that
# patterns appearing inside code are never counted.
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^([ \t]*)(`{3,}|~{3,})")
_INLINE_CODE_RE = re.compile(r"(?<!`)(`+)(?!`).*?\1(?!`)", re.DOTALL)


def _blank_preserving_newlines(text: str) -> str:
    """Replace every non-newline character with a space."""
    return "".join("\n" if ch == "\n" else " " for ch in text)


def strip_code(text: str) -> str:
    """Return text with fenced blocks and inline code spans blanked out.

    Newlines and character positions are preserved so line numbers computed
    on the result still match the original file.
    """
    out_lines = []
    in_fence = False
    fence_char = ""
    fence_len = 0

    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        newline = line[len(body):]
        if not in_fence:
            m = _FENCE_RE.match(body)
            if m:
                in_fence = True
                fence_char = m.group(2)[0]
                fence_len = len(m.group(2))
                out_lines.append(_blank_preserving_newlines(line))
                continue
            stripped = _INLINE_CODE_RE.sub(
                lambda mm: _blank_preserving_newlines(mm.group(0)), body
            )
            out_lines.append(stripped + newline)
        else:
            # Closing fence: same char, at least as long, nothing else on line.
            candidate = body.strip()
            if (
                candidate
                and candidate[0] == fence_char
                and len(candidate) >= fence_len
                and set(candidate) == {fence_char}
            ):
                in_fence = False
            out_lines.append(_blank_preserving_newlines(line))

    return "".join(out_lines)


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Pandoc attribute: {#id}, {.class #id}, {#id .class k=v}
_ATTR_BLOCK_RE = re.compile(r"\{([^{}\n]*#[A-Za-z][\w:.\-]*[^{}\n]*)\}")
_ATTR_ID_RE = re.compile(r"#([A-Za-z][\w:.\-]*)")

_HEADING_RE = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]")

_DIV_RE = re.compile(r"^[ \t]*:::+[ \t]*\{([^{}\n]*)\}")

# Citation keys: [@key], [@key, p. 3], [@a; @b], and bare @key
_BRACKET_CITE_RE = re.compile(r"\[([^\[\]\n]*@[^\[\]\n]*)\]")
_AT_CITE_RE = re.compile(r"(?<![\w@])@([A-Za-z][\w:.\-]*)")

# Link targets: [text](#id)
_LINK_TARGET_RE = re.compile(r"\]\(#([A-Za-z][\w:.\-]*)\)")


# A local-part character that may sit directly before an '@' in an email.
_EMAIL_LOCAL_RE = re.compile(r"[A-Za-z0-9._%+\-]")
# Domain: labels separated by dots, ending in a 2+ letter TLD.
_EMAIL_DOMAIN_RE = re.compile(r"(?:[A-Za-z0-9\-]+\.)+[A-Za-z]{2,}")


def _email_context(text: str, at_index: int) -> bool:
    """True if the '@' at at_index looks like it sits inside an email address.

    Requires a non-empty local part immediately before the '@' *and* an
    email-like domain (at least one dot plus a letter TLD) after it. This keeps
    ordinary citations such as ``@smith2020`` from being mistaken for email.
    """
    if at_index == 0:
        return False
    before = text[at_index - 1]
    if not _EMAIL_LOCAL_RE.fullmatch(before):
        return False
    return _EMAIL_DOMAIN_RE.match(text, at_index + 1) is not None


def _cite_keys_in_brackets(inner: str):
    """Yield citation keys from the inside of a [...] fragment."""
    for m in _AT_CITE_RE.finditer(inner):
        if _email_context(inner, m.start()):
            continue
        yield m.group(1)


def _bare_at_tokens(stripped: str):
    """Yield (line_no, id) for bare @id tokens not inside [...] or emails.

    Bracket citation keys are handled separately so that ``[@key]`` is not
    reported twice. The ``@id`` tokens yielded here double as both citation
    keys and cross-reference uses: a Pandoc/Quarto ``@fig-x`` is a citation of
    the ``fig-x`` label, so a bare ``@id`` also counts as a use of that label.
    """
    for line_no, line in enumerate(stripped.splitlines(), start=1):
        scrubbed = _BRACKET_CITE_RE.sub(lambda mm: " " * len(mm.group(0)), line)
        for m in _AT_CITE_RE.finditer(scrubbed):
            if _email_context(scrubbed, m.start()):
                continue
            yield line_no, m.group(1)


def extract_citations(stripped: str):
    """Return {key: [line numbers]} for citation keys in cleaned text."""
    found = {}
    for line_no, line in enumerate(stripped.splitlines(), start=1):
        for bm in _BRACKET_CITE_RE.finditer(line):
            for key in _cite_keys_in_brackets(bm.group(1)):
                found.setdefault(key, []).append(line_no)
    for line_no, key in _bare_at_tokens(stripped):
        found.setdefault(key, []).append(line_no)
    return found


def extract_definitions(stripped: str):
    """Return (list of (line, id)). Includes attributes, fenced divs, headings."""
    defs = []
    for line_no, line in enumerate(stripped.splitlines(), start=1):
        if not line.strip():
            continue
        div = _DIV_RE.match(line)
        if div:
            for m in _ATTR_ID_RE.finditer(div.group(1)):
                defs.append((line_no, m.group(1)))
            continue
        if _HEADING_RE.match(line):
            for m in _ATTR_ID_RE.finditer(line):
                defs.append((line_no, m.group(1)))
            continue
        for am in _ATTR_BLOCK_RE.finditer(line):
            for m in _ATTR_ID_RE.finditer(am.group(1)):
                defs.append((line_no, m.group(1)))
    return defs


def extract_references(stripped: str):
    """Return list of (line, id) for every reference use of a label.

    A label is *used* when it appears as:
      * a link target ``[text](#id)``; or
      * a bare cross-reference token ``@id`` (Pandoc/Quarto attribute refs).
    """
    refs = []
    for line_no, line in enumerate(stripped.splitlines(), start=1):
        for m in _LINK_TARGET_RE.finditer(line):
            refs.append((line_no, m.group(1)))
    for line_no, ident in _bare_at_tokens(stripped):
        refs.append((line_no, ident))
    return refs


# ---------------------------------------------------------------------------
# BibTeX
# ---------------------------------------------------------------------------

_BIB_ENTRY_RE = re.compile(r"^\s*@[A-Za-z]+\s*\{\s*([^,\s}]+)\s*,", re.MULTILINE)


def parse_bibtex(text: str):
    """Return sorted list of top-level entry keys."""
    keys = set()
    for m in _BIB_ENTRY_RE.finditer(text):
        keys.add(m.group(1))
    return sorted(keys)


# ---------------------------------------------------------------------------
# File collection & IO
# ---------------------------------------------------------------------------

def collect_files(paths):
    """Expand paths (files and directories) into a sorted list of Paths.

    Raises FileNotFoundError if a path does not exist.
    """
    collected = set()
    for raw in paths:
        p = Path(raw)
        if not p.exists():
            raise FileNotFoundError(str(p))
        if p.is_dir():
            for child in p.rglob("*"):
                if child.is_file() and child.suffix.lower() in SUPPORTED_SUFFIXES:
                    collected.add(child)
        elif p.is_file():
            if p.suffix.lower() in SUPPORTED_SUFFIXES:
                collected.add(p)
    return sorted(collected, key=lambda x: str(x))


def read_text(path: Path) -> str:
    """Read as UTF-8; raise ValueError on decode failure."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path}: not valid UTF-8 ({exc})") from exc


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze(files, check_bib=False, bib_paths=None):
    """Run the inventory over already-collected files.

    ``bib_paths`` is an optional sequence of BibTeX files; all are parsed and
    their entry keys merged. Returns the result dict (without 'bib' unless
    check_bib).
    """
    labels_defined = []
    all_refs = []          # (file, line, id)
    cite_keys = {}         # key -> [(file, line), ...]
    read_errors = []
    analyzed_files = []    # files actually read and scanned

    for path in files:
        try:
            raw = read_text(path)
        except ValueError as exc:
            read_errors.append(str(exc))
            continue
        analyzed_files.append(path)
        stripped = strip_code(raw)
        for line_no, ident in extract_definitions(stripped):
            labels_defined.append({"id": ident, "file": str(path), "line": line_no})
        for line_no, ident in extract_references(stripped):
            all_refs.append({"id": ident, "file": str(path), "line": line_no})
        for key, lines in extract_citations(stripped).items():
            for ln in lines:
                cite_keys.setdefault(key, []).append({"file": str(path), "line": ln})

    # deterministic ordering
    labels_defined.sort(key=lambda d: (d["id"], d["file"], d["line"]))
    all_refs.sort(key=lambda d: (d["id"], d["file"], d["line"]))

    # duplicates: same id defined at two or more distinct locations
    by_id = {}
    for d in labels_defined:
        by_id.setdefault(d["id"], []).append(d)
    duplicates = [
        {"id": ident, "definitions": sorted(locs, key=lambda x: (x["file"], x["line"]))}
        for ident, locs in sorted(by_id.items())
        if len({(x["file"], x["line"]) for x in locs}) > 1
    ]

    defined_ids = set(by_id.keys())

    # undefined references: any [text](#id) with no matching definition
    undefined_refs = []
    seen_refs = set()
    for r in all_refs:
        if r["id"] in defined_ids:
            continue
        key = (r["id"], r["file"], r["line"])
        if key in seen_refs:
            continue
        seen_refs.add(key)
        undefined_refs.append(r)
    undefined_refs.sort(key=lambda d: (d["id"], d["file"], d["line"]))

    # unused labels: labels (ids) that are defined but never referenced.
    # This is label-based, not location-based: one entry per id, listing every
    # place the id is defined. An id referenced anywhere (link target or bare
    # @id) is not unused, even if it is also defined more than once.
    referenced_ids = {r["id"] for r in all_refs}
    unused_labels = []
    for ident in sorted(by_id.keys()):
        if ident not in referenced_ids:
            locs = sorted(by_id[ident], key=lambda x: (x["file"], x["line"]))
            unused_labels.append(
                {
                    "id": ident,
                    "definitions": [dict(loc) for loc in locs],
                }
            )

    result = {
        "files": [str(p) for p in analyzed_files],
        "labels_defined": labels_defined,
        "duplicates": duplicates,
        "undefined_refs": undefined_refs,
        "unused_labels": unused_labels,
    }

    if check_bib:
        bib_entries = []
        bib_not_found = []
        bib_uncited = []
        for bib_path in bib_paths or []:
            try:
                bib_text = read_text(bib_path)
            except (ValueError, OSError) as exc:
                read_errors.append(str(exc))
            else:
                bib_entries.extend(parse_bibtex(bib_text))
        bib_entries = sorted(set(bib_entries))
        bib_set = set(bib_entries)
        for key in sorted(cite_keys.keys()):
            if key not in bib_set:
                bib_not_found.append({"key": key, "uses": cite_keys[key]})
        for key in bib_entries:
            if key not in cite_keys:
                bib_uncited.append({"key": key})
        result["bib"] = {
            "entries": bib_entries,
            "not_found": bib_not_found,
            "uncited": bib_uncited,
        }

    result["read_errors"] = read_errors
    result["summary"] = _summarize(result)
    return result


def _summarize(result):
    summary = {
        "files": len(result["files"]),
        "labels_defined": len(result["labels_defined"]),
        "duplicates": len(result["duplicates"]),
        "undefined_refs": len(result["undefined_refs"]),
        "unused_labels": len(result["unused_labels"]),
    }
    if "bib" in result:
        summary["bib_entries"] = len(result["bib"]["entries"])
        summary["bib_not_found"] = len(result["bib"]["not_found"])
        summary["bib_uncited"] = len(result["bib"]["uncited"])
    return summary


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def render_text(result) -> str:
    lines = []
    lines.append("== Files ==")
    if result["files"]:
        for f in result["files"]:
            lines.append(f"  {f}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("== Labels defined ==")
    if result["labels_defined"]:
        for d in result["labels_defined"]:
            lines.append(f"  {d['id']}  {d['file']}:{d['line']}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("== Duplicate labels ==")
    if result["duplicates"]:
        for d in result["duplicates"]:
            locs = ", ".join(f"{x['file']}:{x['line']}" for x in d["definitions"])
            lines.append(f"  {d['id']}  ->  {locs}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("== Undefined references ==")
    if result["undefined_refs"]:
        for d in result["undefined_refs"]:
            lines.append(f"  {d['id']}  at {d['file']}:{d['line']}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("== Unused labels ==")
    if result["unused_labels"]:
        for d in result["unused_labels"]:
            locs = ", ".join(
                f"{x['file']}:{x['line']}" for x in d["definitions"]
            )
            lines.append(f"  {d['id']}  {locs}")
    else:
        lines.append("  (none)")

    if "bib" in result:
        lines.append("")
        lines.append("== Bibliography ==")
        lines.append(f"  entries: {', '.join(result['bib']['entries']) or '(none)'}")
        lines.append("  cited but missing from bib:")
        if result["bib"]["not_found"]:
            for d in result["bib"]["not_found"]:
                lines.append(f"    {d['key']}")
        else:
            lines.append("    (none)")
        lines.append("  bib entries never cited:")
        if result["bib"]["uncited"]:
            for d in result["bib"]["uncited"]:
                lines.append(f"    {d['key']}")
        else:
            lines.append("    (none)")

    if result.get("read_errors"):
        lines.append("")
        lines.append("== Read errors ==")
        for e in result["read_errors"]:
            lines.append(f"  {e}")

    lines.append("")
    s = result["summary"]
    lines.append(
        "== Summary == "
        f"files={s['files']} labels={s['labels_defined']} "
        f"duplicates={s['duplicates']} undefined_refs={s['undefined_refs']} "
        f"unused_labels={s['unused_labels']}"
        + (
            f" bib_entries={s.get('bib_entries')} bib_not_found={s.get('bib_not_found')}"
            f" bib_uncited={s.get('bib_uncited')}"
            if "bib" in result
            else ""
        )
    )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

_DEMO_FILES = {
    "intro.md": (
        "# Introduction {#sec-intro}\n"
        "\n"
        "See @fig-arch and the earlier work [@smith2020].\n"
        "Also [@alpha; @beta] and a bare mention of @gamma.\n"
        "\n"
        "An email like user@example.com must not count.\n"
        "\n"
        "```\n"
        "# Not a heading {#ghost}\n"
        "See @code-cite inside a fence.\n"
        "```\n"
        "\n"
        "Inline code: `[@inline] and @inline-too` should be ignored.\n"
        "\n"
        "Jump to [the method](#sec-method) or the broken [target](#nope).\n"
        "\n"
        "## Method {#sec-method}\n"
        "\n"
        "```{.python #lst-demo}\n"
        "print('hello')\n"
        "```\n"
    ),
    "figures.md": (
        "::: {#fig-arch}\n"
        "Architecture diagram placeholder.\n"
        ":::\n"
        "\n"
        "# Duplicate heading {#sec-intro}\n"
        "\n"
        "![Caption](img.png){#fig-orphan}\n"
        "\n"
        "See @smith2020 again.\n"
    ),
    "notes.txt": (
        "Plain text notes.\n"
        "Reference [here](#sec-method) and cite [@missing2024].\n"
    ),
    "references.bib": (
        "@article{smith2020,\n"
        "  title = {A Study},\n"
        "  author = {Smith, Jane},\n"
        "}\n"
        "\n"
        "@book{unused1999,\n"
        "  title = {Never Cited},\n"
        "}\n"
    ),
}

_DEMO_SOURCE = (
    "@article{alpha,\n  title = {Alpha},\n}\n"
    "@article{beta,\n  title = {Beta},\n}\n"
    "@article{gamma,\n  title = {Gamma},\n}\n"
    "@article{smith2020,\n  title = {A Study},\n}\n"
    "@book{unused1999,\n  title = {Never Cited},\n}\n"
)


def run_demo(fmt="text"):
    """Exercise the inventory on synthetic in-memory input. Prints results."""
    import io

    files = sorted(_DEMO_FILES)
    labels_defined = []
    all_refs = []
    cite_keys = {}

    for name in files:
        if name.endswith(".bib"):
            continue
        stripped = strip_code(_DEMO_FILES[name])
        for line_no, ident in extract_definitions(stripped):
            labels_defined.append({"id": ident, "file": name, "line": line_no})
        for line_no, ident in extract_references(stripped):
            all_refs.append({"id": ident, "file": name, "line": line_no})
        for key, lines in extract_citations(stripped).items():
            for ln in lines:
                cite_keys.setdefault(key, []).append({"file": name, "line": ln})

    labels_defined.sort(key=lambda d: (d["id"], d["file"], d["line"]))
    all_refs.sort(key=lambda d: (d["id"], d["file"], d["line"]))

    by_id = {}
    for d in labels_defined:
        by_id.setdefault(d["id"], []).append(d)
    duplicates = [
        {"id": k, "definitions": sorted(v, key=lambda x: (x["file"], x["line"]))}
        for k, v in sorted(by_id.items())
        if len({(x["file"], x["line"]) for x in v}) > 1
    ]
    defined_ids = set(by_id)
    undefined_refs = [
        r for r in all_refs if r["id"] not in defined_ids
    ]
    referenced_ids = {r["id"] for r in all_refs}
    unused_labels = [
        loc for ident in sorted(by_id) if ident not in referenced_ids
        for loc in sorted(by_id[ident], key=lambda x: (x["file"], x["line"]))
    ]

    bib_entries = parse_bibtex(_DEMO_SOURCE)
    bib_set = set(bib_entries)
    bib_not_found = [
        {"key": k, "uses": cite_keys[k]} for k in sorted(cite_keys) if k not in bib_set
    ]
    bib_uncited = [{"key": k} for k in bib_entries if k not in cite_keys]

    result = {
        "files": files,
        "labels_defined": labels_defined,
        "duplicates": duplicates,
        "undefined_refs": undefined_refs,
        "unused_labels": unused_labels,
        "bib": {
            "entries": bib_entries,
            "not_found": bib_not_found,
            "uncited": bib_uncited,
        },
        "read_errors": [],
    }
    result["summary"] = _summarize(result)

    print("sf-md-ref-inventory demo (in-memory synthetic project; nothing written)")
    print("Files: " + ", ".join(files))
    print()
    print(render_text(result), end="")

    if fmt == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description=(
            "Offline inventory of citation keys and cross-reference labels "
            "across Markdown / Quarto / text files."
        ),
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="files or directories to scan (directories are searched recursively)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="text",
        help="output format (default: text)",
    )
    parser.add_argument("--out", metavar="FILE", help="write output to FILE")
    parser.add_argument(
        "--check-bib",
        action="store_true",
        help="also compare citation keys with a BibTeX file",
    )
    parser.add_argument(
        "--bib",
        metavar="FILE",
        action="append",
        default=[],
        help="BibTeX file(s) to check (may be repeated)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="run a self-contained demo and print example output",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo(args.format)

    if not args.paths:
        parser.error("no input paths given (use --demo to try the tool)")

    check_bib = args.check_bib or bool(args.bib)

    try:
        files = collect_files(args.paths)
    except FileNotFoundError as exc:
        print(f"error: path not found: {exc}", file=sys.stderr)
        return 1

    bib_path = None
    if check_bib:
        if args.bib:
            bib_path = Path(args.bib[0])
            if not bib_path.exists():
                print(f"error: bib file not found: {bib_path}", file=sys.stderr)
                return 1
        else:
            print("error: --check-bib requires --bib FILE", file=sys.stderr)
            return 2

    result = analyze(files, check_bib=check_bib, bib_path=bib_path)

    if args.format == "json":
        output = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    else:
        output = render_text(result)

    if args.out:
        try:
            Path(args.out).write_text(output, encoding="utf-8")
        except OSError as exc:
            print(f"error: could not write {args.out}: {exc}", file=sys.stderr)
            return 1
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(output, end="")

    if result["read_errors"]:
        for e in result["read_errors"]:
            print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
