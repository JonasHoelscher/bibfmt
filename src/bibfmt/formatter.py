#!/usr/bin/env python3

# Standard libraries
import heapq
import logging
import re
from dataclasses import dataclass
from enum import Enum, auto

# Third party libraries
from tree_sitter import Node, Parser
from tree_sitter_language_pack import get_language

logger = logging.getLogger(__name__)
BIBTEX_LANGUAGE = get_language("bibtex")
PARSER = Parser(BIBTEX_LANGUAGE)


class BlockType(Enum):
    Entry = auto()
    String = auto()
    Preamble = auto()
    Comment = auto()
    Raw = auto()


@dataclass(slots=True)
class Block:
    kind: BlockType
    formatted_text: str
    original_index: int

    key: str | None = None
    crossref: str | None = None
    leading_text: str = ""

    @classmethod
    def from_node(cls, source, node, original_index, indent, leading_text):
        match node.type:
            case "entry":
                key_node = node.child_by_field_name("key")

                key = None
                if key_node is not None:
                    key = make_one_line(node_text(source, key_node))

                return cls(
                    kind=BlockType.Entry,
                    formatted_text=format_entry(source, node, indent),
                    original_index=original_index,
                    key=key,
                    crossref=extract_crossref(source, node),
                    leading_text=leading_text,
                )

            case "string":
                return cls(
                    kind=BlockType.String,
                    formatted_text=format_string(source, node),
                    original_index=original_index,
                    leading_text=leading_text,
                )

            case "preamble":
                return cls(
                    kind=BlockType.Preamble,
                    formatted_text=format_preamble(source, node),
                    original_index=original_index,
                    leading_text=leading_text,
                )

            case "comment":
                return cls(
                    kind=BlockType.Comment,
                    formatted_text=format_comment(source, node),
                    original_index=original_index,
                    leading_text=leading_text,
                )

            case _:
                return cls(
                    kind=BlockType.Raw,
                    formatted_text=node_text(source, node),
                    original_index=original_index,
                    leading_text=leading_text,
                )


@dataclass(slots=True)
class Bib:
    blocks: list[Block]
    header_text: str = ""
    trailing_text: str = ""

    @staticmethod
    def _alphabetical_key(block: Block) -> tuple[str, int]:
        """
        Sorting key with deterministic fallback to the original position.
        """
        return (
            block.key.casefold() if block.key is not None else "",
            block.original_index,
        )

    @classmethod
    def _sort_entries(cls, entries: list[Block]) -> list[Block]:
        """
        Sort entries alphabetically while respecting crossref dependencies.

        For
            @inproceedings{Child,
                crossref = {Parent},
            }

            @proceedings{Parent, ...}

        Child is kept before Parent.
        """
        if len(entries) < 2:
            return entries.copy()

        key_to_index: dict[str, int] = {}

        for index, block in enumerate(entries):
            if block.key is None:
                continue

            normalized_key = block.key.casefold()

            if normalized_key in key_to_index:
                logger.warning(
                    "Duplicate BibTeX key encountered: %s",
                    block.key,
                )
                continue

            key_to_index[normalized_key] = index

        # Edge child -> parent:
        # the child must occur before the cross-referenced parent.
        outgoing: list[list[int]] = [[] for _ in entries]
        indegree = [0 for _ in entries]

        for child_index, child in enumerate(entries):
            if child.crossref is None:
                continue

            parent_index = key_to_index.get(child.crossref.casefold())

            # The parent may be in a different section or not in this file.
            if parent_index is None or parent_index == child_index:
                continue

            outgoing[child_index].append(parent_index)
            indegree[parent_index] += 1

        available: list[tuple[str, int, int]] = []

        for index, block in enumerate(entries):
            if indegree[index] == 0:
                key, original_index = cls._alphabetical_key(block)
                heapq.heappush(
                    available,
                    (key, original_index, index),
                )

        result: list[Block] = []
        processed: set[int] = set()

        while available:
            _, _, index = heapq.heappop(available)

            if index in processed:
                continue

            processed.add(index)
            result.append(entries[index])

            for target_index in outgoing[index]:
                indegree[target_index] -= 1

                if indegree[target_index] == 0:
                    target = entries[target_index]
                    key, original_index = cls._alphabetical_key(target)

                    heapq.heappush(
                        available,
                        (key, original_index, target_index),
                    )

        if len(result) != len(entries):
            logger.warning(
                "Crossref cycle detected; sorting remaining entries "
                "alphabetically"
            )

            remaining = [
                block
                for index, block in enumerate(entries)
                if index not in processed
            ]

            remaining.sort(key=cls._alphabetical_key)
            result.extend(remaining)

        return result

    def sort_global(self):
        """
        Sort all entries globally. Non-entr blocks retain their position.
        """
        entries = [e for e in self.blocks if e.kind == BlockType.Entry]
        sorted_entries = iter(self._sort_entries(entries))

        self.blocks = [
            next(sorted_entries) if block.kind is BlockType.Entry else block
            for block in self.blocks
        ]

    @staticmethod
    def _render_block(block: Block) -> str:
        parts: list[str] = []

        leading_text = block.leading_text.strip()
        formatted_text = block.formatted_text.strip()

        if leading_text:
            parts.append(leading_text)

        if formatted_text:
            parts.append(formatted_text)

        return "\n".join(parts)

    def get_text(self):
        parts: list[str] = []

        header = self.header_text.strip()
        if header:
            parts.append(header)

        for block in self.blocks:
            rendered = self._render_block(block)

            if rendered:
                parts.append(rendered)

        trailing = self.trailing_text.strip()
        if trailing:
            parts.append(trailing)

        if not parts:
            return ""

        return "\n\n".join(parts) + "\n"


