"""
Quran Multi-Column PDF Generator (Amulet / Hirz Layout) - Optimized
----------------------------------------------------------------------
Reads a .docx Quran file and uses a bounded binary search to find the
exact maximum font size (precision 0.01pt) to fit onto exactly 2 pages.
Includes CSS overrides for continuous line spacing and full box justification.
"""

import argparse
import os
import sys
from html import escape
from pathlib import Path
from typing import List
import docx
from weasyprint import HTML

BASE_DIR = Path(__file__).resolve().parent
INPUT_DOCX_PATH = "holly_quran.docx"
OUTPUT_PDF_PATH = None

# =====================================================================
# CONFIGURABLE PARAMETERS & PAGE PRESETS
# =====================================================================
PAGE_PRESETS = {
    "A1": {"margin": "10mm", "line_spacing": 2.1},
    "A2": {"margin": "10mm", "line_spacing": 1.8},
    "A3": {"margin": "10mm", "line_spacing": 1.5},
}

FONT_FAMILY = "KFGQPC Uthmanic Script HAFS"
NUM_COLUMNS = 1
FONT_FILE_PATH = BASE_DIR.parent / "fonts" / "KFGQPC Uthmanic Script HAFS Regular.otf"
# =====================================================================


def _font_url() -> str:
    font_path = Path(FONT_FILE_PATH).expanduser().resolve()
    if not font_path.exists():
        raise FileNotFoundError(f"Font file not found: {font_path}")
    return font_path.as_uri()


def load_docx(file_path: str) -> docx.Document:
    """Safely loads a Word document."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Input file not found: '{file_path}'")
    try:
        return docx.Document(file_path)
    except Exception as exc:
        raise RuntimeError(f"Failed to parse Word document: {exc}") from exc


def extract_paragraphs(doc: docx.Document) -> List[str]:
    """Extracts all non-empty paragraphs as clean strings."""
    return [p.text.strip() for p in doc.paragraphs if p.text.strip()]


def generate_html(
    paragraphs: List[str],
    font_family: str,
    font_size: float,
    page_size: str,
    margin: str,
    line_spacing: float,
) -> str:
    """
    Generates lightweight HTML/CSS for W3C Paged Media.
    Enforces strict box justification and uniform line spacing across paragraphs.
    """
    font_url = _font_url()
    content_html = "".join(f"<p>{text}</p>" for text in paragraphs)

    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
<meta charset="utf-8">
<style>
@font-face {{
    font-family: '{font_family}';
    src: url('{font_url}');
    font-weight: normal;
    font-style: normal;
}}
    @page {{
        size: {page_size};
        margin: {margin};
    }}
    body {{
        font-family: '{font_family}' !important;
        font-size: {font_size:.2f}pt;
        line-height: {line_spacing};
        column-fill: auto;
        margin: 0;
        padding: 0;
        text-align: justify;
        text-align-last: justify;
        direction: rtl;
        word-break: normal;
        overflow-wrap: normal;
    }}
    p {{
        margin: 0;
        text-indent: 0;
        text-align: justify;
    }}
    p::after {{
        content: "";
        display: inline-block;
        width: auto;
    }}
</style>
</head>
<body>
{content_html}
</body>
</html>"""


def get_page_count(html_str: str, step: int, page_size: str) -> int:
    """Renders once, saves the step PDF to disk, and returns page count."""
    document = HTML(string=html_str, base_url=str(BASE_DIR)).render()

    out_path = Path(OUTPUT_PDF_PATH)

    # Create the temp directory if it does not exist
    temp_dir = out_path.parent / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Build the step file path using the slash operator instead of with_name()
    temp_pdf = temp_dir / f"{out_path.stem}_{page_size}_step{step}{out_path.suffix or '.pdf'}"

    print(f"\nWriting step PDF: {temp_pdf}")
    document.write_pdf(str(temp_pdf))

    return len(document.pages)


def optimize_font_size(
    paragraphs: List[str],
    font_family: str,
    low: float,
    high: float,
    page_size: str,
    margin: str,
    line_spacing: float,
) -> float:
    """
    Bounded binary search for the maximum font size (up to 0.01 precision).
    """
    best_size = low

    print(f"Running bounded binary search ({low} pt to {high} pt)...")

    for step in range(1, 12):
        mid = round((low + high) / 2.0, 2)

        print(f"  Step {step:2d}/11 | Testing: {mid:5.2f} pt...", end=" ", flush=True)
        temp_html = generate_html(paragraphs, font_family, mid, page_size, margin, line_spacing)
        pages = get_page_count(temp_html, step, page_size)
        print(f"Result: {pages} page(s)")

        if pages <= 2:
            best_size = mid
            low = mid
        else:
            high = mid

    best_size = round(best_size, 2)
    final_html = generate_html(paragraphs, font_family, best_size, page_size, margin, line_spacing)
    HTML(string=final_html, base_url=str(BASE_DIR)).render().write_pdf(f"{OUTPUT_PDF_PATH}")
    if get_page_count(final_html, 0, page_size) > 2:
        best_size = round(best_size - 0.01, 2)

    return best_size


def main():
    parser = argparse.ArgumentParser(description="Quran PDF Generator with dynamic sizing bounds.")
    parser.add_argument("--page_size", choices=["A1", "A2", "A3"], default="A1", help="Page size (A1, A2, A3)")
    parser.add_argument("--low", type=float, default=2.0, help="Lower font size search bound (e.g. 2.0)")
    parser.add_argument("--high", type=float, default=7.0, help="Upper font size search bound (e.g. 5.0)")
    args = parser.parse_args()

    # Dynamic configuration based on selected page_size
    page_size = args.page_size

    margin = PAGE_PRESETS[page_size]["margin"]
    LINE_SPACING = PAGE_PRESETS[page_size]["line_spacing"]
    low = args.low
    high = args.high
    global OUTPUT_PDF_PATH
    OUTPUT_PDF_PATH = f"holly_quran_{page_size}.pdf"
    try:
        print(f"Loading document: '{INPUT_DOCX_PATH}'...")
        doc = load_docx(INPUT_DOCX_PATH)

        paragraphs = extract_paragraphs(doc)
        if not paragraphs:
            raise ValueError("The input Word document contains no readable text.")

        print(f"Config: {page_size} | Margin: {margin} | Line Spacing: {LINE_SPACING} | Range: [{low}, {high}]")
        print(f"Extracted {len(paragraphs)} paragraphs. Starting layout optimization...")
        optimal_size = optimize_font_size(paragraphs, FONT_FAMILY, low, high, page_size, margin, LINE_SPACING)
        print(f"\nOptimal Font Size Found: {optimal_size:.2f} pt")

        print(f"Exporting final 2-page {page_size} PDF to: '{OUTPUT_PDF_PATH}'...")
        final_html = generate_html(paragraphs, FONT_FAMILY, optimal_size, page_size, margin, LINE_SPACING)
        HTML(string=final_html, base_url=str(BASE_DIR)).render().write_pdf(OUTPUT_PDF_PATH)
        print("Done! Layout generated successfully.")

    except Exception as err:
        print(f"\n[ERROR] {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
