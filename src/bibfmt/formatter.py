#!/usr/bin/env python3

# Standard libraries
import logging
import re

# Third party libraries
import tree_sitter_bibtex as tsbibtex
from tree_sitter import Language, Node, Parser

logger = logging.getLogger(__name__)
BIBTEX_LANGUAGE = Language(tsbibtex.language())
PARSER = Parser(BIBTEX_LANGUAGE)


def make_tree_sitter_bibtex_parseable(text: str) -> str:
    """
    There is a bug in the used treesitter grammar:
        @entry (KEY) is allowed but an additional ' ' cannot be parsed:
        @entry ( KEY) is not allowed.
    This function removes such a emptyspace to make it parseable
    """
    return re.sub(
        r"(@[A-Za-z][A-Za-z0-9_-]*\s*[\{\(])\s+",
        r"\1",
        text,
    )


def node_text(source: bytes, node: Node) -> str:
    return source[node.start_byte : node.end_byte].decode("UTF-8")


def make_one_line(text: str) -> str:
    """
    Replace line breaks and their surrounding indentation with one space.

    Spaces that already occur within a line are left unchanged.
    """
    return re.sub(
        r"[ \t]*(?:\r\n|\r|\n)[ \t]*",
        " ",
        text.strip(),
    )


def has_opening_delimiter(source: bytes, type_node: Node) -> bool:
    index = type_node.end_byte

    while index < len(source) and source[index] in b" \t\r\n":
        index += 1

    return index < len(source) and (
        source[index] == ord("{") or source[index] == ord("(")
    )


def format_entry(source: bytes, node: Node, indent: str) -> str:
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
    return node_text(source, node)


def format_bibtex(text: str, indent: str = "    ") -> str:
    source = make_tree_sitter_bibtex_parseable(text).encode("utf-8")
    tree = PARSER.parse(source)

    replacements: list[tuple[int, int, bytes]] = []
    consumed_until = 0

    for node in tree.root_node.named_children:
        if node.start_byte < consumed_until:
            continue

        match node.type:
            case "entry":
                formatted = format_entry(source, node, indent)
                end = node.end_byte
            case "string":
                formatted = format_string(source, node)
                end = node.end_byte
            case "preamble":
                formatted = format_preamble(source, node)
                end = node.end_byte
            case "comment":
                formatted = format_comment(source, node)
                end = node.end_byte
            case _:
                # Preserve junk, %-comments and other unrecognized text
                continue

        replacements.append((node.start_byte, end, formatted.encode("utf-8")))

        consumed_until = end

    result = bytearray()
    cursor = 0

    for start, end, replacement in replacements:
        result.extend(source[cursor:start])
        result.extend(replacement)
        cursor = end

    result.extend(source[cursor:])

    return result.decode("utf-8")
