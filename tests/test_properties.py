from __future__ import annotations

import random
import unicodedata

import pytest

from quran_docx_filter.reference import reference_transform
from quran_docx_filter.rules import KEEP_CODEPOINTS
from quran_docx_filter.transformer import transform_segment


@pytest.mark.parametrize(
    "source,surah_start",
    [
        ("بِسْمِ ٱللَّهِ", False),
        ("ال\u0653م\u0653 ١ ذَٰلِكَ", True),
        ("مَرَض\u0657ا\u06d6 وَقَالُو\u0653ا", False),
        ("فِي\u0653 سُو\u0653ءَ غِشَٰوَة\u065e", False),
        ("ب\u06ddت", False),
    ],
)
def test_production_matches_independent_oracle(make_segment, source, surah_start):
    production = transform_segment(make_segment(source, surah_start=surah_start), strict=True).text
    oracle = reference_transform(source, surah_start=surah_start, strict=True)
    assert production == oracle


@pytest.mark.parametrize(
    "source",
    [
        "مَرَض\u0657ا",
        "فِي\u0653",
        "ب\u0651\u06ddت",
        "\u0621\u0627 \u0670 \u06e6 \u06ed",
        "٠١٢٣۴۵۶۷۸۹",
    ],
)
def test_idempotence(make_segment, source):
    first = transform_segment(make_segment(source), strict=True).text
    second = transform_segment(make_segment(first), strict=True).text
    assert second == first


def test_no_output_character_lacks_lineage(make_segment):
    segment = make_segment("ب\u06ddت \u0621\u0627")
    result = transform_segment(segment, strict=True)
    assert result.lineage_complete
    assert all(token.sources for token in result.output_tokens)


def test_unknown_arabic_character_is_not_silently_changed(make_segment):
    source = "\u08a0"
    result = transform_segment(make_segment(source), strict=True)
    assert result.text == source


def test_protected_base_letters_survive(make_segment):
    source = "\u062c\u0635\u0637\u0642\u0645"
    assert transform_segment(make_segment(source), strict=True).text == source


def test_keep_fuzz_preserves_order_and_bytes(make_segment):
    rng = random.Random(20260822)
    source = "".join(chr(rng.choice(KEEP_CODEPOINTS)) for _ in range(500))
    result = transform_segment(make_segment(source), strict=True)
    assert result.text == source


def test_no_normalization_or_combining_reorder(make_segment):
    source = "ب\u0650\u064e"
    assert transform_segment(make_segment(source), strict=True).text == source
