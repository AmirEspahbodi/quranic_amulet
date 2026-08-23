from __future__ import annotations

import unicodedata

import pytest

from quran_docx_filter.rules import RAW_DELETE_CODEPOINTS
from quran_docx_filter.transformer import StrictTransformError, transform_segment


EXPECTED_OVERRIDE = {0x065E: "\u064c"}
CONTEXT_GUARDED = {0xFDFD}


@pytest.mark.parametrize("codepoint", RAW_DELETE_CODEPOINTS)
def test_every_raw_single_delete_row_is_exercised(make_segment, codepoint):
    if codepoint in CONTEXT_GUARDED:
        with pytest.raises(StrictTransformError):
            transform_segment(make_segment(chr(codepoint)), strict=True)
    else:
        assert transform_segment(make_segment(chr(codepoint)), strict=True).text == EXPECTED_OVERRIDE.get(codepoint, "")


@pytest.mark.parametrize(
    "codepoint",
    list(range(0x0030, 0x003A)) + list(range(0x0660, 0x066A)) + list(range(0x06F0, 0x06FA)),
)
def test_all_three_decimal_digit_ranges_deleted(make_segment, codepoint):
    assert transform_segment(make_segment(chr(codepoint)), strict=True).text == ""


def test_numeric_outside_list_uses_unicode_category(make_segment):
    char = "\u2167"  # ROMAN NUMERAL EIGHT, category Nl
    assert unicodedata.category(char) == "Nl"
    result = transform_segment(make_segment(char), strict=True)
    assert result.text == ""
    assert result.decisions["E3_numeric_category_delete"] == 1


def test_separator_deletion_repairs_exactly_one_space(make_segment):
    result = transform_segment(make_segment("ب\u06ddت"), strict=True)
    assert result.text == "ب ت"
    assert result.word_boundary_repairs == 1


def test_numeric_label_cleanup_removes_its_preceding_nbsp(make_segment):
    result = transform_segment(make_segment("ب\u00a0١ ت"), strict=True)
    assert result.text == "ب ت"
    assert result.word_boundary_repairs == 1
    assert result.decisions["C8_numeric_label_NBSP_cleanup"] == 1


def test_terminal_numeric_label_cleanup_leaves_no_trailing_nbsp(make_segment):
    result = transform_segment(make_segment("ب\u00a0١"), strict=True)
    assert result.text == "ب"
    assert result.word_boundary_repairs == 1


def test_unrelated_nbsp_is_preserved(make_segment):
    result = transform_segment(make_segment("ب\u00a0ت"), strict=True)
    assert result.text == "ب\u00a0ت"
    assert result.word_boundary_repairs == 0


@pytest.mark.parametrize("separator", ["\u0651", "\u0640"])
def test_attached_or_formatting_deletion_inserts_no_space(make_segment, separator):
    assert transform_segment(make_segment("ب" + separator + "ت"), strict=True).text == "بت"
