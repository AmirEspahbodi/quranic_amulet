# Quran DOCX Filter

**KFGQPC Hafs Uthmanic Quran DOCX Transformation Pipeline**

A production-quality Python tool that transforms KFGQPC Hafs Uthmanic Quran Microsoft Word (`.docx`) files according to a strict, auditable rule ledger. It preserves OOXML document structure, RTL properties, and paragraph layout while applying authorized Unicode codepoint transformations and deletions.

---

## Table of Contents

- [Overview](#overview)
- [What This Tool Does](#what-this-tool-does)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [CLI Usage](#cli-usage)
- [Rule Ledger Summary](#rule-ledger-summary)
- [Effective Overrides](#effective-overrides)
- [Contextual Edge Cases](#contextual-edge-cases)
- [Project Structure](#project-structure)
- [Output Files](#output-files)
- [Audit Reports](#audit-reports)
- [Batch Processing (All 114 Surahs)](#batch-processing-all-114-surahs)
- [Testing](#testing)
- [Configuration Reference](#configuration-reference)
- [Safety Guarantees](#safety-guarantees)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)

---

## Overview

This tool processes Quranic text files originating from the **Mushaf Word** Microsoft Word add-in. These files contain Quranic text in **Uthmanic orthography** (Hafs from Asim) using **KFGQPC data** and the font `KFGQPC HAFS Uthmanic Script`.

The pipeline applies **100 explicit rules** (50 KEEP, 13 TRANSFORM, 37 DELETE) plus **7 effective overrides** and **8 critical edge-case handlers** to produce a cleaned output DOCX that:

- Uses only `KFGQPC HAFS Uthmanic Script` for all Quranic text runs
- Removes verse numbers, ornamental marks, and stop signs
- Normalizes certain letter forms (Alef Wasla → Alef, Alef Maksura → Alef, etc.)
- Strips Shadda and certain Quranic annotation marks
- Preserves all base Quranic letters, word boundaries, and RTL layout
- Never silently corrupts, reorders, or invents Quranic text

---

## What This Tool Does

### Input
- Microsoft Word `.docx` files containing KFGQPC Hafs Uthmanic Quran text
- Font: `KFGQPC HAFS Uthmanic Script` (primary) and `KFGQPC Arabic Symbols 01` (symbol runs)

### Processing Pipeline

| Phase | Name | Description |
|-------|------|-------------|
| 0 | **Audit** | Inventory every Unicode codepoint, detect anomalies, check for blockers |
| 1 | **Contextual Normalizations** | Maddah handling, Inverted Damma, stop signs, Bismillah guard, Farsi Yeh |
| 2 | **Simple Transformations** | One-codepoint mappings (e.g., Alef Wasla → Alef) |
| 3 | **Deletions** | Remove Shadda, verse numbers, ornamental marks, digits |
| 4 | **Boundary Repair** | Fix word boundaries damaged by standalone separator deletion |
| 5 | **Validation** | Structural checks, font enforcement, output verification |

### Output
- A new `.docx` file with transformed text
- JSON audit report (machine-readable)
- Markdown audit report (human-readable)
- Original input file is **never modified**

---

## Requirements

- **Python** 3.10 or higher
- **pip** (Python package manager)
- **Microsoft Word** or **LibreOffice** (for visual verification of output, optional)

### Python Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `python-docx` | ≥ 1.1.0 | DOCX read/write |
| `lxml` | ≥ 5.0.0 | XML/OOXML manipulation |
| `regex` | ≥ 2024.4.16 | Unicode-aware regex |
| `typer` | ≥ 0.12.0 | CLI framework |
| `rich` | ≥ 13.0.0 | Terminal output formatting |

### Development Dependencies (optional)

| Package | Purpose |
|---------|---------|
| `pytest` | Test runner |
| `pytest-cov` | Coverage reporting |
| `hypothesis` | Property-based testing |

---

## Installation

### Step 1: Clone or Download the Project

```bash
# If using git
git clone <repository-url>
cd quran-docx-filter

# Or copy the project folder to your desired location
