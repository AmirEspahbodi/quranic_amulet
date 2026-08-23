"""Command-line interface for strict audit and non-overwriting DOCX filtering."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import traceback

from . import SOURCE_SYMBOL_FONT, TARGET_FONT
from .audit import (
    _atomic_text,
    add_zero_match_rules,
    combined_final_markdown,
    combined_final_report,
    combined_preflight_markdown,
    final_markdown,
    preflight_markdown,
    write_json,
)
from .inventory import audit_docx, combine_preflights
from .ooxml import PackageError
from .render import RenderError, render_docx
from .transformer import StrictTransformError, transform_docx_to_bytes
from .validation import validate_output


EXIT_OK = 0
EXIT_ARGUMENT = 2
EXIT_PREFLIGHT_BLOCKED = 3
EXIT_PROCESSING_FAILED = 4
EXIT_VALIDATION_FAILED = 5
EXIT_WOULD_OVERWRITE = 6


def _discover(paths: list[Path]) -> list[Path]:
    discovered: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved.is_dir():
            discovered.extend(
                candidate.resolve() for candidate in sorted(resolved.glob("*.docx"))
                if not candidate.name.endswith(".filtered.docx")
            )
        else:
            discovered.append(resolved)
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in discovered:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    if not unique:
        raise ValueError("no input DOCX files discovered")
    return unique


def _report_stem(path: Path) -> str:
    return path.stem


def _write_preflight_reports(report_dir: Path, preflights: list[dict]) -> dict:
    for report in preflights:
        add_zero_match_rules(report)
        stem = _report_stem(Path(report["input"]["path"]))
        write_json(report_dir / f"{stem}.preflight.json", report)
        _atomic_text(report_dir / f"{stem}.preflight.md", preflight_markdown(report))
    combined = combine_preflights(preflights)
    write_json(report_dir / "combined.preflight.json", combined)
    _atomic_text(report_dir / "combined.preflight.md", combined_preflight_markdown(combined))
    return combined


def _validated_temporary_output(
    input_path: Path,
    output_path: Path,
    package_bytes: bytes,
    transform_report: dict,
    *,
    input_sha256: str,
    target_font: str,
    source_symbol_font: str,
    deterministic_bytes_match: bool,
) -> tuple[Path, dict]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(
        prefix=f".{output_path.stem}.", suffix=".docx", dir=output_path.parent,
    )
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(package_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        validation = validate_output(
            input_path,
            temporary,
            transform_report,
            original_input_sha256=input_sha256,
            target_font=target_font,
            source_symbol_font=source_symbol_font,
            deterministic_bytes_match=deterministic_bytes_match,
        )
        if not validation["all_required_checks_passed"]:
            raise RuntimeError(
                "output validation failed: "
                + ", ".join(name for name, passed in validation["checks"].items() if not passed)
            )
        validation["output_package"]["path"] = str(output_path.resolve())
        return temporary, validation
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="one or more DOCX files or directories")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--render-dir", type=Path)
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--target-font", default=TARGET_FONT)
    parser.add_argument("--source-symbol-font", default=SOURCE_SYMBOL_FONT)
    return parser


def run(args: argparse.Namespace) -> int:
    inputs = _discover(args.inputs)
    output_dir = args.output_dir.resolve()
    report_dir = args.report_dir.resolve()
    render_dir = args.render_dir.resolve() if args.render_dir else None
    report_dir.mkdir(parents=True, exist_ok=True)

    expected_outputs = {
        path: output_dir / f"{path.stem}.filtered.docx" for path in inputs
    }
    if not args.audit_only:
        conflicts = [path for path in expected_outputs.values() if path.exists()]
        if conflicts:
            raise FileExistsError("refusing to overwrite: " + ", ".join(map(str, conflicts)))

    preflights = [
        audit_docx(
            path,
            target_font=args.target_font,
            source_symbol_font=args.source_symbol_font,
            strict=args.strict,
        )
        for path in inputs
    ]
    combined_preflight = _write_preflight_reports(report_dir, preflights)
    if not combined_preflight["preflight_ok"]:
        return EXIT_PREFLIGHT_BLOCKED
    if args.audit_only:
        return EXIT_OK

    final_reports: list[dict] = []
    for input_path, preflight in zip(inputs, preflights):
        output_path = expected_outputs[input_path]
        first = transform_docx_to_bytes(
            input_path,
            target_font=args.target_font,
            source_symbol_font=args.source_symbol_font,
            strict=args.strict,
        )
        second = transform_docx_to_bytes(
            input_path,
            target_font=args.target_font,
            source_symbol_font=args.source_symbol_font,
            strict=args.strict,
        )
        deterministic = first.package_bytes == second.package_bytes
        temporary, validation = _validated_temporary_output(
            input_path,
            output_path,
            first.package_bytes,
            first.report,
            input_sha256=preflight["input"]["sha256"],
            target_font=args.target_font,
            source_symbol_font=args.source_symbol_font,
            deterministic_bytes_match=deterministic,
        )
        if output_path.exists():
            temporary.unlink(missing_ok=True)
            raise FileExistsError(f"refusing to overwrite: {output_path}")
        os.replace(temporary, output_path)

        render = None
        if render_dir is not None:
            render = render_docx(output_path, render_dir)
        report = {
            "schema_version": 1,
            "target_font": args.target_font,
            "source_symbol_font": args.source_symbol_font,
            "strict": args.strict,
            "input_path": str(input_path),
            "output_path": str(output_path.resolve()),
            "preflight": preflight,
            "transform": first.report,
            "validation": validation,
            "render": render,
            "final_automated_pass": validation["all_required_checks_passed"],
        }
        stem = _report_stem(input_path)
        write_json(report_dir / f"{stem}.audit.json", report)
        _atomic_text(report_dir / f"{stem}.audit.md", final_markdown(report))
        final_reports.append(report)

    combined = combined_final_report(final_reports)
    write_json(report_dir / "combined.audit.json", combined)
    _atomic_text(report_dir / "combined.audit.md", combined_final_markdown(combined))
    return EXIT_OK if combined["automated_pass"] else EXIT_VALIDATION_FAILED


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except FileExistsError as exc:
        print(f"refusing overwrite: {exc}")
        return EXIT_WOULD_OVERWRITE
    except (ValueError, PackageError) as exc:
        print(f"argument/package error: {exc}")
        return EXIT_ARGUMENT
    except StrictTransformError as exc:
        print(f"strict transformation blocked: {exc}")
        if exc.blockers:
            print(json.dumps(exc.blockers, ensure_ascii=False, indent=2))
        return EXIT_PREFLIGHT_BLOCKED
    except RenderError as exc:
        print(f"rendering failed: {exc}")
        return EXIT_VALIDATION_FAILED
    except Exception as exc:
        print(f"processing failed: {exc}")
        traceback.print_exc()
        return EXIT_PROCESSING_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
