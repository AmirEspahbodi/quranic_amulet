from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest

from quran_docx_filter.ooxml import PackageError, inspect_package


def test_rejects_non_zip_docx(tmp_path: Path):
    path = tmp_path / "bad.docx"
    path.write_text("not a zip", encoding="utf-8")
    with pytest.raises(PackageError):
        inspect_package(path)


def test_rejects_path_traversal_member(tmp_path: Path):
    path = tmp_path / "traversal.docx"
    with ZipFile(path, "w") as package:
        package.writestr("[Content_Types].xml", "<Types/>")
        package.writestr("_rels/.rels", "<Relationships/>")
        package.writestr("word/document.xml", "<document/>")
        package.writestr("../escape", "x")
    with pytest.raises(PackageError, match="unsafe ZIP member"):
        inspect_package(path)


def test_rejects_missing_required_parts(tmp_path: Path):
    path = tmp_path / "missing.docx"
    with ZipFile(path, "w") as package:
        package.writestr("word/document.xml", "<document/>")
    with pytest.raises(PackageError, match="missing required"):
        inspect_package(path)

