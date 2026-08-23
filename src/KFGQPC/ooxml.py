"""Safe OOXML package access, run/font resolution, and loss-limited writing."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from hashlib import sha256
from io import BytesIO
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from typing import Iterable, Iterator
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo

from lxml import etree

from . import SOURCE_SYMBOL_FONT, TARGET_FONT


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
W = f"{{{W_NS}}}"
XML_SPACE = f"{{{XML_NS}}}space"
NS = {"w": W_NS}

MAX_ENTRIES = 10_000
MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1_000


class PackageError(RuntimeError):
    pass


@dataclass(frozen=True)
class PackageInspection:
    path: str
    sha256: str
    entry_count: int
    total_compressed_bytes: int
    total_uncompressed_bytes: int
    story_parts: tuple[str, ...]
    required_parts_present: bool
    crc_ok: bool


@dataclass(frozen=True)
class RunMetadata:
    part: str
    paragraph_index: int
    run_index: int
    direct_fonts: tuple[tuple[str, str], ...]
    resolved_fonts: tuple[tuple[str, str], ...]
    run_style: str | None
    paragraph_style: str | None
    vert_align: str | None
    position: str | None
    rtl: bool
    paragraph_bidi: bool
    target: bool

    def as_dict(self) -> dict:
        return {
            "part": self.part,
            "paragraph": self.paragraph_index,
            "run": self.run_index,
            "direct_fonts": dict(self.direct_fonts),
            "resolved_fonts": dict(self.resolved_fonts),
            "run_style": self.run_style,
            "paragraph_style": self.paragraph_style,
            "vert_align": self.vert_align,
            "position": self.position,
            "rtl": self.rtl,
            "paragraph_bidi": self.paragraph_bidi,
            "target": self.target,
        }


@dataclass
class TextNodeRef:
    node: etree._Element
    run: etree._Element
    metadata: RunMetadata
    node_index: int
    original_text: str
    source_indices: list[int] = field(default_factory=list)


@dataclass
class SourceToken:
    char: str
    source_index: int
    node_ref: TextNodeRef
    char_in_node: int

    @property
    def metadata(self) -> RunMetadata:
        return self.node_ref.metadata


@dataclass
class TextSegment:
    part: str
    paragraph_index: int
    segment_index: int
    tokens: list[SourceToken]
    nodes: list[TextNodeRef]
    surah_start: bool = False
    _cached_text: str | None = field(default=None, init=False, repr=False)

    @property
    def text(self) -> str:
        if self._cached_text is None:
            self._cached_text = "".join(token.char for token in self.tokens)
        return self._cached_text


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_member_name(name: str) -> bool:
    if not name or "\x00" in name or "\\" in name:
        return False
    p = PurePosixPath(name)
    return not p.is_absolute() and ".." not in p.parts


def _xml_parser() -> etree.XMLParser:
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        recover=False,
        huge_tree=False,
        remove_blank_text=False,
    )


def parse_xml(data: bytes, part: str) -> etree._Element:
    try:
        return etree.fromstring(data, parser=_xml_parser())
    except etree.XMLSyntaxError as exc:
        raise PackageError(f"malformed XML part {part}: {exc}") from exc


def is_story_root(root: etree._Element) -> bool:
    local = etree.QName(root).localname
    return local in {
        "document", "hdr", "ftr", "footnotes", "endnotes", "comments",
        "glossaryDocument",
    } or root.find(".//w:txbxContent", namespaces=NS) is not None


def inspect_package(path: Path) -> PackageInspection:
    path = path.resolve()
    if path.suffix.lower() != ".docx":
        raise PackageError(f"not a .docx path: {path}")
    try:
        mode = path.stat().st_mode
    except OSError as exc:
        raise PackageError(f"cannot stat input: {path}: {exc}") from exc
    if not stat.S_ISREG(mode):
        raise PackageError(f"input is not a regular file: {path}")
    try:
        with ZipFile(path) as package:
            infos = package.infolist()
            if len(infos) > MAX_ENTRIES:
                raise PackageError(f"too many ZIP entries: {len(infos)}")
            total_uncompressed = 0
            total_compressed = 0
            for info in infos:
                if not _safe_member_name(info.filename):
                    raise PackageError(f"unsafe ZIP member path: {info.filename!r}")
                if info.flag_bits & 0x1:
                    raise PackageError(f"encrypted ZIP member: {info.filename}")
                if info.file_size > MAX_MEMBER_BYTES:
                    raise PackageError(f"oversized ZIP member: {info.filename}")
                ratio = info.file_size / max(info.compress_size, 1)
                if ratio > MAX_COMPRESSION_RATIO:
                    raise PackageError(f"suspicious compression ratio: {info.filename}")
                total_uncompressed += info.file_size
                total_compressed += info.compress_size
            if total_uncompressed > MAX_TOTAL_BYTES:
                raise PackageError("suspicious total uncompressed package size")
            required = {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
            names = {info.filename for info in infos}
            if not required.issubset(names):
                missing = sorted(required - names)
                raise PackageError(f"missing required OOXML parts: {missing}")
            bad = package.testzip()
            if bad is not None:
                raise PackageError(f"ZIP CRC failure: {bad}")
            stories: list[str] = []
            for info in infos:
                name = info.filename
                if not name.startswith("word/") or not name.endswith(".xml"):
                    continue
                if info.file_size > MAX_MEMBER_BYTES:
                    continue
                root = parse_xml(package.read(name), name)
                if is_story_root(root):
                    stories.append(name)
    except BadZipFile as exc:
        raise PackageError(f"malformed DOCX ZIP package: {path}") from exc
    return PackageInspection(
        path=str(path),
        sha256=file_sha256(path),
        entry_count=len(infos),
        total_compressed_bytes=total_compressed,
        total_uncompressed_bytes=total_uncompressed,
        story_parts=tuple(stories),
        required_parts_present=True,
        crc_ok=True,
    )


def _rfonts_dict(rpr: etree._Element | None) -> dict[str, str]:
    if rpr is None:
        return {}
    rfonts = rpr.find(f"{W}rFonts")
    if rfonts is None:
        return {}
    result: dict[str, str] = {}
    for key, value in rfonts.attrib.items():
        result[etree.QName(key).localname] = value
    return result


def _val(element: etree._Element | None) -> str | None:
    return None if element is None else element.get(f"{W}val")


class FontResolver:
    """Resolve document defaults, paragraph/run styles, and direct rFonts."""

    def __init__(self, styles_root: etree._Element | None):
        self.defaults: dict[str, str] = {}
        self.styles: dict[str, dict] = {}
        if styles_root is None:
            return
        default_rpr = styles_root.find("./w:docDefaults/w:rPrDefault/w:rPr", NS)
        self.defaults = _rfonts_dict(default_rpr)
        for style in styles_root.findall("./w:style", NS):
            style_id = style.get(f"{W}styleId")
            if not style_id:
                continue
            based = style.find("./w:basedOn", NS)
            self.styles[style_id] = {
                "type": style.get(f"{W}type"),
                "based_on": _val(based),
                "fonts": _rfonts_dict(style.find("./w:rPr", NS)),
            }

    def _style_fonts(self, style_id: str | None) -> dict[str, str]:
        if not style_id:
            return {}
        chain: list[dict[str, str]] = []
        seen: set[str] = set()
        current = style_id
        while current and current not in seen and current in self.styles:
            seen.add(current)
            info = self.styles[current]
            chain.append(info["fonts"])
            current = info["based_on"]
        result: dict[str, str] = {}
        for fonts in reversed(chain):
            result.update(fonts)
        return result

    def resolve(
        self,
        paragraph: etree._Element,
        run: etree._Element,
        *,
        paragraph_style: str | None = None,
        paragraph_style_known: bool = False,
    ) -> tuple[dict[str, str], str | None, str | None]:
        p_style = paragraph_style if paragraph_style_known else _val(paragraph.find("./w:pPr/w:pStyle", NS))
        r_style = _val(run.find("./w:rPr/w:rStyle", NS))
        result = dict(self.defaults)
        result.update(self._style_fonts(p_style))
        result.update(self._style_fonts(r_style))
        result.update(_rfonts_dict(run.find(f"{W}rPr")))
        return result, p_style, r_style


def load_font_resolver(package: ZipFile) -> FontResolver:
    if "word/styles.xml" not in package.namelist():
        return FontResolver(None)
    return FontResolver(parse_xml(package.read("word/styles.xml"), "word/styles.xml"))


def nearest_paragraph(element: etree._Element) -> etree._Element | None:
    for ancestor in element.iterancestors(tag=f"{W}p"):
        return ancestor
    return None


def iter_paragraph_runs(paragraph: etree._Element) -> Iterator[etree._Element]:
    for run in paragraph.iter(f"{W}r"):
        if nearest_paragraph(run) is paragraph:
            yield run


def run_text_nodes(run: etree._Element) -> list[etree._Element]:
    result: list[etree._Element] = []
    for node in run.iter(f"{W}t"):
        nearest_run = next(node.iterancestors(f"{W}r"), None)
        if nearest_run is run:
            result.append(node)
    return result


def is_structural_break_run(run: etree._Element) -> bool:
    break_tags = {f"{W}br", f"{W}cr", f"{W}tab", f"{W}fldChar", f"{W}instrText"}
    return any(element.tag in break_tags for element in run.iter())


def build_run_metadata(
    part: str,
    paragraph_index: int,
    run_index: int,
    paragraph: etree._Element,
    run: etree._Element,
    resolver: FontResolver,
    target_font: str = TARGET_FONT,
    source_symbol_font: str = SOURCE_SYMBOL_FONT,
    paragraph_style: str | None = None,
    paragraph_bidi: bool | None = None,
) -> RunMetadata:
    direct = _rfonts_dict(run.find(f"{W}rPr"))
    resolved, p_style, r_style = resolver.resolve(
        paragraph, run, paragraph_style=paragraph_style, paragraph_style_known=True,
    )
    rpr = run.find(f"{W}rPr")
    vert_align = _val(None if rpr is None else rpr.find(f"{W}vertAlign"))
    position = _val(None if rpr is None else rpr.find(f"{W}position"))
    rtl = rpr is not None and rpr.find(f"{W}rtl") is not None
    if paragraph_bidi is None:
        ppr = paragraph.find(f"{W}pPr")
        paragraph_bidi = ppr is not None and ppr.find(f"{W}bidi") is not None
    font_values = set(direct.values()) | set(resolved.values())
    target = target_font in font_values or source_symbol_font in font_values
    return RunMetadata(
        part=part,
        paragraph_index=paragraph_index,
        run_index=run_index,
        direct_fonts=tuple(sorted(direct.items())),
        resolved_fonts=tuple(sorted(resolved.items())),
        run_style=r_style,
        paragraph_style=p_style,
        vert_align=vert_align,
        position=position,
        rtl=rtl,
        paragraph_bidi=paragraph_bidi,
        target=target,
    )


def extract_segments(
    part: str,
    root: etree._Element,
    resolver: FontResolver,
    *,
    target_font: str = TARGET_FONT,
    source_symbol_font: str = SOURCE_SYMBOL_FONT,
) -> tuple[list[TextSegment], list[dict]]:
    segments: list[TextSegment] = []
    run_inventory: list[dict] = []
    source_index = 0
    first_arabic_segment = True
    for paragraph_index, paragraph in enumerate(root.iter(f"{W}p")):
        ppr = paragraph.find(f"{W}pPr")
        paragraph_style = _val(None if ppr is None else ppr.find(f"{W}pStyle"))
        paragraph_bidi = ppr is not None and ppr.find(f"{W}bidi") is not None
        current_tokens: list[SourceToken] = []
        current_nodes: list[TextNodeRef] = []
        segment_index = 0

        def flush() -> None:
            nonlocal current_tokens, current_nodes, segment_index, first_arabic_segment
            if not current_tokens:
                current_nodes = []
                return
            has_arabic = any("ARABIC" in __import__("unicodedata").name(t.char, "") for t in current_tokens)
            segment = TextSegment(
                part=part,
                paragraph_index=paragraph_index,
                segment_index=segment_index,
                tokens=current_tokens,
                nodes=current_nodes,
                surah_start=bool(first_arabic_segment and has_arabic and part == "word/document.xml"),
            )
            segments.append(segment)
            if has_arabic and part == "word/document.xml":
                first_arabic_segment = False
            segment_index += 1
            current_tokens = []
            current_nodes = []

        for run_index, run in enumerate(iter_paragraph_runs(paragraph)):
            metadata = build_run_metadata(
                part, paragraph_index, run_index, paragraph, run, resolver,
                target_font, source_symbol_font, paragraph_style, paragraph_bidi,
            )
            nodes = run_text_nodes(run)
            text = "".join(node.text or "" for node in nodes)
            run_record = metadata.as_dict()
            run_record["text_length"] = len(text)
            run_record["escaped_text"] = text.encode("unicode_escape").decode("ascii")[:240]
            run_inventory.append(run_record)
            if is_structural_break_run(run):
                flush()
            if not nodes or not text:
                continue
            if not metadata.target:
                flush()
                continue
            for node_index, node in enumerate(nodes):
                original = node.text or ""
                ref = TextNodeRef(node, run, metadata, node_index, original)
                current_nodes.append(ref)
                for char_in_node, char in enumerate(original):
                    token = SourceToken(char, source_index, ref, char_in_node)
                    ref.source_indices.append(source_index)
                    current_tokens.append(token)
                    source_index += 1
        flush()
    return segments, run_inventory


def set_text_with_space_semantics(node: etree._Element, text: str) -> None:
    node.text = text
    if text and (text[0].isspace() or text[-1].isspace()):
        node.set(XML_SPACE, "preserve")
    else:
        node.attrib.pop(XML_SPACE, None)


def set_exact_run_font(run: etree._Element, target_font: str = TARGET_FONT) -> None:
    rpr = run.find(f"{W}rPr")
    if rpr is None:
        rpr = etree.Element(f"{W}rPr")
        run.insert(0, rpr)
    rfonts = rpr.find(f"{W}rFonts")
    if rfonts is None:
        rfonts = etree.Element(f"{W}rFonts")
        rpr.insert(0, rfonts)
    for key in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
        rfonts.attrib.pop(f"{W}{key}", None)
    for key in ("ascii", "hAnsi", "eastAsia", "cs"):
        rfonts.set(f"{W}{key}", target_font)


def serialize_xml(root: etree._Element) -> bytes:
    return etree.tostring(
        root,
        encoding="UTF-8",
        xml_declaration=True,
        standalone=True,
    )


def build_package_bytes(input_path: Path, modified_parts: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with ZipFile(input_path) as source, ZipFile(output, "w") as target:
        for info in source.infolist():
            data = modified_parts.get(info.filename, source.read(info.filename))
            # Passing the original ZipInfo preserves member order, timestamps,
            # attributes, comments, and compression method for deterministic bytes.
            target.writestr(info, data)
    return output.getvalue()


def publish_new_file(path: Path, data: bytes) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {path}")
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        finally:
            raise


def package_member_hashes(path: Path) -> dict[str, str]:
    with ZipFile(path) as package:
        return {name: sha256(package.read(name)).hexdigest() for name in package.namelist()}


def font_signature_counter(run_inventory: Iterable[dict]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for run in run_inventory:
        direct = ",".join(f"{k}={v}" for k, v in sorted(run["direct_fonts"].items())) or "(none)"
        resolved = ",".join(f"{k}={v}" for k, v in sorted(run["resolved_fonts"].items())) or "(none)"
        counter[f"direct[{direct}] resolved[{resolved}] target={run['target']}"] += 1
    return dict(sorted(counter.items()))
