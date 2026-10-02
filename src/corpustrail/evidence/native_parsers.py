"""Deterministic native JATS, publisher-XML, and BioC text extraction."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .parsing import ParserOutput, ParsingError
from corpustrail._internal.xml_safety import parse_xml, read_xml, XmlPolicyError


_SPACE = re.compile(r"\s+")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].casefold()


def _text(node) -> str:
    return _SPACE.sub(" ", "".join(node.itertext())).strip()


class _Renderer:
    def __init__(self):
        self.blocks: list[str] = []
        self.sections: list[dict] = []
        self._cursor = 0

    @property
    def cursor(self) -> int:
        return self._cursor

    def add(self, text: str) -> tuple[int, int] | None:
        value = _SPACE.sub(" ", text).strip()
        if not value:
            return None
        start = self.cursor + (2 if self.blocks else 0)
        self.blocks.append(value)
        self._cursor = start + len(value)
        return start, start + len(value)

    def section(self, path: list[str], blocks: list[str], **metadata) -> None:
        start = self.cursor + (2 if self.blocks and blocks else 0)
        added = False
        for block in blocks:
            added = self.add(block) is not None or added
        if added:
            self.sections.append({
                "path": path, "start_offset": start, "end_offset": self.cursor,
                **metadata,
            })

    def finish(self, *, source_format: str) -> ParserOutput:
        body = "\n\n".join(self.blocks)
        if not body.strip():
            raise ParsingError(f"{source_format} parser produced no readable text")
        return ParserOutput(
            body=body, representation_kind="structured_text", structured=True,
            quality={
                "characters": len(body), "blocks": len(self.blocks),
                "sections": self.sections, "source_format": source_format,
            },
        )


def _first_descendant(root, names: set[str]):
    return next((node for node in root.iter() if _local(node.tag) in names), None)


def _direct_children(node, names: set[str]):
    return [child for child in node if _local(child.tag) in names]


def _walk_xml_section(renderer: _Renderer, node, parent_path: list[str]) -> None:
    title_node = next((child for child in node if _local(child.tag) == "title"), None)
    title = _text(title_node) if title_node is not None else "Untitled section"
    path = parent_path + [title]
    blocks = [title]
    nested = []
    for child in node:
        kind = _local(child.tag)
        if kind == "sec":
            nested.append(child)
        elif kind == "p":
            blocks.append(_text(child))
        elif kind == "list":
            blocks.extend(
                "• " + _text(item) for item in child.iter() if _local(item.tag) == "list-item"
            )
        elif kind in {"fig", "table-wrap", "boxed-text"}:
            caption = _first_descendant(child, {"caption"})
            if caption is not None:
                blocks.append(_text(caption))
            if kind == "table-wrap":
                for row in child.iter():
                    if _local(row.tag) == "tr":
                        cells = [_text(cell) for cell in row if _local(cell.tag) in {"td", "th"}]
                        if any(cells):
                            blocks.append(" | ".join(cells))
    renderer.section(path, blocks)
    for child in nested:
        _walk_xml_section(renderer, child, path)


class NativeJatsParser:
    name = "native_jats"
    version = "corpustrail-native-jats/v2"

    def parse(self, document_path: Path) -> ParserOutput:
        try:
            root = parse_xml(read_xml(document_path))
        except XmlPolicyError as exc:
            raise ParsingError(f"invalid JATS XML: {exc}") from exc
        if _local(root.tag) != "article":
            raise ParsingError("JATS root element must be article")
        return _render_article_xml(root, source_format="jats")


class NativePublisherXmlParser:
    name = "native_publisher_xml"
    version = "corpustrail-native-publisher-xml/v2"

    def parse(self, document_path: Path) -> ParserOutput:
        try:
            root = parse_xml(read_xml(document_path))
        except XmlPolicyError as exc:
            raise ParsingError(f"invalid publisher XML: {exc}") from exc
        return _render_article_xml(root, source_format="publisher_xml")


def _render_article_xml(root, *, source_format: str) -> ParserOutput:
    renderer = _Renderer()
    title = _first_descendant(root, {"article-title"})
    if title is not None:
        renderer.section(["Title"], [_text(title)])
    abstract = _first_descendant(root, {"abstract"})
    if abstract is not None:
        abstract_blocks = [
            _text(node) for node in abstract.iter() if _local(node.tag) == "p"
        ] or [_text(abstract)]
        renderer.section(["Abstract"], abstract_blocks)
    body = _first_descendant(root, {"body"})
    if body is not None:
        direct_sections = _direct_children(body, {"sec"})
        direct_paragraphs = _direct_children(body, {"p"})
        if direct_paragraphs:
            renderer.section(["Body"], [_text(node) for node in direct_paragraphs])
        for section in direct_sections:
            _walk_xml_section(renderer, section, [])
    return renderer.finish(source_format=source_format)


class NativeBiocParser:
    name = "native_bioc"
    version = "corpustrail-native-bioc/v1"

    def parse(self, document_path: Path) -> ParserOutput:
        try:
            value = json.loads(document_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ParsingError(f"invalid BioC JSON: {exc}") from exc
        containers = value if isinstance(value, list) else [value]
        documents = []
        for container in containers:
            if not isinstance(container, dict):
                continue
            nested = container.get("documents")
            documents.extend(nested if isinstance(nested, list) else [container])
        renderer = _Renderer()
        for document in documents:
            if not isinstance(document, dict):
                continue
            for passage in document.get("passages") or []:
                if not isinstance(passage, dict):
                    continue
                text = passage.get("text")
                if not isinstance(text, str) or not text.strip():
                    continue
                infons = passage.get("infons") if isinstance(passage.get("infons"), dict) else {}
                label = str(
                    infons.get("section") or infons.get("section_type")
                    or infons.get("type") or "Passage"
                ).strip()
                source_offset = passage.get("offset")
                renderer.section(
                    [label], [text],
                    source_offset=(source_offset if isinstance(source_offset, int) else None),
                )
        return renderer.finish(source_format="bioc_json")


def render_grobid_tei(raw: bytes) -> ParserOutput:
    """Render GROBID TEI bytes while retaining canonical section offsets."""

    try:
        root = parse_xml(raw)
    except XmlPolicyError as exc:
        raise ParsingError(f"invalid GROBID TEI: {exc}") from exc
    if _local(root.tag) != "tei":
        raise ParsingError("GROBID response root must be TEI")
    renderer = _Renderer()
    header = _first_descendant(root, {"teiheader"})
    if header is not None:
        title = _first_descendant(header, {"title"})
        if title is not None:
            renderer.section(["Title"], [_text(title)])
        abstract = _first_descendant(header, {"abstract"})
        if abstract is not None:
            blocks = [_text(node) for node in abstract.iter() if _local(node.tag) == "p"]
            renderer.section(["Abstract"], blocks or [_text(abstract)])
    body = _first_descendant(root, {"body"})
    if body is not None:
        for division in (node for node in body if _local(node.tag) == "div"):
            heading = next(
                (_text(node) for node in division if _local(node.tag) == "head"),
                "Untitled section",
            )
            blocks = [heading]
            for node in division:
                kind = _local(node.tag)
                if kind == "p":
                    blocks.append(_text(node))
                elif kind == "list":
                    blocks.extend(
                        "• " + _text(item) for item in node.iter()
                        if _local(item.tag) == "item"
                    )
                elif kind in {"figure", "table"}:
                    blocks.append(_text(node))
            renderer.section([heading], blocks)
    return renderer.finish(source_format="grobid_tei")
