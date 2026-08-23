# Quran DOCX Filter CLI

A deterministic, strict DOCX filtering pipeline for Quranic text.

The CLI can process a single DOCX file, an entire folder of DOCX files, or a glob pattern. Each input is audited first, then transformed, validated, and reported. Existing output files are never overwritten; a numeric suffix is added when necessary.

## Requirements

- Python 3.10+
- The project dependencies installed in the project environment
- `rich` is recommended for the modern terminal UI and progress bars. The CLI still works without it, using a plain-text fallback.

## Basic usage

Run the CLI through the package module:

```bash
python -m <package>.cli <INPUTS> --out <OUTPUT_DIR> --reports <REPORT_DIR>
```

Replace `<package>` with the actual Python package name of this project.

### Process one DOCX file

```bash
python -m <package>.cli ./input/surah-al-fatiha.docx \
  --out ./output \
  --reports ./reports
```

The filtered document is written to:

```text
./output/surah-al-fatiha.filtered.docx
```

### Process an entire folder

This is the recommended way to batch-process multiple surah files.

```bash
python -m <package>.cli ./input/surahs \
  --out ./output \
  --reports ./reports
```

Every `.docx` file directly inside `./input/surahs` is discovered and processed. Files whose names already end with `.filtered.docx` are ignored, which prevents previously generated outputs from being processed again.

For example:

```text
input/
└── surahs/
    ├── 001-al-fatiha.docx
    ├── 002-al-baqarah.docx
    ├── 003-ali-imran.docx
    └── ...
```

becomes:

```text
output/
├── 001-al-fatiha.filtered.docx
├── 002-al-baqarah.filtered.docx
├── 003-ali-imran.filtered.docx
└── ...
```

During a batch run, the terminal shows a progress bar for the audit phase and another progress bar while filtering the documents.

## Process files with a glob

The CLI also accepts glob patterns, including recursive globs:

```bash
python -m <package>.cli "./input/surahs/*.docx" \
  --out ./output \
  --reports ./reports
```

Recursive example:

```bash
python -m <package>.cli "./input/**/*.docx" \
  --out ./output \
  --reports ./reports
```

You may also provide multiple inputs in one invocation:

```bash
python -m <package>.cli \
  ./input/surah1.docx \
  ./input/surah2.docx \
  ./input/surahs \
  --out ./output \
  --reports ./reports
```

Duplicate inputs discovered from overlapping arguments are processed only once.

## Non-overwriting output behavior

The CLI never intentionally overwrites an existing filtered document.

For example, if this file already exists:

```text
output/001-al-fatiha.filtered.docx
```

the next generated file will be:

```text
output/001-al-fatiha.filtered-2.docx
```

and then:

```text
output/001-al-fatiha.filtered-3.docx
```

The same collision-avoidance behavior is used for per-file reports.

## Audit only

Use `--audit-only` when you want to run the Phase 0 inventory/preflight without changing any DOCX files:

```bash
python -m <package>.cli ./input/surahs \
  --out ./output \
  --reports ./reports \
  --audit-only
```

The command creates preflight reports but does not run the transformation pipeline.

If the preflight contains an unresolved blocker, processing stops before any transformation is performed.

## Strict mode

Strict mode is enabled by default:

```bash
python -m <package>.cli ./input/surahs \
  --out ./output \
  --reports ./reports \
  --strict
```

Strict mode blocks processing when an unresolved ambiguity could potentially corrupt Quranic letters or otherwise violate the filtering rules.

To disable strict mode explicitly:

```bash
python -m <package>.cli ./input/surahs \
  --out ./output \
  --reports ./reports \
  --no-strict
```

For Quranic document processing, keeping strict mode enabled is the recommended default.

## Target font

The default target font is the project's configured Quranic font (`KFGQPC HAFS Uthmanic Script` in the current configuration).

You can override it with:

```bash
python -m <package>.cli ./input/surahs \
  --out ./output \
  --reports ./reports \
  --target-font "KFGQPC HAFS Uthmanic Script"
```

