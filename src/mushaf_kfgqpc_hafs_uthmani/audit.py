"""Machine-readable JSON and concise human-readable Markdown audit reports."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from .rules import (
    EFFECTIVE_DELETE_CODEPOINTS,
    EFFECTIVE_OVERRIDES,
    RAW_DELETE_SEQUENCES,
    RAW_TRANSFORMS,
    all_rule_labels,
)


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def write_json(path: Path, value: dict) -> None:
    _atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def effective_source_labels() -> list[str]:
    labels = [f"U+{cp:04X}" for cp in sorted(set(RAW_TRANSFORMS) | set(EFFECTIVE_OVERRIDES))]
    labels.extend(f"U+{cp:04X}" for cp in sorted(EFFECTIVE_DELETE_CODEPOINTS))
    labels.extend("+".join(f"U+{cp:04X}" for cp in seq) for seq in RAW_DELETE_SEQUENCES)
    labels.extend(["E3:Unicode numeric category", "U+FDFD"])
    return sorted(set(labels))


def add_zero_match_rules(preflight: dict) -> None:
    matched = set(preflight["trigger_counts"])
    matched.update(
        "+".join(item["sequence"]) for item in preflight["stop_sequence_occurrences"]
    )
    if any(key.startswith("U+") and key in preflight["trigger_counts"] for key in preflight["trigger_counts"]):
        numeric_matched = any(
            occurrence["category"] in {"Nd", "Nl", "No"}
            for occurrence in preflight["trigger_occurrences"]
        )
        if numeric_matched:
            matched.add("E3:Unicode numeric category")
    preflight["zero_match_effective_rules"] = [
        label for label in effective_source_labels() if label not in matched
    ]


def preflight_markdown(report: dict) -> str:
    add_zero_match_rules(report)
    lines = [
        f"# Preflight audit — {Path(report['input']['path']).name}",
        "",
        f"- Identified surah: **{report['identity']['surah']}**",
        f"- Input SHA-256: `{report['input']['sha256']}`",
        f"- Target / non-target characters: {report['target_character_count']} / {report['non_target_character_count']}",
        f"- Raw ledger: KEEP {report['raw_ledger_counts']['KEEP']}, TRANSFORM {report['raw_ledger_counts']['TRANSFORM']}, DELETE {report['raw_ledger_counts']['DELETE']}",
        f"- Unknown Arabic/Quranic occurrences: {report['unknown_count']}",
        f"- Unresolved ambiguities: {report['unresolved_count']}",
        f"- Exact multi-codepoint stop candidates: {report['stop_sequence_count']}",
        f"- Strict preflight: **{'PASS' if report['preflight_ok'] else 'FAIL'}**",
        "",
        "## Contextual decisions",
        "",
        "| Decision | Count | Cross-run |",
        "|---|---:|---:|",
    ]
    decisions = report["contextual_decision_counts"]
    for decision in sorted(decisions):
        lines.append(
            f"| `{decision}` | {decisions[decision]} | {report['run_boundary_match_counts'].get(decision, 0)} |"
        )
    if not decisions:
        lines.append("| none | 0 | 0 |")
    lines.extend([
        "",
        "## Rule-triggering code points",
        "",
        "| Code point | Count |",
        "|---|---:|",
    ])
    for codepoint, count in report["trigger_counts"].items():
        lines.append(f"| `{codepoint}` | {count} |")
    lines.extend([
        "",
        "## Effective rules with zero source matches",
        "",
        ", ".join(f"`{item}`" for item in report["zero_match_effective_rules"]) or "None.",
        "",
        "The JSON companion contains the complete Unicode inventory, font/style inventory, all trigger contexts, and source locations.",
        "",
    ])
    return "\n".join(lines)


def final_markdown(report: dict) -> str:
    validation = report["validation"]
    transform = report["transform"]
    preflight = report["preflight"]
    lines = [
        f"# Final audit — {Path(preflight['input']['path']).name}",
        "",
        f"- Surah: **{preflight['identity']['surah']}**",
        f"- Input SHA-256: `{validation['input_sha256']}`",
        f"- Output SHA-256: `{validation['output_sha256']}`",
        f"- Target characters: {transform['input_target_character_count']} → {transform['output_target_character_count']}",
        f"- Word-boundary repairs: {transform['word_boundary_repairs']}",
        f"- Unknown / unresolved: {preflight['unknown_count']} / {transform['unresolved_count']}",
        f"- Automated acceptance gates: **{'PASS' if validation['all_required_checks_passed'] else 'FAIL'}**",
        "",
        "## Applied decisions",
        "",
        "| Rule/decision | Count |",
        "|---|---:|",
    ]
    for rule, count in transform["decision_counts"].items():
        lines.append(f"| `{rule}` | {count} |")
    lines.extend([
        "",
        "## Validation gates",
        "",
        "| Gate | Status |",
        "|---|---|",
    ])
    for gate, passed in validation["checks"].items():
        lines.append(f"| `{gate}` | {'PASS' if passed else 'FAIL'} |")
    font = validation["font_file"]
    lines.extend([
        "",
        "## Font environment",
        "",
        (
            f"Exact `{report['target_font']}` font file available; cmap check: "
            f"{'PASS' if font.get('coverage_ok') else 'FAIL'}."
            if font.get("available")
            else f"Exact `{report['target_font']}` font file is not installed or embedded; OOXML assignment was verified, but exact glyph/cmap QA is unavailable."
        ),
        "",
    ])
    render = report.get("render")
    if render:
        lines.extend([
            "## Render and visual QA",
            "",
            f"- PDF pages: {render['page_count']} at {render['dpi']} DPI",
            f"- Programmatic blank pages / edge collisions: {render['programmatic_blank_page_count']} / {render['programmatic_edge_touch_count']}",
            f"- All-page visual review: **{render.get('visual_qa_status', 'pending_manual_review')}**",
            f"- Review complete: {'yes' if render.get('visual_qa_complete') else 'no'}",
            f"- Notes: {render.get('visual_qa_notes') or 'None.'}",
            "",
        ])
    lines.extend([
        "The JSON companion contains every transformation/deletion event with lineage, contexts, run locations, and full histograms.",
        "",
    ])
    return "\n".join(lines)


def combined_preflight_markdown(report: dict) -> str:
    lines = [
        "# Combined preflight audit",
        "",
        f"Files: {report['file_count']}; unknown: {report['unknown_count']}; unresolved: {report['unresolved_count']}; status: **{'PASS' if report['preflight_ok'] else 'FAIL'}**",
        "",
        "| Surah | File | SHA-256 | Target chars | Unknown | Unresolved | Status |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for item in report["files"]:
        lines.append(
            f"| {item['surah']} | {Path(item['path']).name} | `{item['sha256']}` | {item['target_character_count']} | {item['unknown_count']} | {item['unresolved_count']} | {'PASS' if item['preflight_ok'] else 'FAIL'} |"
        )
    lines.extend([
        "",
        "## Effective rules with zero matches across the corpus",
        "",
        ", ".join(f"`{item}`" for item in report.get("zero_match_effective_rules", [])) or "None.",
        "",
    ])
    return "\n".join(lines)


def combined_final_report(reports: list[dict]) -> dict:
    decisions: Counter[str] = Counter()
    files: list[dict] = []
    for report in reports:
        decisions.update(report["transform"]["decision_counts"])
        validation = report["validation"]
        preflight = report["preflight"]
        render = report.get("render")
        files.append({
            "surah": preflight["identity"]["surah"],
            "input_path": preflight["input"]["path"],
            "output_path": report["output_path"],
            "input_sha256": validation["input_sha256"],
            "output_sha256": validation["output_sha256"],
            "input_target_characters": report["transform"]["input_target_character_count"],
            "output_target_characters": report["transform"]["output_target_character_count"],
            "unknown_count": preflight["unknown_count"],
            "unresolved_count": report["transform"]["unresolved_count"],
            "automated_pass": validation["all_required_checks_passed"],
            "render": render,
        })
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": files,
        "file_count": len(files),
        "combined_decision_counts": dict(sorted(decisions.items())),
        "unknown_count": sum(item["unknown_count"] for item in files),
        "unresolved_count": sum(item["unresolved_count"] for item in files),
        "word_boundary_repairs": sum(
            report["transform"]["word_boundary_repairs"] for report in reports
        ),
        "automated_pass": all(item["automated_pass"] for item in files),
        "visual_qa_complete": all(
            bool(item.get("render") and item["render"].get("visual_qa_complete")) for item in files
        ),
    }


def combined_final_markdown(report: dict) -> str:
    lines = [
        "# Combined final audit",
        "",
        f"Automated status: **{'PASS' if report['automated_pass'] else 'FAIL'}**; unknown: {report['unknown_count']}; unresolved: {report['unresolved_count']}; word-boundary repairs: {report['word_boundary_repairs']}.",
        "",
        "| Surah | Input SHA-256 | Output SHA-256 | Characters | Automated | Render pages | Visual QA |",
        "|---|---|---|---:|---|---:|---|",
    ]
    for item in report["files"]:
        render = item.get("render") or {}
        lines.append(
            f"| {item['surah']} | `{item['input_sha256']}` | `{item['output_sha256']}` | {item['input_target_characters']} → {item['output_target_characters']} | {'PASS' if item['automated_pass'] else 'FAIL'} | {render.get('page_count', 'not run')} | {render.get('visual_qa_status', 'not reviewed')} |"
        )
    lines.append("")
    return "\n".join(lines)