def unwrap_bibtex_value(value: str) -> str:
    """
    Remove one pair of surrounding braces or quotation marks.

    Examples:
        "{Proceedings2026}" -> "Proceedings2026"
        '"Proceedings2026"' -> "Proceedings2026"
        "proceedings"       -> "proceedings"

    Parameters:
        value (str): Value which is unwrapped.

    Returns:
        str: Unwrapped text.
    """
    value = value.strip()

    if len(value) >= 2:
        delimiters = (value[0], value[-1])

        if delimiters in {
            ("{", "}"),
            ('"', '"'),
        }:
            return value[1:-1].strip()

    return value


def extract_crossref(source: bytes, entry_node: Node) -> str | None:
    """
    Extract the crossref target of an entry.

    Parameters:
        source (bytes): Total source.
        entry_node (Node): Current node to extract crossref from.

    Returns:
        str | None: None if the entry does not contain a crossref field.
            Otherwise the key is returned.
    """
    for field_node in entry_node.children_by_field_name("field"):
        name_node = field_node.child_by_field_name("name")
        value_node = field_node.child_by_field_name("value")

        if name_node is None or value_node is None:
            continue

        name = node_text(source, name_node).strip().casefold()

        if name != "crossref":
            continue

        value = make_one_line(node_text(source, value_node))
        return unwrap_bibtex_value(value)

    return None


def node_text(source: bytes, node: Node) -> str:
    """
    Decodes the text for the given node.

    Parameters:
        source (bytes): Total text in bytes (which contains the node text).
        node (Node): Node for which the text is decoded.

    Returns:
        str: Decoded text.
    """
    return source[node.start_byte : node.end_byte].decode("UTF-8")


def make_one_line(text: str) -> str:
    """
    Replace line breaks and their surrounding indentation with one space.
    Spaces that already occur within a line are left unchanged.

    Parameters:
        text (str): Text which is made to one line.

    Returns:
        str: One line text.
    """
    return re.sub(
        r"[ \t]*(?:\r\n|\r|\n)[ \t]*",
        " ",
        text.strip(),
    )


def has_opening_delimiter(source: bytes, type_node: Node) -> bool:
    """
    Checks if the type_node has an opening delimiter.

    Parameters:
        source (bytes): Total text in bytes.
        type_node (Node): Node to check.

    Returns:
        bool: True if an opening delimiter ("{", "(") is found.
    """
    index = type_node.end_byte

    while index < len(source) and source[index] in b" \t\r\n":
        index += 1

    return index < len(source) and (
        source[index] == ord("{") or source[index] == ord("(")
    )


