# Quranic Amulet

> A high-integrity Quran text-processing and document-generation toolkit for preparing Uthmanic-script Quran content for compact Amulet / Hirz-style layouts.

[![Python](https://img.shields.io/badge/Python-3.14%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Not%20Specified-lightgrey)](#license-and-content-rights)

## Overview

**Quranic Amulet** is a Python project for working with Quranic DOCX documents whose text must be handled with unusually high care.

The project is built around three related goals:

1. **Normalize and transform Quranic text** from a Tanzil Uthmani DOCX representation into the target textual form required by this project.
2. **Process KFGQPC Hafs Uthmanic DOCX files safely**, with explicit font handling, structural inspection, transformation, validation, audit reports, and non-overwriting behavior.
3. **Generate compact PDF layouts** from a prepared Quran DOCX, including automatic font-size optimization for a two-page Amulet / Hirz-style result.

This is not simply a text replacement script. Quranic Arabic contains combining marks, orthographic conventions, Unicode characters, right-to-left behavior, OpenXML font metadata, and document structures that can easily be damaged by naïve processing. The project therefore treats the document as a structured artifact and uses validation and audit stages before accepting generated output.

The current repository is organized around the `KFGQPC` and `TANZIL` processing paths, plus document concatenation and PDF generation utilities. fileciteturn5file0L1-L10

---

## Who Is This Project For?

You do **not** need to be a programmer to understand the purpose of this repository.

### For non-technical readers

If you only want to understand what the project does:

> It takes Quranic Word documents, carefully prepares their Arabic text and typography, combines the required content, and can produce a compact PDF suitable for an Amulet / Hirz-style layout.

The project is especially concerned with avoiding accidental changes to Quranic text during conversion and formatting.

### For users who work with Word or PDF

You can use the project as a document-processing pipeline:

- start from the supplied Quranic DOCX corpus,
- normalize or filter the source representation,
- combine Surah documents when required,
- enforce the intended Quranic font,
- validate the resulting DOCX,
- and generate a compact PDF.

### For Python developers

The repository is a Python 3.14+ project using Poetry-style packaging and includes `python-docx`, `WeasyPrint`, `Typer`, and `Rich` as its main runtime dependencies. fileciteturn4file0L2-L6

### For senior engineers and maintainers

The interesting part of the project is its **data-integrity strategy**:

- preflight inspection before transformation,
- strict transformation rules,
- Unicode-domain validation,
- DOCX round-trip validation,
- OpenXML font-slot validation,
- deterministic transformation checks,
- atomic temporary-file replacement,
- refusal to overwrite existing outputs,
- machine-readable JSON reports,
- human-readable Markdown reports,
- and optional rendering verification.

The KFGQPC CLI explicitly performs preflight auditing, transformation, validation, deterministic-byte comparison, reporting, and optional rendering. fileciteturn8file0L1-L6

---

## What Does "Quranic Amulet" Mean Here?

The name refers to the project's intended output format: a highly compact Quranic document commonly associated with **Amulet / Hirz-style** layouts.

The software itself is a document-processing and typesetting pipeline. It does not make religious, theological, medical, legal, or spiritual claims about the use or efficacy of an amulet.

---

# Quran Text Sources

This repository currently contains two distinct Quran text representations. They should **not** be treated as interchangeable datasets.

## 1. `KFGQPC` — KFGQPC Hafs Uthmanic representation

The `KFGQPC` directory contains the Quranic corpus and processing logic for the version described for this project as:

> **The Holy Quran in Uthmanic script, Hafs 'an 'Asim narration, based on the King Fahd Complex / KFGQPC data and typography.**

The intended fonts are:

- **KFGQPC HAFS Uthmanic Script** — primary Quranic font.
- **KFGQPC Arabic Symbols 01** — Quranic/special-symbol font used where required by the source material.

These exact font names are defined by the project itself. fileciteturn12file0L2-L6

According to the project's source provenance, the Surah DOCX files in this version were obtained from the **Mushaf Word / مصحف وورد** extension.

The repository's KFGQPC package contains dedicated modules for inventory, auditing, OpenXML handling, transformation, validation, rendering, rules, batch processing, and CLI orchestration. fileciteturn6file0L1-L10

### Why KFGQPC matters

Quranic fonts are not merely cosmetic. Font selection affects the visual representation of Arabic glyphs and Quranic signs. For that reason, the project explicitly writes font information into multiple Word/OpenXML locations rather than relying only on a normal Word style.

---

## 2. `TANZIL` — Tanzil Uthmani representation

The `TANZIL` directory contains the source-side filtering logic for the digital Quran representation described for this project as:

> **The Madinah Mushaf (King Fahd Complex edition), using Uthmanic orthography and the well-known Uthman Taha script, represented digitally as Tanzil Uthmani.**

According to the project's source provenance, the Surah DOCX files for this representation were obtained from the **QuranWord** extension:

https://quranword.net/fa#download

The Tanzil processor is deliberately designed around the fact that combining Quranic signs can be separated from their base letters by Microsoft Word run boundaries. It therefore transforms **complete paragraph strings rather than individual Word runs**. fileciteturn11file0L1-L6

### Why there are two representations

The two datasets represent different stages and/or conventions of Quranic digital text. The repository therefore keeps them separate instead of silently treating one as a drop-in replacement for the other.

A simplified view is:

```text
TANZIL source DOCX
       |
       v
Tanzil Uthmani filtering / normalization
       |
       v
Target Quranic text representation
       |
       +----------------------+
       |                      |
       v                      v
KFGQPC DOCX processing     Surah concatenation
       |                      |
       +----------+-----------+
                  |
                  v
             Prepared DOCX
                  |
                  v
          WeasyPrint PDF
                  |
                  v
       Compact Amulet / Hirz PDF
```

---

# Architecture

At a high level, the repository can be understood as five layers.

```text
+-------------------------------------------------------+
|                    User / Operator                   |
+-----------------------------+-------------------------+
                              |
                              v
+-------------------------------------------------------+
| CLI / orchestration                                   |
| KFGQPC.cli                                             |
+-----------------------------+-------------------------+
                              |
                              v
+-------------------------------------------------------+
| Quran document processing                              |
| Inventory -> Rules -> Transformer -> Validation       |
+-----------------------------+-------------------------+
                              |
                              v
+-------------------------------------------------------+
| Document assembly                                      |
| TANZIL filtering / Surah concatenation                 |
+-----------------------------+-------------------------+
                              |
                              v
+-------------------------------------------------------+
| Rendering / typesetting                                |
| DOCX -> HTML/CSS -> WeasyPrint -> PDF                 |
+-------------------------------------------------------+
```

The repository uses a `src/` layout and currently exposes `KFGQPC`, `TANZIL`, `concat_surah.py`, and `pdf_gen.py` under that source tree. fileciteturn5file0L1-L10

---

# Repository Structure

```text
quranic_amulet/
├── .work/                 # Working/build-related material
├── fonts/                 # Project font assets
├── src/
│   ├── KFGQPC/
│   │   ├── __init__.py
│   │   ├── audit.py
│   │   ├── batch_process.py
│   │   ├── cli.py
│   │   ├── inventory.py
│   │   ├── ooxml.py
│   │   ├── qa.py
│   │   ├── reference.py
│   │   ├── render.py
│   │   ├── rules.py
│   │   ├── transformer.py
│   │   └── validation.py
│   │
│   ├── TANZIL/
│   │   └── tanzil_text_filter.py
│   │
│   ├── concat_surah.py
│   └── pdf_gen.py
│
├── temp/                 # Temporary/generated working artifacts
├── tests/
│   ├── conftest.py
│   ├── test_contextual_rules.py
│   ├── test_corpus.py
│   ├── test_deletions.py
│   ├── test_docx_roundtrip.py
│   ├── test_package_safety.py
│   ├── test_properties.py
│   ├── test_rule_ledger.py
│   └── test_run_boundaries.py
│
├── pyproject.toml
└── README.md
```

The repository currently contains a dedicated test suite covering contextual rules, corpus behavior, deletions, DOCX round trips, package safety, properties, rule ledgers, and Word run boundaries. fileciteturn13file0L1-L10

---

# Core Components

## `src/KFGQPC/cli.py`

This is the main orchestration layer for the KFGQPC processing pipeline.

It can:

- accept one or more DOCX files or directories,
- discover DOCX inputs,
- refuse to process an empty input set,
- perform a preflight audit,
- write preflight JSON/Markdown reports,
- stop before transformation when preflight fails,
- transform documents in strict mode,
- validate generated output,
- verify deterministic output by transforming twice,
- refuse accidental overwrites,
- optionally render output for additional inspection,
- and generate combined audit reports.

It also defines explicit exit codes so automation can distinguish argument errors, preflight failures, processing failures, validation failures, and overwrite conflicts. fileciteturn8file0L1-L6

### Important safety property

The CLI is intentionally **non-overwriting** by default. If the expected output already exists, processing stops instead of silently replacing it. fileciteturn8file0L1-L6

---

## `src/KFGQPC/inventory.py`

Responsible for inspecting DOCX input and building an inventory used by the preflight/audit stage.

The purpose of this layer is to understand what is actually inside a document before changing it.

---

## `src/KFGQPC/rules.py`

Contains the transformation rule definitions used by the KFGQPC processing path.

Keeping transformation rules separate from orchestration makes the system easier to inspect, test, and audit.

---

## `src/KFGQPC/transformer.py`

Performs the actual strict DOCX transformation.

The separation between transformation and validation is deliberate: a document is not considered successful merely because a transformation function completed without raising an exception.

---

## `src/KFGQPC/ooxml.py`

Provides lower-level handling for the underlying **Office Open XML (OOXML)** package used by `.docx` files.

This matters because a DOCX file is not a simple text file. It is a ZIP-based package containing XML documents, relationships, styles, metadata, and other resources.

---

## `src/KFGQPC/validation.py`

Validates the generated DOCX against the project's required invariants.

The CLI uses this validation stage before accepting the generated output. fileciteturn8file0L1-L6

---

## `src/KFGQPC/audit.py`

Produces machine-readable and human-readable reports for preflight and final processing.

The project writes both `.json` and `.md` reports, including combined reports for batch processing. fileciteturn8file0L1-L6

---

## `src/KFGQPC/render.py`

Provides an optional rendering step for generated documents. Rendering is kept separate from the transformation pipeline so that document correctness and visual inspection can be treated as distinct concerns.

---

## `src/TANZIL/tanzil_text_filter.py`

This module implements a three-phase transformation pipeline:

```text
Phase 1: Contextual normalization
        |
        v
Phase 2: Character mapping
        |
        v
Phase 3: Deletion
        |
        v
Final validation
```

The module explicitly documents contextual rules, character mappings, deletion rules, Unicode-domain checks, DOCX read/write behavior, round-trip verification, and built-in regression tests. fileciteturn11file0L1-L6 fileciteturn14file0L1-L6

### Why the three phases matter

A naïve implementation might delete or replace Unicode characters globally. That can be dangerous because the meaning of a Quranic mark can depend on the character immediately before or after it.

The Tanzil implementation therefore performs context-sensitive operations before generic mappings and deletions.

It also validates the final Unicode domain and rejects forbidden or unsupported characters instead of silently passing them through. fileciteturn14file0L1-L6

---

## `src/concat_surah.py`

Combines individual Surah Word files into one Quran DOCX.

The current implementation:

- discovers Surah files,
- extracts text from DOCX documents,
- supports legacy `.doc` files through Microsoft Word COM when required,
- normalizes extracted text,
- orders files by their numeric Surah prefix,
- checks for missing/duplicate numbering,
- and applies the intended Quranic font through WordprocessingML/OpenXML metadata.

The implementation also explicitly handles paragraphs and tables when extracting DOCX text. fileciteturn9file0L1-L2

> **Note:** this utility currently contains project-specific input/output defaults in the source code. If you are integrating it into a larger automated pipeline, inspect and parameterize those paths rather than assuming they are universal.

---

## `src/pdf_gen.py`

Generates the final compact PDF.

The current PDF generator:

- reads a prepared `.docx`,
- extracts non-empty paragraphs,
- generates RTL Arabic HTML/CSS,
- loads the KFGQPC font with `@font-face`,
- renders through **WeasyPrint**,
- supports A1/A2/A3 presets,
- uses configurable margins and line spacing,
- and performs a bounded binary search to find a font size capable of fitting the document into two pages.

The current implementation searches with a precision of `0.01pt` and uses a configurable lower/upper font-size bound. fileciteturn10file0L1-L6

---

# Data-Integrity Philosophy

Quranic text should not be treated like ordinary prose during automated processing.

The project therefore follows several engineering principles.

## 1. Never silently reinterpret input

When an input document contains structures that the processing code cannot safely interpret, the preferred behavior is to fail explicitly rather than silently discard or rewrite content.

The Tanzil processor, for example, rejects text boxes, content controls, tracked revisions, and ambiguous table content instead of silently omitting their text. fileciteturn14file0L1-L6

## 2. Validate the output, not only the operation

A successful Python function call does not prove that a generated DOCX is correct.

The pipeline reopens and validates generated documents, including text, RTL metadata, and font slots. fileciteturn14file0L1-L6

## 3. Do not overwrite source material

Generated files are treated as new artifacts. The KFGQPC CLI explicitly refuses existing output paths. fileciteturn8file0L1-L6

## 4. Prefer deterministic processing

The KFGQPC CLI transforms the same input twice and compares the resulting package bytes as a determinism check before accepting the generated artifact. fileciteturn8file0L1-L6

## 5. Keep an audit trail

Processing produces JSON and Markdown reports so a human can inspect what happened and automation can consume the same information programmatically. fileciteturn8file0L1-L6

---

# Installation

## Requirements

The project currently declares:

- **Python 3.14 or newer**
- **Poetry** / Poetry Core packaging
- `typer`
- `rich`
- `python-docx`
- `weasyprint`

These requirements are declared in `pyproject.toml`. fileciteturn4file0L2-L6

### Recommended setup

```bash
git clone https://github.com/AmirEspahbodi/quranic_amulet.git
cd quranic_amulet
poetry install
```

If you prefer not to use Poetry, install the project in an isolated Python environment according to your normal Python packaging workflow. Poetry is the repository's declared build backend.

---

# Typical Workflow

A conceptual end-to-end workflow looks like this:

```text
1. Obtain the source Quranic DOCX corpus
                 |
                 v
2. Inspect / preflight the corpus
                 |
                 v
3. Normalize the required Quranic representation
                 |
                 v
4. Apply strict KFGQPC transformations where applicable
                 |
                 v
5. Validate the generated DOCX
                 |
                 v
6. Concatenate Surahs into one document if required
                 |
                 v
7. Generate the compact PDF
                 |
                 v
8. Visually inspect the final PDF
```

For production or archival use, **do not skip the validation and visual-inspection stages** merely because the script exits successfully.

---

# Using the KFGQPC CLI

The main KFGQPC CLI is implemented in `src/KFGQPC/cli.py` and accepts one or more DOCX files or directories. fileciteturn8file0L1-L6

A typical invocation is:

```bash
poetry run python -m KFGQPC.cli INPUT.docx \
  --output-dir output \
  --report-dir reports
```

For a directory containing multiple DOCX files:

```bash
poetry run python -m KFGQPC.cli ./input \
  --output-dir ./output \
  --report-dir ./reports
```

### Audit only

If you want to inspect the corpus without generating transformed DOCX files:

```bash
poetry run python -m KFGQPC.cli ./input \
  --output-dir ./output \
  --report-dir ./reports \
  --audit-only
```

### Optional rendering

The CLI also accepts a render directory:

```bash
poetry run python -m KFGQPC.cli ./input \
  --output-dir ./output \
  --report-dir ./reports \
  --render-dir ./renders
```

### Strict mode

Strict processing is enabled by default. The CLI exposes `--strict` / `--no-strict` through Python's `BooleanOptionalAction`. fileciteturn8file0L1-L6

---

# Output Reports

A normal KFGQPC run can produce files such as:

```text
reports/
├── document.preflight.json
├── document.preflight.md
├── document.audit.json
├── document.audit.md
├── combined.preflight.json
└── combined.audit.json
```

The JSON reports are intended for automation and machine inspection.

The Markdown reports are intended for humans, code review, troubleshooting, and archival documentation.

---

# Understanding the Tanzil Transformation Pipeline

The Tanzil processor is intentionally more sophisticated than a global character-replacement table.

## Phase 1 — Contextual rules

Context-sensitive Quranic marks are interpreted according to surrounding characters.

Examples of concepts handled here include:

- Maddah behavior,
- long-vowel contexts,
- Muqatta'at forms,
- inverted Damma,
- plural-verb Waw + Maddah cases,
- Dammatan normalization,
- Dagger Alef,
- Small High Madda,
- and repeated Alef collapse.

The source implementation documents these as C-series contextual rules. fileciteturn11file0L1-L6

## Phase 2 — Character mapping

Characters that represent equivalent or source-specific forms are mapped into the target representation.

The current mapping includes cases such as:

- Alef Wasla -> Alef,
- Alef with Madda -> Alef,
- Alef with Hamza Below -> Alef,
- Alef Maksura -> Alef,
- Small Low Seen -> Tha,
- Small Yeh -> Yeh,
- Small High Noon -> Noon,
- Small Low Meem -> Meem.

These mappings are explicitly encoded in the source rather than inferred dynamically. fileciteturn11file0L1-L6

## Phase 3 — Deletion

The final phase removes source-specific signs and markers that are not part of the requested target representation.

The implementation also handles attached ayah-number runs and isolated pause marks using context-aware expressions rather than blindly deleting every digit or Arabic character that happens to match a pattern. fileciteturn11file0L1-L6

## Final validation

After all phases, the processor checks the output Unicode domain and rejects forbidden characters and invalid states such as double Alef sequences. fileciteturn14file0L1-L6

---

# Word / DOCX Font Handling

A `.docx` document has multiple locations where font information can influence rendering.

For Quranic Arabic, setting only:

```python
run.font.name = "KFGQPC HAFS Uthmanic Script"
```

may not be enough.

The project therefore explicitly manages multiple OpenXML font slots, including:

- `w:ascii`
- `w:hAnsi`
- `w:eastAsia`
- `w:cs`

and removes relevant theme-font attributes where necessary.

The concatenation utility also applies the target font at document-default and run levels. fileciteturn9file0L1-L2

The Tanzil writer likewise sets the complex-script font metadata and Arabic language information when producing DOCX output. fileciteturn14file0L1-L6

---

# PDF Generation

The PDF stage uses **WeasyPrint** rather than relying on Microsoft Word to perform the final pagination.

The basic rendering chain is:

```text
DOCX
 |
 | python-docx
 v
Paragraph text
 |
 | HTML + CSS
 v
RTL HTML document
 |
 | WeasyPrint
 v
PDF
```

The generator embeds the configured KFGQPC font through CSS `@font-face` and uses RTL Arabic layout rules. fileciteturn10file0L1-L6

## Page presets

The current implementation defines three named presets:

| Preset | Margin | Line spacing |
|---|---:|---:|
| A1 | 10 mm | 2.1 |
| A2 | 10 mm | 1.8 |
| A3 | 10 mm | 1.5 |

The names and values are implementation presets, not claims about official Quran page standards. fileciteturn10file0L1-L6

## Font-size optimization

The PDF generator uses bounded binary search to find the largest tested font size that fits the requested two-page target.

The current defaults search from `2.0pt` to `7.0pt` and refine the result to `0.01pt` precision. fileciteturn10file0L1-L6

---

# Testing

The repository includes a dedicated regression-oriented test suite.

Run the tests with:

```bash
poetry run pytest
```

The test suite includes coverage for:

- contextual transformation rules,
- deletion rules,
- corpus-level behavior,
- DOCX round trips,
- package safety,
- property-style invariants,
- rule ledgers,
- and Word run-boundary behavior. fileciteturn13file0L1-L10

## Why run-boundary tests matter

Microsoft Word may split a visually continuous Quranic phrase into multiple XML runs. A combining mark can therefore be stored in a different run from the base letter it visually belongs to.

Processing runs independently can consequently change the meaning or structure of the text.

The Tanzil implementation explicitly avoids this class of bug by transforming complete paragraph strings. fileciteturn11file0L1-L6

---

# Safety and Failure Behavior

The project is designed to **fail loudly rather than silently corrupt data**.

Typical failure categories include:

- invalid input paths,
- missing DOCX files,
- unsupported DOCX structures,
- invalid Quranic Unicode characters,
- preflight blockers,
- transformation errors,
- validation failures,
- rendering failures,
- and output-overwrite conflicts.

The KFGQPC CLI exposes separate exit codes for these categories, which makes it suitable for scripting and CI-style workflows. fileciteturn8file0L1-L6

---

# Important Operational Recommendations

## Keep source and generated files separate

Do not use the same directory for immutable source material and generated artifacts unless you have a deliberate versioning strategy.

## Keep reports

For important outputs, keep the corresponding JSON and Markdown audit reports alongside the generated artifact or in a versioned archive.

## Verify the actual font file

A font name in a DOCX does not guarantee that the same font file is installed or available to the renderer.

For reproducible PDF generation, ensure the expected KFGQPC font files are available to the environment running WeasyPrint.

## Inspect the final PDF visually

Automated checks can detect many structural and Unicode errors, but visual inspection remains important for typography-heavy Quranic documents.

Check at minimum:

- glyph shapes,
- Quranic marks,
- line breaks,
- RTL direction,
- page boundaries,
- clipping,
- missing-glyph boxes,
- unexpected fallback fonts,
- and overall readability.

---

# Reproducibility

For reproducible results, record at least:

- Git commit SHA,
- Python version,
- operating system,
- installed font files and versions,
- project dependency versions,
- source corpus version,
- transformation configuration,
- PDF preset,
- and generated audit reports.

This is particularly important because font rendering and Word/HTML layout can vary between environments.

---

# Source and Content Provenance

The project distinguishes **software provenance** from **Quranic content provenance**.

### Quranic content

The current project documentation identifies:

- `KFGQPC` Quranic Surah files as originating from the **Mushaf Word / مصحف وورد** extension.
- `TANZIL` Quranic Surah files as originating from the **QuranWord** extension at https://quranword.net/fa#download.

These statements document the provenance supplied for this repository; users performing scholarly, publishing, or archival work should independently verify the exact source edition, text revision, font version, and licensing terms applicable to their intended use.

### Software

The project itself is authored and maintained as a Python codebase and is packaged through Poetry. fileciteturn4file0L2-L6

---

# Fonts and Licensing

This repository works with Quranic fonts associated with KFGQPC / King Fahd Complex material.

**Do not assume that because a font file is present in a Git repository, it is automatically free of redistribution restrictions.**

Before redistributing this project, packaging the fonts into another product, publishing generated documents commercially, or creating derivative distributions, verify the applicable license and redistribution permissions for every font and Quranic source asset.

The repository currently does not declare a software license in `pyproject.toml`; therefore this README intentionally does **not** assign an SPDX license to the project or claim permissions that have not been explicitly established. fileciteturn4file0L2-L6

---

# Frequently Asked Questions

## Is this a Quran-reading application?

No. It is primarily a **Quranic document-processing and typesetting pipeline**.

## Does it modify Quranic text?

Some processing paths intentionally transform source representations into a defined target representation. These transformations are rule-based and are accompanied by validation intended to prevent unintended changes.

## Why not just use regular string replacement?

Because Quranic Unicode data is context-sensitive. Some signs represent different things depending on neighboring characters, and Word may split combining sequences across runs.

## Why does the project care about OpenXML?

Because a DOCX file stores formatting and text metadata in XML. Correctly setting the visible font in a Python object is not always sufficient to control how Word or another renderer interprets the document.

## Why are there both KFGQPC and TANZIL directories?

They represent different Quranic digital-text sources and processing requirements. The project keeps their assumptions and transformations separate.

## Can I safely run the processor over my original files?

The KFGQPC CLI is designed to refuse overwriting expected outputs, but you should still keep original source material backed up and separate from generated files.

## Does a successful PDF generation prove that the Quranic text is correct?

No. PDF generation proves that the rendering stage completed. It does not replace source verification, transformation validation, or human visual inspection.

---

# Engineering Design Principles

The project follows these principles:

1. **Preserve source data.**
2. **Fail rather than guess when sacred text cannot be safely interpreted.**
3. **Separate source normalization from target formatting.**
4. **Make transformations explicit and testable.**
5. **Validate generated artifacts independently from transformation code.**
6. **Prefer deterministic processing.**
7. **Never silently overwrite user data.**
8. **Produce an audit trail.**
9. **Keep rendering concerns separate from text transformation.**
10. **Make provenance and licensing assumptions visible.**

---

# Contributing

Contributions should preserve the project's data-integrity philosophy.

Before submitting a change:

1. Understand the relevant Quranic transformation rule or document invariant.
2. Add or update regression tests for the behavior.
3. Avoid broad Unicode replacements unless the rule is explicitly justified.
4. Verify DOCX round-trip behavior when document structure changes.
5. Verify font metadata when typography-related code changes.
6. Run the complete test suite.
7. Document any new source-data or font provenance.
8. Avoid introducing destructive default behavior.

For changes affecting Quranic text transformation, include concrete before/after examples and explain why the transformation is safe.

---

# Project Status

This repository is an actively developed engineering project. Some utilities currently contain project-specific paths and assumptions, while the KFGQPC package has a more structured audit/validation architecture.

Treat the repository as a **source-controlled processing pipeline**, not as a universal Quran publishing standard.

---

# Acknowledgements and Source Ecosystem

The project builds on the wider ecosystem of Quranic digital-text and typography resources, including:

- the King Fahd Complex / KFGQPC Quranic typography and data ecosystem,
- Tanzil Uthmani digital Quran text,
- QuranWord / مصحف وورد resources used as the stated source of the project's DOCX corpora,
- Microsoft Word / Office Open XML document technology,
- `python-docx`,
- and WeasyPrint.

All external Quranic text, fonts, and other assets remain subject to their respective source licenses and terms.

---

# License and Content Rights

No project software license is currently declared in the repository metadata. Until an explicit license is added, users should not assume that the code is granted broad open-source redistribution rights.

Likewise, Quranic text corpora, fonts, and third-party source materials may have separate terms.

For redistribution, commercial use, publication, or inclusion in another project, verify the rights for **each individual asset**, not only the repository as a whole.

---

# Maintainer Notes

When extending this project, think of every Quranic document as an integrity-sensitive artifact:

```text
INPUT
  |
  | inspect
  v
PREFLIGHT
  |
  | transform only when safe
  v
TRANSFORMATION
  |
  | validate independently
  v
VALIDATED ARTIFACT
  |
  | render
  v
VISUAL OUTPUT
  |
  | inspect + archive reports
  v
FINAL DELIVERABLE
```

That separation is the central engineering idea behind the repository.
