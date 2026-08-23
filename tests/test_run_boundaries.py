from __future__ import annotations

import pytest

from quran_docx_filter.transformer import transform_segment


@pytest.mark.parametrize(
    "source,expected,surah_start",
    [
        ("مَرَض\u0657ا", "مَرَضا", False),
        ("فِي\u0653", "فِي", False),
        ("و\u0653ا", "وا", False),
        ("ال\u0653م\u0653", "الم", True),
        ("ب\u0651ت", "بت", False),
        ("ب\u06ddت", "ب ت", False),
    ],
)
def test_one_run_and_every_character_split_are_identical(make_segment, source, expected, surah_start):
    single = transform_segment(make_segment(source, surah_start=surah_start), strict=True)
    split = transform_segment(
        make_segment(source, split_every_char=True, surah_start=surah_start), strict=True,
    )
    assert single.text == split.text == expected
    if "\u0657ا" in source or "\u0653ا" in source:
        assert any(event.cross_run for event in split.events)


def test_combining_marks_split_across_runs_keep_order(make_segment):
    source = "ب\u064e\u0650ت"
    result = transform_segment(make_segment(source, split_every_char=True), strict=True)
    assert result.text == source

