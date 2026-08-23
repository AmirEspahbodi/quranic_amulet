from __future__ import annotations

from collections import Counter

import pytest

from quran_docx_filter.rules import (
    EFFECTIVE_OVERRIDES,
    KEEP_CODEPOINTS,
    RAW_DELETE_CODEPOINTS,
    RAW_DELETE_SEQUENCES,
    RAW_RULES,
    RAW_TRANSFORMS,
    effective_action,
    raw_counts,
)
from quran_docx_filter.transformer import transform_segment


def test_raw_ledger_has_exactly_100_rows():
    assert len(RAW_RULES) == 100


def test_raw_action_counts_are_authoritative():
    assert raw_counts() == {"KEEP": 50, "TRANSFORM": 13, "DELETE": 37}


def test_no_blank_or_duplicate_raw_rows():
    assert all(rule.action and rule.source for rule in RAW_RULES)
    assert len({(rule.source, rule.action) for rule in RAW_RULES}) == 100


def test_e1_overrides_raw_delete():
    assert 0x065E in RAW_DELETE_CODEPOINTS
    assert EFFECTIVE_OVERRIDES[0x065E] == 0x064C
    assert effective_action((0x065E,)) == ("TRANSFORM", (0x064C,))


@pytest.mark.parametrize("codepoint", KEEP_CODEPOINTS)
def test_every_keep_codepoint_is_byte_identical(make_segment, codepoint):
    char = chr(codepoint)
    result = transform_segment(make_segment(char), strict=True)
    assert result.text == char


@pytest.mark.parametrize("codepoint,target", RAW_TRANSFORMS.items())
def test_every_raw_transform_has_effective_behavior(make_segment, codepoint, target):
    result = transform_segment(make_segment(chr(codepoint)), strict=True)
    assert result.text == chr(target)


@pytest.mark.parametrize("sequence", RAW_DELETE_SEQUENCES)
def test_every_context_guarded_sequence_resolves_uniquely(sequence):
    assert effective_action(sequence) == ("CONTEXT_GUARDED_DELETE", ())


def test_every_single_raw_row_has_one_effective_action():
    for rule in RAW_RULES:
        action, target = effective_action(rule.source)
        assert action in {"KEEP", "TRANSFORM", "CONTEXTUAL_TRANSFORM", "DELETE", "CONTEXT_GUARDED_DELETE"}

