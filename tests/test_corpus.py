from __future__ import annotations

import pytest

from quran_docx_filter.inventory import audit_docx
from quran_docx_filter.transformer import transform_docx_to_bytes


def test_all_discovered_corpus_inputs_pass_strict_preflight(corpus_docx_paths):
    assert len(corpus_docx_paths) >= 3
    reports = [audit_docx(path, strict=True) for path in corpus_docx_paths]
    assert {report["identity"]["surah"] for report in reports} >= {
        "Al-Fatihah", "Al-Baqarah", "Fussilat"
    }
    assert all(report["preflight_ok"] for report in reports)
    assert sum(report["unknown_count"] for report in reports) == 0
    assert sum(report["unresolved_count"] for report in reports) == 0


@pytest.mark.parametrize("split", [False, True])
def test_constructed_corpus_style_cross_run_oracle(make_segment, split):
    source = "ال\u0653م\u0653 ١ ذَٰلِكَ مَرَض\u0657ا وَقَالُو\u0653ا"
    segment = make_segment(source, split_every_char=split, surah_start=True)
    result = __import__("quran_docx_filter.transformer", fromlist=["transform_segment"]).transform_segment(segment)
    assert result.lineage_complete


def test_all_extracted_corpus_paragraph_streams_match_oracle(corpus_docx_paths):
    for path in corpus_docx_paths:
        result = transform_docx_to_bytes(path, strict=True)
        assert all(item["independent_oracle_match"] for item in result.report["segments"])

