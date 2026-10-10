# sf-md-footnote-check

An offline, dependency-free Python command line tool that audits Markdown
footnote labels before you convert your documents. It scans one or more
`.md` / `.markdown` files (or directories, recursively) and reports three
classes of label problems that are easy to miss by eye:

- **duplicate definitions** — the same normalized label is defined more than once
- **unreferenced definitions** — a label is defined but never cited
- **undefined references** — a label is cited but never defined

This is an original, AI-assisted prototype. It was written from a short
specification describing the general friction found in document-conversion
pipelines, not copied from any existing project. It has no established
adoption, no user community, and makes no claim of accuracy or completeness.
Treat it as a starting point you can read, test, and adapt.

## Purpose

Repeated citations of the same footnote label, missing definitions, and
orphaned definitions often pass silently through Markdown source and only
surface after rendering. Checking them by hand across a folder is tedious.
This tool gives you a fast, local answer using only the Python standard
library — no network access, no third-party packages, no services. It never
modifies the paths you pass it; the only optional writes are the synthetic
files `--demo` creates in its own temporary directory (see below).

## Requirements

- Python 3.10 or newer
- Standard library only (no `pip install` needed)

## Quickstart

```sh
# Human-readable report over one file
python cli.py notes.md

# Scan a whole directory recursively
python cli.py docs/

# Machine-readable JSON
python cli.py --json docs/

# Exit-code only, for scripts and CI
python cli.py --quiet docs/

# Self-contained synthetic demonstration
python cli.py --demo

# Help
python cli.py --help
```

`--demo` creates a fresh temporary directory (`tempfile.mkdtemp`), writes a
few synthetic `.md`/`.markdown` files into it, scans them with the same logic
used for real files, prints a report and a JSON view, then removes those files
and the directory. It never touches the paths you pass to a normal run — but
note that it *does* write to disk (in the temp area), so it is not a
zero-write or input-free pure scan. It exercises duplicates, unreferenced
definitions, undefined references, case-insensitive labels, and
fenced/inline code so you can see the output without supplying input.

## Real example

Suppose `guide/intro.md` contains:

```markdown
See the note[^alpha] and again[^alpha]. A missing one[^ghost].

[^alpha]: First definition.
[^Alpha]: Second definition of the same label.
[^orphan]: Defined but never referenced.
```

Running:

```sh
python cli.py guide/
```

produces this report (shown exactly as printed):

```text
guide/intro.md
  duplicates: [^alpha]
  unreferenced: [^orphan]
  undefined: [^ghost]
  definitions=3 references=3

summary
  files=1 definitions=3 references=3
  duplicate_labels=1 unreferenced=1 undefined=1
```

(Single-file output uses whatever path you passed; here the file is rendered
as `guide/intro.md`.) The process exits with status `1`. With `--json` you
get a stable object keyed by file path; see `example.json` for the shape.

## Rules the parser applies

- Definitions are lines beginning with `[^label]:`, with 0–3 leading spaces.
- Labels use letters, digits, `_`, and `-`, 1–64 characters long.
- Labels are compared case-insensitively (normalized by lowercasing and
  trimming).
- A reference is `[^label]` that is not a definition line and not escaped
  with a preceding backslash.
- Content inside fenced code blocks (` ``` ` or `~~~`) and inside inline
  backtick code spans is ignored.
- A reference appearing on the same line as its own definition is not
  counted as a reference.
- Multiple references to one label are allowed and counted, never flagged.

## Exit codes

| Code | Meaning |
| ---- | ------- |
| 0 | No duplicates, no undefined references, no unreferenced definitions |
| 1 | At least one issue found |
| 2 | Usage error (no paths, nonexistent path) or an unreadable file |

Diagnostics for code `2` are written to stderr.

## Limitations

- This is a heuristic text scanner, not a full CommonMark parser. Indented
  code blocks (four-space), block quotes, and HTML blocks are not special-
  cased, so labels inside them may be counted.
- Footnote syntax varies between Markdown flavors; only the `[^label]`
  convention is recognized.
- Labels are normalized only by trimming and lowercasing.
- Files are read as UTF-8 (a leading BOM is accepted) and streamed line by
  line; unusual encodings with unreadable bytes are decoded leniently.
- No automatic fixing, no output rendering, and no network features.

## Testing

```sh
python -m unittest discover -s .
```

The suite imports `cli` directly, so run it from the test directory.

## License

MIT. This is an AI-assisted prototype provided as-is, with no warranty and
no guarantee of fitness for any purpose.

## Reference links

- Pandoc issue #1603 — https://github.com/jgm/pandoc/issues/1603
- Pandoc issue #11596 — https://github.com/jgm/pandoc/issues/11596
