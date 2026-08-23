"""Small, deliberately independent in-memory reference transformer.

This oracle shares only declarative rule constants with the production OOXML
path.  It does not call the production token transducer or its callbacks.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
import unicodedata

from .rules import (
    LONG_VOWELS,
    MUQATTAAT_SKELETONS,
    RAW_DELETE_SEQUENCES,
    SIMPLE_TRANSFORMS,
    is_arabic_or_quranic,
    is_effective_delete,
    is_numeric_char,
    is_standalone_separator,
)


class ReferenceStrictError(RuntimeError):
    pass


@dataclass
class RefUnit:
    char: str
    source: tuple[int, ...]
    introduced: bool = False


def _base_before(chars: list[str], index: int) -> int | None:
    cursor = index - 1
    while cursor >= 0:
        char = chars[cursor]
        if char.isspace():
            return None
        if not unicodedata.category(char).startswith("M"):
            return ord(char)
        cursor -= 1
    return None


def _muqattaat_positions(chars: list[str], at_start: bool) -> set[int]:
    if not at_start:
        return set()
    begin = 0
    while begin < len(chars) and chars[begin].isspace():
        begin += 1
    finish = begin
    while finish < len(chars) and not chars[finish].isspace():
        finish += 1
    skeleton = "".join(
        char for char in chars[begin:finish]
        if not unicodedata.category(char).startswith("M")
    )
    if skeleton not in MUQATTAAT_SKELETONS:
        return set()
    return {i for i in range(begin, finish) if ord(chars[i]) == 0x0653}


def _decorative_bismillah(chars: list[str], index: int) -> bool:
    remaining = chars[:index] + chars[index + 1:]
    skeleton = "".join(
        char for char in remaining
        if not char.isspace() and not unicodedata.category(char).startswith("M")
    )
    return "بسمٱللهٱلرحمنٱلرحيم" in skeleton or "بسماللهالرحمنالرحيم" in skeleton


def _arabic_side(units: list[RefUnit], index: int, direction: int) -> bool:
    while 0 <= index < len(units):
        char = units[index].char
        if char.isspace():
            return False
        if unicodedata.category(char).startswith("M"):
            index += direction
            continue
        return is_arabic_or_quranic(char) and unicodedata.category(char) in {"Lo", "Lm"}
    return False


def reference_transform(
    text: str,
    *,
    surah_start: bool = False,
    strict: bool = True,
    stop_classes: dict[int, str] | None = None,
) -> str:
    chars = list(text)
    stop_classes = stop_classes or {}
    muqattaat = _muqattaat_positions(chars, surah_start)
    first: list[RefUnit] = []
    separator_deletions: set[int] = set()
    deleted: set[int] = set()
    cursor = 0
    sequences = sorted(RAW_DELETE_SEQUENCES, key=len, reverse=True)

    while cursor < len(chars):
        matched = None
        for sequence in sequences:
            if tuple(ord(c) for c in chars[cursor:cursor + len(sequence)]) == sequence:
                matched = sequence
                break
        if matched is not None:
            classification = stop_classes.get(cursor, "lexical")
            if classification in {"proven", "proven_stop_sign"}:
                positions = range(cursor, cursor + len(matched))
                deleted.update(positions)
                separator_deletions.update(positions)
                cursor += len(matched)
                continue
            if classification == "unresolved" and strict:
                raise ReferenceStrictError("unresolved stop-sign sequence")
            for position in range(cursor, cursor + len(matched)):
                first.append(RefUnit(chars[position], (position,)))
            cursor += len(matched)
            continue

        char = chars[cursor]
        cp = ord(char)
        if cp == 0xFDFD:
            if not _decorative_bismillah(chars, cursor):
                if strict:
                    raise ReferenceStrictError("unresolved Bismillah ligature")
                first.append(RefUnit(char, (cursor,)))
            else:
                deleted.add(cursor)
                separator_deletions.add(cursor)
            cursor += 1
            continue
        if cp == 0x06CC:
            first.append(RefUnit("ي", (cursor,), True))
            cursor += 1
            continue
        if cp == 0x065E:
            first.append(RefUnit("ٌ", (cursor,), True))
            cursor += 1
            continue
        if cp == 0x0653:
            strip = (
                cursor in muqattaat
                or _base_before(chars, cursor) in LONG_VOWELS
                or (cursor + 1 < len(chars) and ord(chars[cursor + 1]) == 0x0627)
            )
            if strip:
                deleted.add(cursor)
            else:
                first.append(RefUnit("ا", (cursor,), True))
            cursor += 1
            continue
        if cp == 0x0657:
            if cursor + 1 < len(chars) and ord(chars[cursor + 1]) == 0x0627:
                first.append(RefUnit("ا", (cursor, cursor + 1), True))
                cursor += 2
            else:
                first.append(RefUnit("ا", (cursor,), True))
                cursor += 1
            continue
        if cp == 0x06E4:
            first.append(RefUnit("ا", (cursor,), True))
            cursor += 1
            continue
        first.append(RefUnit(char, (cursor,)))
        cursor += 1

    second: list[RefUnit] = []
    for unit in first:
        cp = ord(unit.char)
        if cp in SIMPLE_TRANSFORMS and not unit.introduced:
            second.append(RefUnit(chr(SIMPLE_TRANSFORMS[cp]), unit.source, True))
        else:
            second.append(unit)

    collapsed: list[RefUnit] = []
    for unit in second:
        if (
            collapsed and collapsed[-1].char == unit.char == "ا"
            and (collapsed[-1].introduced or unit.introduced)
        ):
            prior = collapsed[-1]
            collapsed[-1] = RefUnit("ا", prior.source + unit.source, True)
        else:
            collapsed.append(unit)

    numeric_label_nbsp_sources: set[int] = set()
    for index, unit in enumerate(collapsed):
        if not is_numeric_char(unit.char) or index < 2:
            continue
        previous = collapsed[index - 1]
        if previous.char != "\u00A0":
            continue
        if max(previous.source) + 1 != min(unit.source):
            continue
        if not _arabic_side(collapsed, index - 2, -1):
            continue
        numeric_label_nbsp_sources.update(previous.source)

    third: list[RefUnit] = []
    for unit in collapsed:
        if unit.char == "\u00A0" and any(
            source in numeric_label_nbsp_sources for source in unit.source
        ):
            deleted.update(unit.source)
            separator_deletions.update(unit.source)
        elif is_effective_delete(unit.char):
            deleted.update(unit.source)
            if is_standalone_separator(unit.char):
                separator_deletions.update(unit.source)
        else:
            third.append(unit)

    source_to_output = {
        source: output_index
        for output_index, unit in enumerate(third)
        for source in unit.source
    }
    surviving = sorted(source_to_output)
    pairs: set[tuple[int, int]] = set()
    for deletion in sorted(separator_deletions):
        point = bisect_left(surviving, deletion)
        if point == 0 or point == len(surviving):
            continue
        left = source_to_output[surviving[point - 1]]
        right = source_to_output[surviving[point]]
        if right != left + 1:
            continue
        if _arabic_side(third, left, -1) and _arabic_side(third, right, 1):
            pairs.add((left, right))
    for left, right in sorted(pairs, reverse=True):
        gap = tuple(
            position for position in sorted(separator_deletions)
            if max(third[left].source) < position < min(third[right].source)
        )
        if gap:
            third.insert(right, RefUnit(" ", gap, True))

    return "".join(unit.char for unit in third)
