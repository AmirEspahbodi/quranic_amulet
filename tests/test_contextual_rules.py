from __future__ import annotations

import pytest

from quran_docx_filter.reference import ReferenceStrictError, reference_transform
from quran_docx_filter.transformer import StrictTransformError, transform_segment


@pytest.mark.parametrize(
    "source,expected,surah_start",
    [
        ("مَرَض\u0657ا", "مَرَضا", False),
        ("فِي\u0653", "فِي", False),
        # Maddah is stripped from the long Waw; the separate raw U+0621 rule
        # then maps the following standalone Hamza to Alef.
        ("سُو\u0653ءَ", "سُواَ", False),
        ("ال\u0653م\u0653", "الم", True),
        ("و\u0653ا", "وا", False),
        ("ب\u0653", "با", False),
        ("ب\u0657", "با", False),
        ("ب\u06e4", "با", False),
        ("\u065e", "\u064c", False),
        ("\u06cc", "\u064a", False),
    ],
)
def test_required_golden_contexts(make_segment, source, expected, surah_start):
    production = transform_segment(make_segment(source, surah_start=surah_start), strict=True)
    oracle = reference_transform(source, surah_start=surah_start, strict=True)
    assert production.text == expected
    assert oracle == expected


def test_muqattaat_logic_is_position_guarded(make_segment):
    source = "قال ال\u0653م\u0653"
    result = transform_segment(make_segment(source, surah_start=False), strict=True)
    assert result.text != "قال الم"


def test_literal_double_alef_is_not_globally_collapsed(make_segment):
    assert transform_segment(make_segment("اا"), strict=True).text == "اا"


def test_new_duplicate_alef_has_transformation_lineage(make_segment):
    result = transform_segment(make_segment("ءا"), strict=True)
    assert result.text == "ا"
    assert result.decisions["C6_new_duplicate_Alef_collapse"] == 1


def test_shadda_deleted_without_base(make_segment):
    assert transform_segment(make_segment("ب\u0651"), strict=True).text == "ب"


def test_lexical_lam_alef_remains(make_segment):
    result = transform_segment(make_segment("لا"), strict=True)
    assert result.text == "لا"
    assert result.decisions["stop_sequence:lexical"] == 1


def test_proven_raised_stop_sequence_may_be_deleted(make_segment):
    segment = make_segment("بلا ت", raised_indices={1, 2})
    result = transform_segment(segment, strict=True)
    assert result.text == "ب ت"
    assert result.decisions["stop_sequence:proven_stop_sign"] == 1


def test_unresolved_stop_sequence_fails_closed(make_segment):
    segment = make_segment("لا", ambiguous_indices={0, 1})
    with pytest.raises(StrictTransformError):
        transform_segment(segment, strict=True)
    with pytest.raises(ReferenceStrictError):
        reference_transform("لا", strict=True, stop_classes={0: "unresolved"})


def test_sole_bismillah_ligature_fails_closed(make_segment):
    with pytest.raises(StrictTransformError):
        transform_segment(make_segment("\ufdfd"), strict=True)
    with pytest.raises(ReferenceStrictError):
        reference_transform("\ufdfd", strict=True)


def test_decorative_bismillah_ligature_is_deleted(make_segment):
    source = "بسم الله الرحمن الرحيم \ufdfd"
    assert transform_segment(make_segment(source), strict=True).text == "بسم الله الرحمن الرحيم "
    assert reference_transform(source, strict=True) == "بسم الله الرحمن الرحيم "


def test_honorific_ligatures_deleted_and_counted_separately(make_segment):
    result = transform_segment(make_segment("\ufdfa \ufdfb"), strict=True)
    assert result.text == " "
    assert result.decisions["E4_U+FDFA_delete"] == 1
    assert result.decisions["E4_U+FDFB_delete"] == 1