The source symbol font can also be overridden when required:

```bash
python -m <package>.cli ./input/surahs \
  --out ./output \
  --reports ./reports \
  --source-symbol-font "<FONT_NAME>"
```

## JSON output for automation / CI

Use `--json` to suppress the human-oriented terminal UI and emit machine-readable JSON to stdout:

```bash
python -m <package>.cli ./input/surahs \
  --out ./output \
  --reports ./reports \
  --json
```

This is useful for shell scripts, CI pipelines, and other automation. The JSON payload includes the overall status, exit code, processed inputs, reports, blockers, and warnings.

Example:

```json
{
  "status": "success",
  "exit_code": 0,
  "inputs": [
    "input/surah1.docx",
    "input/surah2.docx"
  ],
  "reports": [],
  "blockers": [],
  "warnings": []
}
```

The `reports` array contains the detailed per-file reports after a successful transformation run.

## Rendering

If the project supports DOCX rendering in the configured environment, an optional render directory can be supplied:

```bash
python -m <package>.cli ./input/surahs \
  --out ./output \
  --reports ./reports \
  --render-dir ./renders
```

## Generated reports

The reports directory contains JSON and Markdown reports for the audit and final processing stages.

Typical output:

```text
reports/
├── 001-al-fatiha.preflight.json
├── 001-al-fatiha.preflight.md
├── 002-al-baqarah.preflight.json
├── 002-al-baqarah.preflight.md
├── ...
├── combined.preflight.json
├── combined.preflight.md
├── 001-al-fatiha.audit.json
├── 001-al-fatiha.audit.md
├── 002-al-baqarah.audit.json
├── 002-al-baqarah.audit.md
├── ...
├── combined.audit.json
└── combined.audit.md
```

The reports are useful for reviewing:

- input SHA-256 hashes
- preflight/audit results
- transformation results
- validation checks
- warnings and blockers
- final automated-pass status
- output document paths

## Pipeline behavior

For each batch, the CLI follows this overall flow:

```text
Input discovery
      ↓
Phase 0 — Audit / preflight for all inputs
      ↓
Write preflight reports
      ↓
Block the whole run if preflight detects blockers
      ↓
Phase 1–5 transformation pipeline per file
      ↓
Determinism check
      ↓
Output validation
      ↓
Atomically publish the validated DOCX
      ↓
Write per-file reports
      ↓
Write combined final report
```

The audit phase is completed for the entire discovered batch before transformation starts. This prevents a later-discovered preflight blocker from leaving an earlier file in the batch already transformed.

## Command-line options

The current CLI accepts:

```text
inputs                 one or more DOCX files, directories, or glob patterns
--output-dir, --out    directory for filtered DOCX output (required)
--report-dir, --reports directory for JSON/Markdown reports (required)
--render-dir           optional directory for rendered output
--audit-only           run audit/preflight without transforming files
--strict / --no-strict block or allow unresolved ambiguities
--target-font          target font name
--source-symbol-font   source symbol font name
--json                 emit machine-readable JSON to stdout
```

To see the same information directly from the installed CLI:

```bash
python -m <package>.cli --help
```

## Exit codes

| Code | Meaning |
|---:|---|
| `0` | Success / audit-only completed successfully |
| `2` | Argument or DOCX package error |
| `3` | Preflight blocker / strict processing blocked |
| `4` | General processing failure |
| `5` | Output validation failure or rendering failure |
| `6` | Reserved for an overwrite conflict detected by the CLI |

These stable exit codes are intended for scripting and CI systems.

## Recommended batch command

For processing a complete folder of surah DOCX files with strict filtering and detailed reports:

```bash
python -m <package>.cli ./input/surahs \
  --out ./output \
  --reports ./reports \
  --strict
```

After the command finishes, inspect:

```text
output/    → filtered DOCX files
reports/   → preflight + final audit reports
```
