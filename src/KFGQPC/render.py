"""Headless DOCX rendering and page-image manifest generation."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image, ImageChops, ImageStat


class RenderError(RuntimeError):
    pass


def _page_count(pdf: Path) -> tuple[int, str]:
    pdfinfo = shutil.which("pdfinfo")
    if not pdfinfo:
        raise RenderError("pdfinfo is unavailable")
    result = subprocess.run(
        [pdfinfo, str(pdf)], check=True, capture_output=True, text=True, timeout=60,
    )
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip()), result.stdout
    raise RenderError("pdfinfo did not report a page count")


def _image_metrics(path: Path) -> dict:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        grayscale = rgb.convert("L")
        inverted = ImageChops.invert(grayscale)
        bbox = inverted.point(lambda value: 255 if value > 10 else 0).getbbox()
        width, height = rgb.size
        stat = ImageStat.Stat(grayscale)
        mean = stat.mean[0]
        nonwhite_bbox = list(bbox) if bbox else None
        touches_edge = False
        if bbox:
            left, top, right, bottom = bbox
            touches_edge = left <= 1 or top <= 1 or right >= width - 1 or bottom >= height - 1
        return {
            "path": str(path.resolve()),
            "width": width,
            "height": height,
            "mean_luminance": round(mean, 4),
            "nonwhite_bbox": nonwhite_bbox,
            "blank": bbox is None or mean > 254.95,
            "nonwhite_touches_page_edge": touches_edge,
        }


def render_docx(docx_path: Path, render_root: Path, *, dpi: int = 160) -> dict:
    soffice = shutil.which("soffice")
    pdftoppm = shutil.which("pdftoppm")
    if not soffice:
        raise RenderError("soffice is unavailable")
    if not pdftoppm:
        raise RenderError("pdftoppm is unavailable")
    destination = (render_root / docx_path.stem).resolve()
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite render directory: {destination}")
    destination.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="quran-docx-render-") as work_name:
        work = Path(work_name)
        profile = work / "lo-profile"
        profile_uri = profile.resolve().as_uri()
        result = subprocess.run(
            [
                soffice,
                "--headless",
                f"-env:UserInstallation={profile_uri}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(work),
                str(docx_path.resolve()),
            ],
            check=True,
            capture_output=True,
            text=True,
            # The supplied Baqarah document contains more than 45,000 runs.
            # LibreOffice can spend several minutes laying out that single
            # run-heavy paragraph even though the compressed DOCX is small.
            timeout=1_200,
        )
        generated = work / f"{docx_path.stem}.pdf"
        if not generated.exists():
            candidates = list(work.glob("*.pdf"))
            if len(candidates) != 1:
                raise RenderError(f"LibreOffice produced no unambiguous PDF: {result.stdout} {result.stderr}")
            generated = candidates[0]
        pdf = destination / f"{docx_path.stem}.pdf"
        shutil.copy2(generated, pdf)
    page_count, pdfinfo_output = _page_count(pdf)
    prefix = destination / "page"
    subprocess.run(
        [pdftoppm, "-png", "-r", str(dpi), str(pdf), str(prefix)],
        check=True,
        capture_output=True,
        text=True,
        timeout=600,
    )
    raw_pages = sorted(destination.glob("page-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
    if len(raw_pages) != page_count:
        raise RenderError(f"rendered page count {len(raw_pages)} != PDF page count {page_count}")
    pages: list[dict] = []
    for page_number, raw in enumerate(raw_pages, start=1):
        normalized = destination / f"page-{page_number:03d}.png"
        if raw != normalized:
            raw.rename(normalized)
        metrics = _image_metrics(normalized)
        metrics["page_number"] = page_number
        metrics["visually_reviewed"] = False
        pages.append(metrics)
    return {
        "docx_path": str(docx_path.resolve()),
        "render_directory": str(destination),
        "pdf_path": str(pdf.resolve()),
        "page_count": page_count,
        "dpi": dpi,
        "pages": pages,
        "libreoffice_stdout": result.stdout,
        "libreoffice_stderr": result.stderr,
        "pdfinfo": pdfinfo_output,
        "programmatic_blank_page_count": sum(page["blank"] for page in pages),
        "programmatic_edge_touch_count": sum(page["nonwhite_touches_page_edge"] for page in pages),
        "visual_qa_complete": False,
        "visual_qa_status": "pending_manual_review",
        "visual_qa_notes": "",
    }
