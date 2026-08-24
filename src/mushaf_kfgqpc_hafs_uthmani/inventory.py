"""Strict preflight inventory for DOCX packages and Unicode rule contexts."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZipFile
import unicodedata

from lxml import etree

from . import SOURCE_SYMBOL_FONT, TARGET_FONT
from .ooxml import (
    extract_segments,
    font_signature_counter,
    inspect_package,
    load_font_resolver,
    parse_xml,
    run_text_nodes,
)
from .rules import (
    CONTEXTUAL_CODEPOINTS,
    EFFECTIVE_DELETE_CODEPOINTS,
    EFFECTIVE_OVERRIDES,
    KEEP_CODEPOINTS,
    LONG_VOWELS,
    RAW_DELETE_SEQUENCES,
    RAW_TRANSFORMS,
    is_arabic_or_quranic,
    is_effective_delete,
    is_numeric_char,
    known_effective_source,
    raw_counts,
)
from .transformer import (
    classify_stop_candidate,
    escaped_context,
    muqattaat_maddah_indices,
)


SPECIAL_CODEPOINTS = frozenset(
    {0x0653, 0x0657, 0x065E, 0x0670, 0x06E4, 0xFDFD, 0xFDFA, 0xFDFB, 0x06CC}
)


def codepoint_record(char: str) -> dict:
    cp = ord(char)
    return {
        "codepoint": f"U+{cp:04X}",
        "literal": char,
        "escaped": char.encode("unicode_escape").decode("ascii"),
        "name": unicodedata.name(char, "UNNAMED"),
        "category": unicodedata.category(char),
    }


def _surah_identity(target_text: str) -> dict:
    # This fingerprint is inspection-only.  It does not mutate output text.
    skeleton = "".join(
        char for char in target_text
        if not unicodedata.category(char).startswith("M")
        and not is_numeric_char(char)
        and char != "\u00a0"
    )
    skeleton = " ".join(skeleton.split())
    signatures = (
        ("Al-Fatihah", ("بسم ٱلله ٱلرحمن ٱلرحيم", "بسم الله الرحمن الرحيم")),
        ("Al-Baqarah", ("الم ذلك ٱلكتب", "الم ذلك الكتب")),
        ("Fussilat", ("حم تنزيل من ٱلرحمن ٱلرحيم", "حم تنزيل من الرحمن الرحيم")),
    )
    for name, prefixes in signatures:
        for prefix in prefixes:
            if skeleton.startswith(prefix):
                return {
                    "surah": name,
                    "method": "initial base-letter skeleton fingerprint",
                    "evidence_escaped": skeleton[:80].encode("unicode_escape").decode("ascii"),
                }
    return {
        "surah": "unidentified",
        "method": "initial base-letter skeleton fingerprint",
        "evidence_escaped": skeleton[:80].encode("unicode_escape").decode("ascii"),
    }


def _context_decision(segment, index: int, muqattaat: set[int]) -> tuple[str, list[int]]:
    tokens = segment.tokens
    cp = ord(tokens[index].char)
    dependencies = [index]
    if cp == 0x0653:
        prior_base = None
        prior_index = None
        for cursor in range(index - 1, -1, -1):
            if tokens[cursor].char.isspace():
                break
            if not unicodedata.category(tokens[cursor].char).startswith("M"):
                prior_base = ord(tokens[cursor].char)
                prior_index = cursor
                break
        if index in muqattaat:
            decision = "C3_Muqattaat_strip_Maddah"
        elif prior_base in LONG_VOWELS:
            decision = "C2_long_vowel_strip_Maddah"
        elif index + 1 < len(tokens) and ord(tokens[index + 1].char) == 0x0627:
            decision = "C5_existing_Alef_strip_Maddah"
        else:
            decision = "C5_nominal_Maddah_to_Alef"
        if prior_index is not None:
            dependencies.append(prior_index)
        if index + 1 < len(tokens) and ord(tokens[index + 1].char) == 0x0627:
            dependencies.append(index + 1)
        return decision, dependencies
    if cp == 0x0657:
        if index + 1 < len(tokens) and ord(tokens[index + 1].char) == 0x0627:
            return "C1_Inverted_Damma_plus_Alef", [index, index + 1]
        return "C1_Inverted_Damma_nominal_Alef", [index]
    if cp == 0x06E4:
        if index + 1 < len(tokens) and ord(tokens[index + 1].char) == 0x0627:
            return "C6_small_high_Maddah_to_Alef_followed_Alef_collision", [index, index + 1]
        return "C6_small_high_Maddah_to_Alef", [index]
    if cp == 0x065E:
        return "E1_Dammatan_anomaly", [index]
    if cp == 0x06CC:
        return "E2_Farsi_Yeh", [index]
    return "declarative_rule", [index]


def audit_docx(
    path: Path,
    *,
    target_font: str = TARGET_FONT,
    source_symbol_font: str = SOURCE_SYMBOL_FONT,
    strict: bool = True,
) -> dict:
    inspection = inspect_package(path)
    overall_histogram: Counter[str] = Counter()
    target_histogram: Counter[str] = Counter()
    non_target_histogram: Counter[str] = Counter()
    contexts: defaultdict[str, list[dict]] = defaultdict(list)
    font_sets: defaultdict[str, set[str]] = defaultdict(set)
    styles: defaultdict[str, set[str]] = defaultdict(set)
    parts_by_cp: defaultdict[str, set[str]] = defaultdict(set)
    target_counts_by_cp: Counter[str] = Counter()
    non_target_counts_by_cp: Counter[str] = Counter()
    trigger_occurrences: list[dict] = []
    special_occurrences: list[dict] = []
    stop_occurrences: list[dict] = []
    unknown_occurrences: list[dict] = []
    unresolved: list[dict] = []
    contextual_decisions: Counter[str] = Counter()
    run_boundary_matches: Counter[str] = Counter()
    run_inventory: list[dict] = []
    paragraph_count = 0
    target_texts: list[str] = []
    story_inventory: list[dict] = []

    with ZipFile(path) as package:
        resolver = load_font_resolver(package)
        for part in inspection.story_parts:
            root = parse_xml(package.read(part), part)
            paragraphs = list(root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"))
            paragraph_count += len(paragraphs)
            segments, part_runs = extract_segments(
                part, root, resolver,
                target_font=target_font,
                source_symbol_font=source_symbol_font,
            )
            run_inventory.extend(part_runs)
            story_inventory.append({
                "part": part,
                "paragraph_count": len(paragraphs),
                "target_segment_count": len(segments),
                "target_character_count": sum(len(segment.tokens) for segment in segments),
            })
            records_by_location = {
                (run["paragraph"], run["run"]): run for run in part_runs
            }
            for paragraph_index, paragraph in enumerate(paragraphs):
                for run_index, run in enumerate(
                    r for r in paragraph.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}r")
                    if next(r.iterancestors("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"), None) is paragraph
                ):
                    text = "".join(node.text or "" for node in run_text_nodes(run))
                    metadata_record = records_by_location.get((paragraph_index, run_index))
                    target = bool(metadata_record and metadata_record["target"])
                    for char_index, char in enumerate(text):
                        cp_key = f"U+{ord(char):04X}"
                        overall_histogram[char] += 1
                        parts_by_cp[cp_key].add(part)
                        if target:
                            target_histogram[char] += 1
                            target_counts_by_cp[cp_key] += 1
                        else:
                            non_target_histogram[char] += 1
                            non_target_counts_by_cp[cp_key] += 1
                        if metadata_record:
                            signature = ",".join(
                                f"{k}={v}" for k, v in sorted(metadata_record["resolved_fonts"].items())
                            ) or "(none)"
                            font_sets[cp_key].add(signature)
                            styles[cp_key].add(metadata_record["run_style"] or "(none)")
                        if len(contexts[cp_key]) < 12:
                            contexts[cp_key].append({
                                "part": part,
                                "paragraph": paragraph_index,
                                "run": run_index,
                                "char_in_run": char_index,
                                "target": target,
                                "run_context_escaped": text[max(0, char_index - 8):char_index + 9].encode("unicode_escape").decode("ascii"),
                            })

            for segment in segments:
                text = segment.text
                target_texts.append(text)
                muqattaat = muqattaat_maddah_indices(segment.tokens, segment.surah_start)
                for index, token in enumerate(segment.tokens):
                    char = token.char
                    cp = ord(char)
                    decision, dependencies = _context_decision(segment, index, muqattaat)
                    dependency_runs = sorted({segment.tokens[pos].metadata.run_index for pos in dependencies})
                    occurrence = {
                        **codepoint_record(char),
                        "part": part,
                        "paragraph": segment.paragraph_index,
                        "segment": segment.segment_index,
                        "source_index": token.source_index,
                        "run": token.metadata.run_index,
                        "runs": dependency_runs,
                        "cross_run": len(dependency_runs) > 1,
                        "context": escaped_context(text, index, index + 1),
                        "fonts": {
                            "direct": dict(token.metadata.direct_fonts),
                            "resolved": dict(token.metadata.resolved_fonts),
                        },
                        "styles": {
                            "run": token.metadata.run_style,
                            "paragraph": token.metadata.paragraph_style,
                        },
                        "vertical": {
                            "vert_align": token.metadata.vert_align,
                            "position": token.metadata.position,
                        },
                        "decision": decision,
                    }
                    triggers = (
                        cp in RAW_TRANSFORMS
                        or cp in EFFECTIVE_OVERRIDES
                        or cp in EFFECTIVE_DELETE_CODEPOINTS
                        or is_numeric_char(char)
                        or cp == 0xFDFD
                    )
                    if triggers:
                        trigger_occurrences.append(occurrence)
                    if cp in SPECIAL_CODEPOINTS:
                        special_occurrences.append(occurrence)
                        contextual_decisions[decision] += 1
                        if occurrence["cross_run"]:
                            run_boundary_matches[decision] += 1
                    if is_arabic_or_quranic(char) and not known_effective_source(char):
                        unknown_occurrences.append(occurrence)

                for sequence in sorted(RAW_DELETE_SEQUENCES, key=len, reverse=True):
                    pattern = "".join(chr(cp) for cp in sequence)
                    start = 0
                    while True:
                        at = text.find(pattern, start)
                        if at < 0:
                            break
                        classification = classify_stop_candidate(segment.tokens, at, len(sequence))
                        token_slice = segment.tokens[at:at + len(sequence)]
                        runs = sorted({item.metadata.run_index for item in token_slice})
                        item = {
                            "sequence": [f"U+{cp:04X}" for cp in sequence],
                            "escaped": pattern.encode("unicode_escape").decode("ascii"),
                            "part": part,
                            "paragraph": segment.paragraph_index,
                            "segment": segment.segment_index,
                            "source_indices": [token.source_index for token in token_slice],
                            "runs": runs,
                            "cross_run": len(runs) > 1,
                            "classification": classification,
                            "context": escaped_context(text, at, at + len(sequence)),
                            "run_metadata": [token.metadata.as_dict() for token in token_slice],
                        }
                        stop_occurrences.append(item)
                        contextual_decisions[f"stop_sequence:{classification}"] += 1
                        if len(runs) > 1:
                            run_boundary_matches[f"stop_sequence:{classification}"] += 1
                        if classification == "unresolved":
                            unresolved.append(item)
                        start = at + 1

                for at, char in enumerate(text):
                    if ord(char) == 0xFDFD:
                        # The production guard performs the same evidence test;
                        # preflight treats every unproven instance as blocking.
                        from .transformer import _bismillah_is_decorative
                        if not _bismillah_is_decorative(text, at):
                            unresolved.append({
                                "type": "sole_or_unproven_bismillah_ligature",
                                "part": part,
                                "paragraph": segment.paragraph_index,
                                "segment": segment.segment_index,
                                "context": escaped_context(text, at, at + 1),
                            })

    codepoint_inventory = []
    for char in sorted(overall_histogram, key=ord):
        cp_key = f"U+{ord(char):04X}"
        codepoint_inventory.append({
            **codepoint_record(char),
            "count": overall_histogram[char],
            "target_count": target_counts_by_cp[cp_key],
            "non_target_count": non_target_counts_by_cp[cp_key],
            "files": [str(path.resolve())],
            "parts": sorted(parts_by_cp[cp_key]),
            "resolved_font_signatures": sorted(font_sets[cp_key]),
            "styles": sorted(styles[cp_key]),
            "short_contexts": contexts[cp_key],
        })

    identity = _surah_identity("".join(target_texts))
    unknown_codepoints = sorted({item["codepoint"] for item in unknown_occurrences})
    unexplained_risk = len(unknown_occurrences) + len(unresolved)
    preflight_ok = unexplained_risk == 0 and identity["surah"] != "unidentified"
    return {
        "schema_version": 1,
        "mode": "preflight_audit_only",
        "input": inspection.__dict__,
        "identity": identity,
        "raw_ledger_counts": raw_counts(),
        "story_inventory": story_inventory,
        "paragraph_count": paragraph_count,
        "target_character_count": sum(target_histogram.values()),
        "non_target_character_count": sum(non_target_histogram.values()),
        "codepoint_inventory": codepoint_inventory,
        "font_style_inventory": font_signature_counter(run_inventory),
        "run_inventory": run_inventory,
        "trigger_occurrences": trigger_occurrences,
        "trigger_counts": dict(sorted(Counter(item["codepoint"] for item in trigger_occurrences).items())),
        "special_occurrences": special_occurrences,
        "special_counts": dict(sorted(Counter(item["codepoint"] for item in special_occurrences).items())),
        "contextual_decision_counts": dict(sorted(contextual_decisions.items())),
        "run_boundary_match_counts": dict(sorted(run_boundary_matches.items())),
        "stop_sequence_occurrences": stop_occurrences,
        "stop_sequence_count": len(stop_occurrences),
        "unknown_occurrences": unknown_occurrences,
        "unknown_codepoints": unknown_codepoints,
        "unknown_count": len(unknown_occurrences),
        "unresolved_ambiguities": unresolved,
        "unresolved_count": len(unresolved),
        "preflight_ok": preflight_ok,
        "strict": strict,
    }


def combine_preflights(reports: list[dict]) -> dict:
    histogram: Counter[str] = Counter()
    trigger_counts: Counter[str] = Counter()
    special_counts: Counter[str] = Counter()
    decisions: Counter[str] = Counter()
    run_boundaries: Counter[str] = Counter()
    files: list[dict] = []
    zero_match_sets: list[set[str]] = []
    for report in reports:
        for item in report["codepoint_inventory"]:
            histogram[item["codepoint"]] += item["count"]
        trigger_counts.update(report["trigger_counts"])
        special_counts.update(report["special_counts"])
        decisions.update(report["contextual_decision_counts"])
        run_boundaries.update(report["run_boundary_match_counts"])
        if "zero_match_effective_rules" in report:
            zero_match_sets.append(set(report["zero_match_effective_rules"]))
        files.append({
            "path": report["input"]["path"],
            "sha256": report["input"]["sha256"],
            "surah": report["identity"]["surah"],
            "target_character_count": report["target_character_count"],
            "non_target_character_count": report["non_target_character_count"],
            "unknown_count": report["unknown_count"],
            "unresolved_count": report["unresolved_count"],
            "preflight_ok": report["preflight_ok"],
        })
    return {
        "schema_version": 1,
        "mode": "combined_preflight_audit_only",
        "files": files,
        "file_count": len(files),
        "raw_ledger_counts": raw_counts(),
        "combined_codepoint_histogram": dict(sorted(histogram.items())),
        "combined_trigger_counts": dict(sorted(trigger_counts.items())),
        "combined_special_counts": dict(sorted(special_counts.items())),
        "combined_contextual_decision_counts": dict(sorted(decisions.items())),
        "combined_run_boundary_match_counts": dict(sorted(run_boundaries.items())),
        "zero_match_effective_rules": sorted(set.intersection(*zero_match_sets)) if zero_match_sets else [],
        "unknown_count": sum(item["unknown_count"] for item in files),
        "unresolved_count": sum(item["unresolved_count"] for item in files),
        "preflight_ok": all(item["preflight_ok"] for item in files),
    }
