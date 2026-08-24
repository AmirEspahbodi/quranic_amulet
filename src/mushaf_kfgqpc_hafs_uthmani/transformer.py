"""Production lineage-preserving Unicode token transducer and DOCX processor."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from bisect import bisect_left
import re
import unicodedata
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

from . import SOURCE_SYMBOL_FONT, TARGET_FONT
from .ooxml import (
    NS,
    W,
    RunMetadata,
    SourceToken,
    TextSegment,
    build_package_bytes,
    extract_segments,
    inspect_package,
    load_font_resolver,
    parse_xml,
    serialize_xml,
    set_exact_run_font,
    set_text_with_space_semantics,
)
from .rules import (
    ALEF_PRODUCING_SOURCES,
    CONTEXTUAL_CODEPOINTS,
    EFFECTIVE_DELETE_CODEPOINTS,
    KEEP_CODEPOINTS,
    LONG_VOWELS,
    MUQATTAAT_SKELETONS,
    RAW_DELETE_SEQUENCES,
    SIMPLE_TRANSFORMS,
    is_arabic_or_quranic,
    is_effective_delete,
    is_numeric_char,
    is_standalone_separator,
)


class StrictTransformError(RuntimeError):
    def __init__(self, message: str, blockers: list[dict] | None = None):
        super().__init__(message)
        self.blockers = blockers or []


@dataclass
class WorkToken:
    char: str
    sources: tuple[int, ...]
    anchor: int
    introduced: bool = False
    source_chars: tuple[str, ...] = ()
    rule: str = "KEEP"


@dataclass
class Event:
    rule: str
    phase: str
    action: str
    sources: tuple[int, ...]
    source_text: str
    output_text: str
    context: str
    part: str
    paragraph: int
    segment: int
    runs: tuple[int, ...]
    cross_run: bool
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "rule": self.rule,
            "phase": self.phase,
            "action": self.action,
            "sources": list(self.sources),
            "source_codepoints": [f"U+{ord(char):04X}" for char in self.source_text],
            "source_escaped": self.source_text.encode("unicode_escape").decode("ascii"),
            "output_codepoints": [f"U+{ord(char):04X}" for char in self.output_text],
            "output_escaped": self.output_text.encode("unicode_escape").decode("ascii"),
            "context": self.context,
            "part": self.part,
            "paragraph": self.paragraph,
            "segment": self.segment,
            "runs": list(self.runs),
            "cross_run": self.cross_run,
            "detail": self.detail,
        }


@dataclass
class SegmentResult:
    text: str
    output_tokens: list[WorkToken]
    events: list[Event]
    blockers: list[dict]
    decisions: Counter
    input_count: int
    output_count: int
    lineage_complete: bool
    word_boundary_repairs: int
    unapproved_duplicate_alef: int


@dataclass
class DocumentTransformResult:
    modified_parts: dict[str, bytes]
    report: dict
    package_bytes: bytes


def escaped_context(text: str, start: int, end: int, radius: int = 14) -> str:
    return text[max(0, start - radius): min(len(text), end + radius)].encode(
        "unicode_escape"
    ).decode("ascii")


def _previous_base(tokens: list[SourceToken], index: int) -> int | None:
    for token in reversed(tokens[:index]):
        if token.char.isspace():
            break
        if not unicodedata.category(token.char).startswith("M"):
            return ord(token.char)
    return None


def _previous_base_index(tokens: list[SourceToken], index: int) -> int | None:
    for cursor in range(index - 1, -1, -1):
        if tokens[cursor].char.isspace():
            break
        if not unicodedata.category(tokens[cursor].char).startswith("M"):
            return cursor
    return None


def _initial_word_bounds(tokens: list[SourceToken]) -> tuple[int, int] | None:
    start = 0
    while start < len(tokens) and tokens[start].char.isspace():
        start += 1
    if start == len(tokens):
        return None
    end = start
    while end < len(tokens) and not tokens[end].char.isspace():
        end += 1
    return start, end


def _skeleton(chars: str) -> str:
    return "".join(char for char in chars if not unicodedata.category(char).startswith("M"))


def muqattaat_maddah_indices(tokens: list[SourceToken], surah_start: bool) -> set[int]:
    if not surah_start:
        return set()
    bounds = _initial_word_bounds(tokens)
    if bounds is None:
        return set()
    start, end = bounds
    word = "".join(token.char for token in tokens[start:end])
    if _skeleton(word) not in MUQATTAAT_SKELETONS:
        return set()
    return {i for i in range(start, end) if ord(tokens[i].char) == 0x0653}


def _positive_stop_discriminator(metadata: list[RunMetadata]) -> bool:
    if not metadata:
        return False
    for item in metadata:
        direct = dict(item.direct_fonts)
        values = set(direct.values())
        cs_symbol_only = direct.get("cs") == SOURCE_SYMBOL_FONT and TARGET_FONT not in values
        style = (item.run_style or "").lower()
        raised = item.vert_align in {"superscript"} or (
            item.position is not None and item.position.lstrip("-").isdigit() and int(item.position) > 0
        )
        named_stop_style = any(word in style for word in ("stop", "waqf", "wqf"))
        if cs_symbol_only or raised or named_stop_style:
            return True
    return False


def classify_stop_candidate(tokens: list[SourceToken], start: int, length: int) -> str:
    metadata = [token.metadata for token in tokens[start:start + length]]
    if _positive_stop_discriminator(metadata):
        return "proven_stop_sign"
    # Normal HAFS complex-script formatting is positive lexical evidence.  It
    # is how lexical Arabic is encoded in the supplied KFGQPC documents.
    if all(
        dict(item.resolved_fonts).get("cs") == TARGET_FONT
        and item.vert_align not in {"superscript"}
        and not item.position
        for item in metadata
    ):
        return "lexical"
    return "unresolved"


def _bismillah_is_decorative(text: str, ligature_index: int) -> bool:
    without_ligature = text[:ligature_index] + text[ligature_index + 1:]
    letters = "".join(
        char for char in without_ligature
        if not unicodedata.category(char).startswith("M") and not char.isspace()
    )
    candidates = ("بسمٱللهٱلرحمنٱلرحيم", "بسماللهالرحمنالرحيم")
    return any(candidate in letters for candidate in candidates)


def _event(
    segment: TextSegment,
    source_text: str,
    source_positions: tuple[int, ...],
    output: str,
    rule: str,
    phase: str,
    action: str,
    *,
    detail: str = "",
    context_positions: tuple[int, ...] | None = None,
) -> Event:
    first_source = segment.tokens[0].source_index if segment.tokens else 0
    evidence_positions = context_positions or source_positions
    local_indices = [pos - first_source for pos in evidence_positions]
    start = min(local_indices) if local_indices else 0
    end = max(local_indices) + 1 if local_indices else start
    runs = tuple(sorted({
        segment.tokens[pos - first_source].metadata.run_index
        for pos in evidence_positions
        if 0 <= pos - first_source < len(segment.tokens)
    }))
    return Event(
        rule=rule,
        phase=phase,
        action=action,
        sources=source_positions,
        source_text=source_text,
        output_text=output,
        context=escaped_context(segment.text, start, end),
        part=segment.part,
        paragraph=segment.paragraph_index,
        segment=segment.segment_index,
        runs=runs,
        cross_run=len(runs) > 1,
        detail=detail,
    )


def _token_from_source(token: SourceToken) -> WorkToken:
    return WorkToken(
        char=token.char,
        sources=(token.source_index,),
        anchor=token.source_index,
        introduced=False,
        source_chars=(token.char,),
        rule="KEEP",
    )


def _match_stop_sequence(tokens: list[SourceToken], index: int) -> tuple[int, tuple[int, ...]] | None:
    for sequence in sorted(RAW_DELETE_SEQUENCES, key=len, reverse=True):
        chars = tuple(ord(token.char) for token in tokens[index:index + len(sequence)])
        if chars == sequence:
            return len(sequence), sequence
    return None


def _is_arabic_letter(char: str) -> bool:
    return is_arabic_or_quranic(char) and unicodedata.category(char) in {"Lo", "Lm"}


def _word_side_is_arabic(tokens: list[WorkToken], index: int, direction: int) -> bool:
    i = index
    while 0 <= i < len(tokens):
        char = tokens[i].char
        if char.isspace():
            return False
        if unicodedata.category(char).startswith("M"):
            i += direction
            continue
        return _is_arabic_letter(char)
    return False


def transform_segment(segment: TextSegment, *, strict: bool = True) -> SegmentResult:
    """Apply the production transducer without normalizing or reordering text."""
    original = segment.tokens
    muqattaat = muqattaat_maddah_indices(original, segment.surah_start)
    phase1: list[WorkToken] = []
    events: list[Event] = []
    blockers: list[dict] = []
    decisions: Counter = Counter()
    deleted_source_indices: set[int] = set()
    separator_deletions: dict[int, str] = {}
    i = 0

    while i < len(original):
        token = original[i]
        char = token.char
        cp = ord(char)
        stop_match = _match_stop_sequence(original, i)
        if stop_match is not None:
            length, sequence = stop_match
            classification = classify_stop_candidate(original, i, length)
            source_slice = original[i:i + length]
            source_positions = tuple(item.source_index for item in source_slice)
            source_text = "".join(item.char for item in source_slice)
            decisions[f"stop_sequence:{classification}"] += 1
            if classification == "proven_stop_sign":
                deleted_source_indices.update(source_positions)
                for pos in source_positions:
                    separator_deletions[pos] = "E5_proven_stop_sequence"
                events.append(_event(
                    segment, source_text, source_positions, "", "E5_stop_sequence",
                    "phase1", "DELETE", detail="positive run-property discriminator",
                ))
                i += length
                continue
            if classification == "unresolved":
                record = {
                    "type": "unresolved_stop_sequence",
                    "part": segment.part,
                    "paragraph": segment.paragraph_index,
                    "segment": segment.segment_index,
                    "source_indices": list(source_positions),
                    "codepoints": [f"U+{cp_:04X}" for cp_ in sequence],
                    "context": escaped_context(segment.text, i, i + length),
                    "runs": sorted({item.metadata.run_index for item in source_slice}),
                    "metadata": [item.metadata.as_dict() for item in source_slice],
                }
                blockers.append(record)
                if strict:
                    raise StrictTransformError("unresolved stop-sign sequence", blockers)
            phase1.extend(_token_from_source(item) for item in source_slice)
            i += length
            continue

        if cp == 0xFDFD:
            if not _bismillah_is_decorative(segment.text, i):
                record = {
                    "type": "sole_or_unproven_bismillah_ligature",
                    "part": segment.part,
                    "paragraph": segment.paragraph_index,
                    "segment": segment.segment_index,
                    "source_index": token.source_index,
                    "codepoint": "U+FDFD",
                    "context": escaped_context(segment.text, i, i + 1),
                    "run": token.metadata.run_index,
                }
                blockers.append(record)
                decisions["bismillah:unresolved"] += 1
                if strict:
                    raise StrictTransformError("unresolved Bismillah ligature", blockers)
                phase1.append(_token_from_source(token))
            else:
                deleted_source_indices.add(token.source_index)
                separator_deletions[token.source_index] = "E6_decorative_bismillah"
                decisions["bismillah:decorative_duplicate"] += 1
                events.append(_event(
                    segment, char, (token.source_index,), "", "E6_decorative_bismillah",
                    "phase1", "DELETE",
                ))
            i += 1
            continue

        if cp == 0x06CC:
            phase1.append(WorkToken("ي", (token.source_index,), token.source_index, True, (char,), "E2_Farsi_Yeh"))
            decisions["E2_Farsi_Yeh"] += 1
            events.append(_event(segment, char, (token.source_index,), "ي", "E2_Farsi_Yeh", "phase1", "TRANSFORM"))
            i += 1
            continue

        if cp == 0x065E:
            phase1.append(WorkToken("ٌ", (token.source_index,), token.source_index, True, (char,), "E1_Dammatan_anomaly"))
            decisions["E1_Dammatan_anomaly"] += 1
            events.append(_event(segment, char, (token.source_index,), "ٌ", "E1_Dammatan_anomaly", "phase1", "TRANSFORM"))
            i += 1
            continue

        if cp == 0x0653:
            previous_base_index = _previous_base_index(original, i)
            event_context_positions: tuple[int, ...] = (token.source_index,)
            if i in muqattaat:
                rule = "C3_Muqattaat_strip_Maddah"
                detail = "initial allowlisted Muqatta'at skeleton"
                bounds = _initial_word_bounds(original)
                if bounds is not None:
                    event_context_positions = tuple(
                        item.source_index for item in original[bounds[0]:bounds[1]]
                    )
            elif previous_base_index is not None and ord(original[previous_base_index].char) in LONG_VOWELS:
                rule = "C2_long_vowel_strip_Maddah"
                detail = "nearest base is Alef, Waw, or Yeh"
                event_context_positions = (original[previous_base_index].source_index, token.source_index)
            elif i + 1 < len(original) and ord(original[i + 1].char) == 0x0627:
                rule = "C5_existing_Alef_strip_Maddah"
                detail = "Maddah immediately followed by existing Alef"
                event_context_positions = (token.source_index, original[i + 1].source_index)
            else:
                rule = "C5_nominal_Maddah_to_Alef"
                detail = "no contextual strip condition"
            decisions[rule] += 1
            if rule == "C5_nominal_Maddah_to_Alef":
                phase1.append(WorkToken("ا", (token.source_index,), token.source_index, True, (char,), rule))
                output = "ا"
            else:
                deleted_source_indices.add(token.source_index)
                output = ""
            events.append(_event(
                segment, char, (token.source_index,), output, rule, "phase1", "TRANSFORM",
                detail=detail, context_positions=event_context_positions,
            ))
            i += 1
            continue

        if cp == 0x0657:
            if i + 1 < len(original) and ord(original[i + 1].char) == 0x0627:
                next_token = original[i + 1]
                positions = (token.source_index, next_token.source_index)
                source_text = char + next_token.char
                rule = "C1_Inverted_Damma_plus_Alef"
                phase1.append(WorkToken("ا", positions, token.source_index, True, tuple(source_text), rule))
                decisions[rule] += 1
                events.append(_event(segment, source_text, positions, "ا", rule, "phase1", "TRANSFORM"))
                i += 2
                continue
            rule = "C1_Inverted_Damma_nominal_Alef"
            phase1.append(WorkToken("ا", (token.source_index,), token.source_index, True, (char,), rule))
            decisions[rule] += 1
            events.append(_event(segment, char, (token.source_index,), "ا", rule, "phase1", "TRANSFORM"))
            i += 1
            continue

        if cp == 0x06E4:
            rule = "C6_small_high_Maddah_to_Alef"
            phase1.append(WorkToken("ا", (token.source_index,), token.source_index, True, (char,), rule))
            decisions[rule] += 1
            events.append(_event(segment, char, (token.source_index,), "ا", rule, "phase1", "TRANSFORM"))
            i += 1
            continue

        phase1.append(_token_from_source(token))
        i += 1

    # Phase 2: declarative one-codepoint transformations not consumed above.
    phase2: list[WorkToken] = []
    for work in phase1:
        cp = ord(work.char)
        if cp in SIMPLE_TRANSFORMS and work.rule == "KEEP":
            target = chr(SIMPLE_TRANSFORMS[cp])
            rule = f"simple_U+{cp:04X}_to_U+{ord(target):04X}"
            transformed = WorkToken(
                target, work.sources, work.anchor, True, work.source_chars, rule,
            )
            phase2.append(transformed)
            decisions[rule] += 1
            events.append(_event(
                segment, work.char, work.sources, target, rule, "phase2", "TRANSFORM",
            ))
        else:
            phase2.append(work)

    # C6: collapse only an adjacent Alef pair for which at least one Alef has
    # authorized transformation provenance.  Literal source اا remains intact.
    deduped: list[WorkToken] = []
    for work in phase2:
        if (
            deduped
            and deduped[-1].char == "ا"
            and work.char == "ا"
            and (deduped[-1].introduced or work.introduced)
        ):
            previous = deduped[-1]
            merged_sources = previous.sources + tuple(pos for pos in work.sources if pos not in previous.sources)
            merged = WorkToken(
                "ا", merged_sources, previous.anchor, True,
                previous.source_chars + work.source_chars, "C6_new_duplicate_Alef_collapse",
            )
            deduped[-1] = merged
            decisions["C6_new_duplicate_Alef_collapse"] += 1
            events.append(_event(
                segment,
                "".join(previous.source_chars + work.source_chars),
                merged_sources,
                "ا",
                "C6_new_duplicate_Alef_collapse",
                "phase2",
                "COLLAPSE",
                detail="at least one adjacent Alef was introduced by an authorized mapping",
            ))
        else:
            deduped.append(work)

    # Phase 3: authorized deletions.  U+065E has already become U+064C and is
    # therefore not eligible here (E7 transformation priority).
    #
    # The supplied corpus encodes a verse boundary as Arabic text + NBSP +
    # numeric verse label (+ an ordinary space when another verse follows).
    # Once the numeric label is deleted, that immediately adjacent NBSP is no
    # longer content: internally it duplicates the surviving ordinary space,
    # and at a paragraph end it becomes a visible missing-glyph box in common
    # renderers.  Treat only this proven, source-adjacent pattern as a local
    # deletion-boundary repair; unrelated NBSP characters remain untouched.
    numeric_label_nbsp_sources: set[int] = set()
    for index, work in enumerate(deduped):
        if not is_numeric_char(work.char) or index < 2:
            continue
        previous = deduped[index - 1]
        if previous.char != "\u00A0":
            continue
        if max(previous.sources) + 1 != min(work.sources):
            continue
        if not _word_side_is_arabic(deduped, index - 2, -1):
            continue
        numeric_label_nbsp_sources.update(previous.sources)

    phase3: list[WorkToken] = []
    repairs = 0
    for work in deduped:
        if work.char == "\u00A0" and any(
            source in numeric_label_nbsp_sources for source in work.sources
        ):
            rule = "C8_numeric_label_NBSP_cleanup"
            deleted_source_indices.update(work.sources)
            for pos in work.sources:
                separator_deletions[pos] = rule
            decisions[rule] += 1
            repairs += 1
            events.append(_event(
                segment, work.char, work.sources, "", rule, "phase3", "DELETE_BOUNDARY",
                detail="NBSP immediately precedes a deleted numeric label after Arabic text",
            ))
        elif is_effective_delete(work.char):
            cp = ord(work.char)
            if is_numeric_char(work.char):
                rule = "E3_numeric_category_delete"
            elif cp == 0xFDFA:
                rule = "E4_U+FDFA_delete"
            elif cp == 0xFDFB:
                rule = "E4_U+FDFB_delete"
            else:
                rule = f"delete_U+{cp:04X}"
            deleted_source_indices.update(work.sources)
            if is_standalone_separator(work.char):
                for pos in work.sources:
                    separator_deletions[pos] = rule
            decisions[rule] += 1
            events.append(_event(
                segment, work.char, work.sources, "", rule, "phase3", "DELETE",
                detail=unicodedata.name(work.char, "UNNAMED"),
            ))
        else:
            phase3.append(work)

    # Phase 4: only repair an adjacency whose source gap contains a proven
    # standalone separator deletion and whose surviving sides are Arabic words.
    repaired = list(phase3)
    source_to_output: dict[int, int] = {}
    for output_index, work in enumerate(repaired):
        for source in work.sources:
            source_to_output[source] = output_index
    repair_pairs: set[tuple[int, int]] = set()
    surviving_sources = sorted(source_to_output)
    for deleted_index in sorted(separator_deletions):
        insertion = bisect_left(surviving_sources, deleted_index)
        if insertion == 0 or insertion == len(surviving_sources):
            continue
        previous_output = source_to_output[surviving_sources[insertion - 1]]
        next_output = source_to_output[surviving_sources[insertion]]
        if next_output != previous_output + 1:
            continue
        pair = (previous_output, next_output)
        if pair in repair_pairs:
            continue
        if not _word_side_is_arabic(repaired, previous_output, -1):
            continue
        if not _word_side_is_arabic(repaired, next_output, 1):
            continue
        repair_pairs.add(pair)

    for previous_output, next_output in sorted(repair_pairs, reverse=True):
        gap_sources = tuple(
            index for index in sorted(separator_deletions)
            if max(repaired[previous_output].sources) < index < min(repaired[next_output].sources)
        )
        if not gap_sources:
            continue
        inserted = WorkToken(
            " ", gap_sources, gap_sources[0], True,
            tuple(original[index].char for index in range(len(original)) if original[index].source_index in gap_sources),
            "C8_word_boundary_repair",
        )
        repaired.insert(next_output, inserted)
        repairs += 1
        decisions["C8_word_boundary_repair"] += 1
        source_text = "".join(
            next(token.char for token in original if token.source_index == pos) for pos in gap_sources
        )
        events.append(_event(
            segment, source_text, gap_sources, " ", "C8_word_boundary_repair",
            "phase4", "INSERT_BOUNDARY",
        ))

    output_text = "".join(work.char for work in repaired)

    represented_sources = {source for work in repaired for source in work.sources}
    event_deleted_sources = set(deleted_source_indices)
    all_sources = {token.source_index for token in original}
    lineage_complete = all_sources <= represented_sources | event_deleted_sources

    unapproved_duplicate = 0
    for left, right in zip(repaired, repaired[1:]):
        if left.char == right.char == "ا" and (left.introduced or right.introduced):
            unapproved_duplicate += 1

    if strict and not lineage_complete:
        raise StrictTransformError("output lineage is incomplete")
    if strict and unapproved_duplicate:
        raise StrictTransformError("unapproved newly introduced duplicate Alef")

    return SegmentResult(
        text=output_text,
        output_tokens=repaired,
        events=events,
        blockers=blockers,
        decisions=decisions,
        input_count=len(original),
        output_count=len(repaired),
        lineage_complete=lineage_complete,
        word_boundary_repairs=repairs,
        unapproved_duplicate_alef=unapproved_duplicate,
    )


def apply_result_to_segment(segment: TextSegment, result: SegmentResult, target_font: str) -> None:
    by_anchor: defaultdict[int, list[str]] = defaultdict(list)
    for output in result.output_tokens:
        by_anchor[output.anchor].append(output.char)
    node_text: defaultdict[int, list[str]] = defaultdict(list)
    node_by_id = {id(ref.node): ref for ref in segment.nodes}
    for token in segment.tokens:
        node_text[id(token.node_ref.node)].extend(by_anchor.get(token.source_index, []))
    for node_id, ref in node_by_id.items():
        set_text_with_space_semantics(ref.node, "".join(node_text[node_id]))
    for ref in segment.nodes:
        run_has_text = any((node.text or "") for node in ref.run.iter(f"{W}t"))
        if run_has_text:
            set_exact_run_font(ref.run, target_font)


def transform_docx_to_bytes(
    input_path: Path,
    *,
    target_font: str = TARGET_FONT,
    source_symbol_font: str = SOURCE_SYMBOL_FONT,
    strict: bool = True,
) -> DocumentTransformResult:
    inspection = inspect_package(input_path)
    modified_parts: dict[str, bytes] = {}
    all_events: list[dict] = []
    all_blockers: list[dict] = []
    decision_counts: Counter = Counter()
    segment_reports: list[dict] = []
    target_run_locations: list[dict] = []
    run_inventory: list[dict] = []
    with ZipFile(input_path) as package:
        resolver = load_font_resolver(package)
        for part in inspection.story_parts:
            root = parse_xml(package.read(part), part)
            segments, part_runs = extract_segments(
                part, root, resolver,
                target_font=target_font,
                source_symbol_font=source_symbol_font,
            )
            run_inventory.extend(part_runs)
            modified = False
            for segment in segments:
                result = transform_segment(segment, strict=strict)
                from .reference import reference_transform
                stop_classes: dict[int, str] = {}
                segment_text = segment.text
                for sequence in sorted(RAW_DELETE_SEQUENCES, key=len, reverse=True):
                    pattern = "".join(chr(cp) for cp in sequence)
                    search_from = 0
                    while True:
                        at = segment_text.find(pattern, search_from)
                        if at < 0:
                            break
                        stop_classes[at] = classify_stop_candidate(segment.tokens, at, len(sequence))
                        search_from = at + 1
                reference_text = reference_transform(
                    segment_text,
                    surah_start=segment.surah_start,
                    strict=strict,
                    stop_classes=stop_classes,
                )
                oracle_match = result.text == reference_text
                if strict and not oracle_match:
                    raise StrictTransformError(
                        f"independent oracle mismatch in {part} paragraph {segment.paragraph_index}"
                    )
                apply_result_to_segment(segment, result, target_font)
                modified = True
                all_events.extend(event.as_dict() for event in result.events)
                all_blockers.extend(result.blockers)
                decision_counts.update(result.decisions)
                target_run_locations.extend(
                    {
                        "part": ref.metadata.part,
                        "paragraph": ref.metadata.paragraph_index,
                        "run": ref.metadata.run_index,
                    }
                    for ref in segment.nodes
                )
                segment_reports.append({
                    "part": part,
                    "paragraph": segment.paragraph_index,
                    "segment": segment.segment_index,
                    "surah_start": segment.surah_start,
                    "input_count": result.input_count,
                    "output_count": result.output_count,
                    "lineage_complete": result.lineage_complete,
                    "word_boundary_repairs": result.word_boundary_repairs,
                    "unapproved_duplicate_alef": result.unapproved_duplicate_alef,
                    "independent_oracle_match": oracle_match,
                    "input_escaped": segment.text.encode("unicode_escape").decode("ascii"),
                    "output_escaped": result.text.encode("unicode_escape").decode("ascii"),
                })
            if modified:
                modified_parts[part] = serialize_xml(root)
    package_bytes = build_package_bytes(input_path, modified_parts)
    report = {
        "input": inspection.__dict__,
        "modified_parts": sorted(modified_parts),
        "events": all_events,
        "decision_counts": dict(sorted(decision_counts.items())),
        "blockers": all_blockers,
        "segments": segment_reports,
        "target_run_locations": [dict(item) for item in {tuple(sorted(x.items())) for x in target_run_locations}],
        "run_inventory": run_inventory,
        "input_target_character_count": sum(item["input_count"] for item in segment_reports),
        "output_target_character_count": sum(item["output_count"] for item in segment_reports),
        "word_boundary_repairs": sum(item["word_boundary_repairs"] for item in segment_reports),
        "unresolved_count": len(all_blockers),
        "lineage_complete": all(item["lineage_complete"] for item in segment_reports),
        "unapproved_duplicate_alef": sum(item["unapproved_duplicate_alef"] for item in segment_reports),
    }
    return DocumentTransformResult(modified_parts, report, package_bytes)
