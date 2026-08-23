#!/usr/bin/env python3
"""Batch DOCX filter runner built on top of the package CLI (cli.py).

Scans a source folder for ``*.docx`` files and runs every single one
through the strict filtering pipeline of the wrapped CLI module. Each
filtered document is saved in the destination folder as
``<original-stem>.filtered.docx``.

Every file is processed through its own CLI invocation, so a failure on
one document never blocks the rest of the batch.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Locate the filtering package that contains the provided cli.py.
#
# cli.py uses relative imports ("from . import ..."), therefore it MUST be
# imported as part of a package. Adjust PACKAGE_NAME / PACKAGE_PARENT if
# your project layout is different.
# ---------------------------------------------------------------------------
PACKAGE_NAME = "src.KFGQPC"                      # <-- change if needed
PACKAGE_PARENT = Path(__file__).resolve().parent  # folder holding the package

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

try:
    cli = importlib.import_module(f"{PACKAGE_NAME}.cli")
except ImportError as exc:  # pragma: no cover - guidance for setup mistakes
    sys.stderr.write(
        f"Cannot import package '{PACKAGE_NAME}': {exc}\n"
        "Make sure cli.py lives inside a package folder (with __init__.py)\n"
        "and fix PACKAGE_NAME / PACKAGE_PARENT at the top of this script.\n"
    )
    raise

# Re-export the pieces of the CLI this wrapper relies on.
cli_main = cli.main
EXIT_OK = cli.EXIT_OK
EXIT_ARGUMENT = cli.EXIT_ARGUMENT
EXIT_PREFLIGHT_BLOCKED = cli.EXIT_PREFLIGHT_BLOCKED
EXIT_PROCESSING_FAILED = cli.EXIT_PROCESSING_FAILED
EXIT_VALIDATION_FAILED = cli.EXIT_VALIDATION_FAILED
EXIT_WOULD_OVERWRITE = cli.EXIT_WOULD_OVERWRITE

# Exit code reserved by this wrapper: batch finished with mixed results.
EXIT_PARTIAL = 7

# Human readable meaning of every CLI exit code (used in the summary).
EXIT_LABELS: dict[int, str] = {
    EXIT_OK: "ok",
    EXIT_ARGUMENT: "argument/package error",
    EXIT_PREFLIGHT_BLOCKED: "preflight blocked",
    EXIT_PROCESSING_FAILED: "processing failed",
    EXIT_VALIDATION_FAILED: "validation failed",
    EXIT_WOULD_OVERWRITE: "refused to overwrite",
}


def collect_docx_files(source_dir: Path, recursive: bool) -> list[Path]:
    """Return sorted, resolved DOCX files found inside ``source_dir``.

    Files already produced by a previous run (``*.filtered.docx``) are
    skipped, which makes re-running the script on a mixed folder safe.
    """
    if not source_dir.is_dir():
        raise NotADirectoryError(f"source folder not found: {source_dir}")

    pattern = "**/*.docx" if recursive else "*.docx"
    found = {
        path.resolve()
        for path in source_dir.glob(pattern)
        if path.is_file() and not path.name.endswith(".filtered.docx")
    }
    return sorted(found)


def ensure_unique_stems(files: list[Path]) -> None:
    """Fail early when two inputs share the same stem.

    The CLI writes outputs flat into the destination folder using the
    input stem, so duplicate stems would collide (or trigger the CLI's
    overwrite protection halfway through the batch).
    """
    seen: dict[str, Path] = {}
    for path in files:
        twin = seen.get(path.stem)
        if twin is not None:
            raise ValueError(
                f"duplicate stem '{path.stem}': {twin} and {path} "
                "would produce the same output file"
            )
        seen[path.stem] = path


def clear_previous_outputs(files: list[Path], dest_dir: Path) -> int:
    """Remove outputs of previous runs (only used with --overwrite).

    Only the exact ``<stem>.filtered.docx`` paths this batch is about to
    regenerate are deleted; unrelated files in dest_dir stay untouched.
    """
    removed = 0
    for path in files:
        target = dest_dir / f"{path.stem}.filtered.docx"
        if target.exists():
            target.unlink()
            removed += 1
    return removed


def build_cli_argv(docx_path: Path, args: argparse.Namespace) -> list[str]:
    """Assemble the argv vector for a single cli.main() invocation."""
    argv = [
        str(docx_path),
        "--output-dir", str(args.dest_dir),
        "--report-dir", str(args.report_dir),
    ]
    if args.render_dir is not None:
        argv += ["--render-dir", str(args.render_dir)]
    if args.audit_only:
        argv.append("--audit-only")
    argv.append("--strict" if args.strict else "--no-strict")
    if args.target_font is not None:
        argv += ["--target-font", args.target_font]
    if args.source_symbol_font is not None:
        argv += ["--source-symbol-font", args.source_symbol_font]
    return argv


def print_summary(results: list[tuple[Path, int]], dest_dir: Path) -> None:
    """Print a compact pass/fail table for the whole batch."""
    line = "=" * 72
    print(f"\n{line}\nBATCH SUMMARY\n{line}")
    for path, code in results:
        label = EXIT_LABELS.get(code, f"exit code {code}")
        mark = "PASS" if code == EXIT_OK else "FAIL"
        print(f"[{mark}] {path.name}  ->  {label}")
    ok_count = sum(1 for _, code in results if code == EXIT_OK)
    print("-" * 72)
    print(f"{ok_count}/{len(results)} file(s) succeeded | outputs: {dest_dir}")


def build_parser() -> argparse.ArgumentParser:
    """Command line options of the batch wrapper."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("source_dir", type=Path,
                        help="folder containing the input DOCX files")
    parser.add_argument("dest_dir", type=Path,
                        help="destination folder for filtered DOCX files")
    parser.add_argument("--report-dir", type=Path,
                        help="folder for preflight/audit reports (default: <dest_dir>/reports)")
    parser.add_argument("--render-dir", type=Path,
                        help="optional folder for rendered previews")
    parser.add_argument("--recursive", action="store_true",
                        help="also scan subfolders of source_dir")
    parser.add_argument("--audit-only", action="store_true",
                        help="only audit the files, do not write filtered outputs")
    parser.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True,
                        help="run the pipeline in strict mode (default: on)")
    parser.add_argument("--target-font", default=None,
                        help="override the target font (defaults to package default)")
    parser.add_argument("--source-symbol-font", default=None,
                        help="override the source symbol font (defaults to package default)")
    parser.add_argument("--overwrite", action="store_true",
                        help="delete matching *.filtered.docx outputs before running")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Resolve every folder up front so all reports use absolute paths.
    source_dir = args.source_dir.resolve()
    dest_dir = args.dest_dir.resolve()
    report_dir = (args.report_dir or dest_dir / "reports").resolve()
    render_dir = args.render_dir.resolve() if args.render_dir else None

    try:
        files = collect_docx_files(source_dir, args.recursive)
        if not files:
            raise ValueError(f"no DOCX files found in: {source_dir}")
        ensure_unique_stems(files)
    except (NotADirectoryError, ValueError) as exc:
        print(f"error: {exc}")
        return EXIT_ARGUMENT

    # Create destination folders before the batch starts.
    dest_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    # Opt-in cleanup of previous outputs (makes the batch re-runnable).
    if args.overwrite and not args.audit_only:
        removed = clear_previous_outputs(files, dest_dir)
        if removed:
            print(f"--overwrite: removed {removed} old filtered file(s) in {dest_dir}")

    # Normalise the namespace so build_cli_argv sees resolved paths.
    args.dest_dir, args.report_dir, args.render_dir = dest_dir, report_dir, render_dir

    # cli.main() never raises: it catches everything, prints its own
    # diagnostics and returns an exit code - exactly what we need to keep
    # the batch going after a single-file failure.
    results: list[tuple[Path, int]] = []
    for index, docx_path in enumerate(files, start=1):
        print(f"\n({index}/{len(files)}) filtering: {docx_path.name}")
        results.append((docx_path, cli_main(build_cli_argv(docx_path, args))))

    print_summary(results, dest_dir)

    codes = {code for _, code in results}
    if codes == {EXIT_OK}:
        return EXIT_OK          # everything succeeded
    if len(codes) == 1:
        return codes.pop()      # everything failed for the same reason
    return EXIT_PARTIAL         # mixed outcome, see the summary above


if __name__ == "__main__":
    raise SystemExit(main())
