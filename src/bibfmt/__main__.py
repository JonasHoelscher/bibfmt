#!/usr/bin/env python3

# Standard libraries
import argparse
from pathlib import Path

# Local libraries
from .formatter import format_bibtex

if __name__ == "__main__":
    argument_parser = argparse.ArgumentParser(
        description="Format a BibTeX file"
    )

    argument_parser.add_argument("file", type=Path)

    argument_parser.add_argument(
        "-o",
        "--overwrite",
        action="store_true",
        help="Overwrite the input file",
    )
    argument_parser.add_argument(
        "-i",
        "--indent",
        type=str,
        help="Set indentation",
    )

    args = argument_parser.parse_args()

    indent = "    "
    if args.indent is not None:
        indent = args.indent

    original = args.file.read_text(encoding="utf-8")
    formatted = format_bibtex(original, indent)

    if args.overwrite:
        args.file.write_text(formatted, encoding="utf-8")
    else:
        print(formatted, end="")
