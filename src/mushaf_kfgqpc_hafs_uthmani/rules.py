"""Declarative raw rule ledger and its effective resolution.

No normalization is performed anywhere in this module.  Every key is an exact
Unicode scalar value or exact multi-codepoint tuple copied from the supplied
100-row ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
import unicodedata


@dataclass(frozen=True)
class RawRule:
    source: tuple[int, ...]
    action: str
    target: tuple[int, ...] = ()
    label: str = ""


KEEP_CODEPOINTS = (
    0x0623, 0x0624, 0x0626, 0x0627, 0x0628, 0x0629, 0x062A, 0x062B,
    0x062C, 0x062D, 0x062E, 0x062F, 0x0630, 0x0631, 0x0632, 0x0633,
    0x0634, 0x0635, 0x0636, 0x0637, 0x0638, 0x0639, 0x063A, 0x0641,
    0x0642, 0x0643, 0x0644, 0x0645, 0x0646, 0x0647, 0x0648, 0x064A,
    0x064B, 0x064C, 0x064D, 0x064E, 0x064F, 0x0650, 0x0652, 0x0654,
    0x0656, 0x06E1, 0x06E9, 0x0020, 0x00A0, 0x0655, 0x200C, 0x200D,
    0x200E, 0x200F,
)

RAW_TRANSFORMS = {
    0x0621: 0x0627,
    0x0625: 0x0627,
    0x0649: 0x0627,
    0x0653: 0x0627,
    0x0657: 0x0627,
    0x0670: 0x0627,
    0x06E4: 0x0627,
    0x06E6: 0x064A,
    0x06E7: 0x064A,
    0x06ED: 0x0645,
    0x0671: 0x0627,
    0x0622: 0x0627,
    0x06E3: 0x062B,
}

# These are the 34 single-codepoint rows in the raw DELETE section.  U+065E
# is deliberately present here because this is the raw ledger; E1 overrides it.
RAW_DELETE_CODEPOINTS = (
    0x0651, 0x065E, 0x06D6, 0x06D7, 0x06D8, 0x06DA, 0x06DB, 0x06DC,
    0x06DE, 0x06E0, 0x06E2, 0x06E5, 0x06EC, 0x0031, 0x0034, 0x0035,
    0x0660, 0x0661, 0x0662, 0x0663, 0x0664, 0x0665, 0x0666, 0x0667,
    0x0668, 0x0669, 0x002D, 0x003A, 0x0640, 0x06EB, 0x06D4, 0x06DD,
    0xFDFD, 0xFDFB,
)

RAW_DELETE_SEQUENCES = (
    (0x0644, 0x0627),
    (0x0642, 0x0644, 0x064A),
    (0x0635, 0x0644, 0x064A),
)

RAW_RULES = tuple(
    [RawRule((cp,), "KEEP", label=f"U+{cp:04X}") for cp in KEEP_CODEPOINTS]
    + [
        RawRule((cp,), "TRANSFORM", (target,), label=f"U+{cp:04X}->U+{target:04X}")
        for cp, target in RAW_TRANSFORMS.items()
    ]
    + [RawRule((cp,), "DELETE", label=f"U+{cp:04X}") for cp in RAW_DELETE_CODEPOINTS]
    + [
        RawRule(seq, "DELETE", label="+".join(f"U+{cp:04X}" for cp in seq))
        for seq in RAW_DELETE_SEQUENCES
    ]
)

if len(KEEP_CODEPOINTS) != 50 or len(RAW_TRANSFORMS) != 13:
    raise AssertionError("raw KEEP/TRANSFORM ledger cardinality changed")
if len(RAW_DELETE_CODEPOINTS) + len(RAW_DELETE_SEQUENCES) != 37:
    raise AssertionError("raw DELETE ledger cardinality changed")
if len(RAW_RULES) != 100:
    raise AssertionError("raw ledger must contain exactly 100 rows")


# Effective overrides E1, E2, E3, and E4.
EFFECTIVE_OVERRIDES = {
    0x065E: 0x064C,
    0x06CC: 0x064A,
}

CONTEXTUAL_CODEPOINTS = frozenset({0x0653, 0x0657, 0x06E4})
SIMPLE_TRANSFORMS = {
    cp: target for cp, target in RAW_TRANSFORMS.items() if cp not in CONTEXTUAL_CODEPOINTS
} | EFFECTIVE_OVERRIDES

EFFECTIVE_DELETE_CODEPOINTS = frozenset(
    set(RAW_DELETE_CODEPOINTS) - {0x065E, 0xFDFD} | {0xFDFA}
)

ALEF_PRODUCING_SOURCES = frozenset(
    cp for cp, target in (RAW_TRANSFORMS | EFFECTIVE_OVERRIDES).items() if target == 0x0627
)

MUQATTAAT_SKELETONS = frozenset(
    {
        "الم", "المص", "الر", "المر", "كهيعص", "طه", "طسم", "طس",
        "يس", "ص", "حم", "حم عسق", "عسق", "ق", "ن",
    }
)

LONG_VOWELS = frozenset({0x0627, 0x0648, 0x064A})
NUMERIC_CATEGORIES = frozenset({"Nd", "Nl", "No"})

# Deletions that are spacing-neutral attached/formatting marks are omitted.
STANDALONE_SEPARATOR_CODEPOINTS = frozenset(
    {0x002D, 0x003A, 0x06DE, 0x06D4, 0x06DD, 0xFDFA, 0xFDFB, 0xFDFD}
)


def is_numeric_char(char: str) -> bool:
    return unicodedata.category(char) in NUMERIC_CATEGORIES


def is_effective_delete(char: str) -> bool:
    return ord(char) in EFFECTIVE_DELETE_CODEPOINTS or is_numeric_char(char)


def is_standalone_separator(char: str) -> bool:
    return is_numeric_char(char) or ord(char) in STANDALONE_SEPARATOR_CODEPOINTS


def is_arabic_or_quranic(char: str) -> bool:
    cp = ord(char)
    in_block = (
        0x0600 <= cp <= 0x06FF
        or 0x0750 <= cp <= 0x077F
        or 0x0870 <= cp <= 0x089F
        or 0x08A0 <= cp <= 0x08FF
        or 0xFB50 <= cp <= 0xFDFF
        or 0xFE70 <= cp <= 0xFEFF
    )
    return in_block or "ARABIC" in unicodedata.name(char, "")


def known_effective_source(char: str) -> bool:
    cp = ord(char)
    return (
        cp in KEEP_CODEPOINTS
        or cp in RAW_TRANSFORMS
        or cp in EFFECTIVE_OVERRIDES
        or cp in EFFECTIVE_DELETE_CODEPOINTS
        or is_numeric_char(char)
    )


def raw_counts() -> dict[str, int]:
    counts = {"KEEP": 0, "TRANSFORM": 0, "DELETE": 0}
    for rule in RAW_RULES:
        counts[rule.action] += 1
    return counts


def effective_action(source: tuple[int, ...]) -> tuple[str, tuple[int, ...]]:
    """Resolve a raw/effective key to its one authorized action."""
    if len(source) > 1:
        if source not in RAW_DELETE_SEQUENCES:
            raise KeyError(source)
        return "CONTEXT_GUARDED_DELETE", ()
    cp = source[0]
    if cp in EFFECTIVE_OVERRIDES:
        return "TRANSFORM", (EFFECTIVE_OVERRIDES[cp],)
    if cp == 0xFDFD:
        return "CONTEXT_GUARDED_DELETE", ()
    if cp in RAW_TRANSFORMS:
        action = "CONTEXTUAL_TRANSFORM" if cp in CONTEXTUAL_CODEPOINTS else "TRANSFORM"
        return action, (RAW_TRANSFORMS[cp],)
    if cp in KEEP_CODEPOINTS:
        return "KEEP", (cp,)
    if cp in EFFECTIVE_DELETE_CODEPOINTS:
        return "DELETE", ()
    raise KeyError(source)


def all_rule_labels() -> list[str]:
    labels = [rule.label for rule in RAW_RULES]
    labels.extend(["E2_U+06CC_to_U+064A", "E4_U+FDFA_delete", "E3_numeric_category"])
    return labels