def format_entry(source: bytes, node: Node, indent: str) -> str:
    """
    Formats an entry node.

    Parameters:
        source (bytes): Total text in bytes.
        node (Node): Node to format as entry.
        indent (str): Indentation with is prefixed for each field of the node.

    Returns:
        str: Formatted text.
    """
    original = node_text(source, node)

    # Do not modify malformed entries
    if node.has_error:
        logger.warning("Skipping entry due to syntax errors")
        return original

    type_node = node.child_by_field_name("ty")
    key_node = node.child_by_field_name("key")
    field_nodes = node.children_by_field_name("field")

    if type_node is None or key_node is None:
        return original

    if not has_opening_delimiter(source, type_node):
        return original

    entry_type = node_text(source, type_node).strip()
    key = make_one_line(node_text(source, key_node))

    fields: list[tuple[str, str]] = []

    for field_node in field_nodes:
        if field_node.has_error:
            return original

        name_node = field_node.child_by_field_name("name")
        value_node = field_node.child_by_field_name("value")

        if name_node is None or value_node is None:
            return original

        name = node_text(source, name_node).strip()
        value = make_one_line(node_text(source, value_node))

        fields.append((name, value))

    field_width = max((len(name) for name, _ in fields), default=0)

    lines = [f"{entry_type}{{{key},"]

    for name, value in fields:
        lines.append(f"{indent}{name:<{field_width}} = {value},")

    lines.append("}")

    return "\n".join(lines)


def format_string(source: bytes, node: Node) -> str:
    """
    Formats a string node.

    Parameters:
        source (bytes): Total text in bytes.
        node (Node): Node to format as entry.

    Returns:
        str: Formatted text.
    """
    original = node_text(source, node)

    if node.has_error:
        return original

    type_node = node.child_by_field_name("ty")
    name_node = node.child_by_field_name("name")
    value_node = node.child_by_field_name("value")

    if type_node is None or name_node is None or value_node is None:
        return original

    if not has_opening_delimiter(source, type_node):
        return original

    entry_type = node_text(source, type_node).strip()
    name = node_text(source, name_node).strip()
    value = make_one_line(node_text(source, value_node))

    return f"{entry_type}{{{name} = {value}}}"


def format_preamble(source: bytes, node: Node) -> str:
    """
    Formats a preamble node.

    Parameters:
        source (bytes): Total text in bytes.
        node (Node): Node to format as entry.

    Returns:
        str: Formatted text.
    """
    original = node_text(source, node)

    if node.has_error:
        return original

    type_node = node.child_by_field_name("ty")
    value_node = node.child_by_field_name("value")

    if type_node is None or value_node is None:
        return original

    if not has_opening_delimiter(source, type_node):
        return original

    entry_type = node_text(source, type_node).strip()
    value = make_one_line(node_text(source, value_node))

    return f"{entry_type}{{{value}}}"


def format_comment(source: bytes, node: Node) -> str:
    """
    Formats a comment node. Comments stay as they are.

    Parameters:
        source (bytes): Total text in bytes.
        node (Node): Node to format as entry.

    Returns:
        str: Formatted text.
    """
    return node_text(source, node)


def make_tree_sitter_bibtex_parseable(text: str) -> str:
    """
    There is a bug in the used treesitter grammar:
        @entry (KEY) is allowed but an additional ' ' cannot be parsed:
        @entry ( KEY) is not allowed.
    This function removes such an empty space to make it parseable.

    Parameters:
        text (str): Text which is made parseable

    Returns:
        str: Parseable text
    """
    return re.sub(
        r"(@[A-Za-z][A-Za-z0-9_-]*\s*[\{\(])\s+",
        r"\1",
        text,
    )


def parse_bib(text: str, indent: str) -> Bib:
    text = make_tree_sitter_bibtex_parseable(text)
    source = text.encode("utf-8")
    tree = PARSER.parse(source)
    nodes = list(tree.root_node.named_children)

    if not nodes:
        return Bib(blocks=[], header_text=text)

    blocks: list[Block] = []
    header_text = source[: nodes[0].start_byte].decode("utf-8")
    previous_end = nodes[0].start_byte

    for original_index, node in enumerate(nodes):
        if node.start_byte < previous_end:
            continue

        if blocks:
            leading_text = source[previous_end : node.start_byte].decode(
                "utf-8"
            )
        else:
            leading_text = ""
        blocks.append(
            Block.from_node(source, node, original_index, indent, leading_text)
        )

        previous_end = node.end_byte

    trailing_text = source[previous_end:].decode("utf-8")

    return Bib(blocks, header_text, trailing_text)
