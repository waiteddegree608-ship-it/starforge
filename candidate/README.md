# sf-md-ref-inventory

A small, offline command-line tool for auditing **citation keys** and
**cross-reference labels** across a set of Markdown, Quarto (`.qmd`), or plain
text files. It answers three recurring questions before you run a full render
pipeline:

1. Is the same figure/section/table label defined in more than one place?
2. Does some `[text](#id)` link point at a label that is never defined?
3. Is a label defined but never referenced, or a BibTeX entry never cited?

A renamed or deleted bibliography file, a duplicated `{#id}`, or a typo in a
citation key often produces confusing downstream errors long after the mistake
was introduced. This tool gives writers a fast, dependency-free pre-render
audit so such mismatches are caught locally and early.

## Status and provenance

This project is an **AI-assisted prototype**. It was drafted as a small original
utility rather than extracted from an established product. There is **no
established adoption**, no community endorsement, and no affiliation with any
existing editor, publishing system, or tool. It is a starting point you are
expected to adapt to your own project conventions. It makes **no promise of
accuracy or correctness** — treat its output as a hint, not a guarantee.

## Requirements

- Python 3.10 or newer.
- Standard library only (`argparse`, `re`, `json`, `pathlib`, `sys`). No third
  party packages, no network access.

## Quickstart

```bash
# Describe the interface
python cli.py --help

# Run a self-contained demo with synthetic in-memory input
python cli.py --demo

# Scan a directory recursively for supported files
python cli.py docs/

# Scan specific files
python cli.py docs/intro.md docs/figures.md notes.txt

# Emit machine-readable JSON
python cli.py --format json docs/

# Also check citation keys against a BibTeX file
python cli.py --check-bib --bib references.bib docs/

# Write results to a file instead of stdout
python cli.py --format json --out report.json docs/
```

Supported input extensions: `.md`, `.markdown`, `.qmd`, `.txt`. Passing a
directory searches it recursively for those extensions.

## What gets extracted

- **Citation keys** from inline `[@key]`, `[@key, p. 3]`, `[@a; @b]`, and bare
  `@key` tokens, using word boundaries and ignoring patterns inside fenced code
  blocks, inline code spans, and email addresses.
- **Labels (anchors)** from Pandoc-style attributes such as `{#id}`,
  `{.class #id}`, and `[text]{#id}`; from ATX headings only when an explicit
  `{#id}` is attached; and from fenced-div `::: {#id}` markers.
- **References** from link targets written as `[text](#id)`.

## Output

JSON output is an object with the keys `files`, `labels_defined`, `duplicates`,
`undefined_refs`, `unused_labels`, optional `bib`, `read_errors`, and
`summary`. Text output prints the same information in labelled sections. All
ordering is deterministic (sorted by id, then file, then line).

### Real example

Given this layout:

```markdown
<!-- intro.md -->
# Introduction {#sec-intro}

See @fig-arch and the earlier work [@smith2020].
Jump to [the method](#sec-method).

## Method {#sec-method}
```

```markdown
<!-- figures.md -->
::: {#fig-arch}
Architecture placeholder.
:::

# Duplicate heading {#sec-intro}

![Caption](img.png){#fig-orphan}
```

Running:

```bash
python cli.py --check-bib --bib references.bib .
```

reports, among other findings, that `sec-intro` is defined twice, that
`fig-orphan` is defined but never referenced, that any `#nope`-style link has no
definition, and that a cited key has no matching BibTeX entry. Each finding
includes the file and line number so you can jump straight to it.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Completed; findings (if any) are reported normally |
| 1 | An input file could not be read, or was not valid UTF-8 |
| 2 | Usage error, e.g. no input paths were given |

## Limitations

- This is a **heuristic text scanner**, not a real Markdown or Pandoc parser.
  It uses regular expressions, so unusual syntax or nested constructs may be
  misread.
- Only **UTF-8** input is supported; a decode failure is reported as an error.
- The BibTeX support is deliberately minimal: it only recognises top-level
  `@type{key,` entries and does not expand `@string`, `@comment`, macros, or
  `crossref` fields.
- It does not resolve includes, partials, footnotes, or shortcode-generated
  identifiers.
- It never writes files unless `--out` is supplied, and it never accesses the
  network.
- Output is a diagnostic aid, not a validation guarantee.

## Tests

Behavior tests live in `test_cli.py` and cover extraction, duplicate/undefined/
unused detection, BibTeX comparison, a clean no-match case, unreadable input,
and CLI failure paths. Run them from this directory:

```bash
python -m unittest discover -s . -p "test_*.py"
```

## License

Released under the MIT License. See the `LICENSE` terms: use, copy, modify,
merge, publish, and distribute freely, provided the copyright notice and
permission notice are retained. The software is provided "as is", without
warranty of any kind.

## References

- Pandoc citations and cross-reference attribute syntax (documentation):
  https://pandoc.org/MANUAL.html
- Pandoc extension for bracketed spans and attributes:
  https://pandoc.org/MANUAL.html#extension-bracketed_spans
- Quarto cross-reference guide:
  https://quarto.org/docs/authoring/cross-references.html
- Quarto citations and bibliographies:
  https://quarto.org/docs/authoring/citations.html
- BibTeX entry format overview (BibTeXing, Oren Patashnik):
  https://www.ctan.org/pkg/bibtex
- Background friction this prototype responds to (upstream issue trackers):
  https://github.com/quarto-dev/quarto-cli/issues/11040 and
  https://github.com/quarto-dev/quarto-cli/issues/7157
