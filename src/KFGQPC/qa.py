"""Record an explicit all-page visual review and refresh final reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audit import (
    combined_final_markdown,
    combined_final_report,
    final_markdown,
    write_json,
)


def record_visual_qa(
    report_dir: Path,
    *,
    status: str,
    notes: str,
) -> dict:
    reports: list[dict] = []
    for audit_path in sorted(report_dir.glob("*.audit.json")):
        if audit_path.name == "combined.audit.json":
            continue
        report = json.loads(audit_path.read_text(encoding="utf-8"))
        render = report.get("render")
        if not render:
            raise RuntimeError(f"report has no render manifest: {audit_path}")
        if len(render["pages"]) != render["page_count"]:
            raise RuntimeError(f"incomplete render manifest: {audit_path}")
        for page in render["pages"]:
            page["visually_reviewed"] = True
        render["visual_qa_complete"] = True
        render["visual_qa_status"] = status
        render["visual_qa_notes"] = notes
        report["render"] = render
        write_json(audit_path, report)
        markdown_path = audit_path.with_suffix("").with_suffix(".md")
        from .audit import _atomic_text
        _atomic_text(markdown_path, final_markdown(report))
        reports.append(report)
    combined = combined_final_report(reports)
    write_json(report_dir / "combined.audit.json", combined)
    from .audit import _atomic_text
    _atomic_text(report_dir / "combined.audit.md", combined_final_markdown(combined))
    return combined


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", required=True, type=Path)
    parser.add_argument(
        "--status",
        required=True,
        choices=("pass", "pass_with_font_limitation", "fail"),
    )
    parser.add_argument("--notes", required=True)
    args = parser.parse_args(argv)
    record_visual_qa(args.report_dir, status=args.status, notes=args.notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

